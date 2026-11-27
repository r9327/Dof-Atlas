from __future__ import annotations

import threading
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from queue import Empty, Queue
from time import monotonic
from typing import Any, Callable, Iterable, TYPE_CHECKING

from app.core.network_presentation import capture_retry_allowed
from app.validation_log import record_validation

if TYPE_CHECKING:
    from app.network.progress_bridge import EventApplicationResult, NetworkProgressBridge
    from app.quest_catalog import QuestCatalog


_CALIBRATION_PENDING_REASONS = frozenset(
    {
        "calibrating",
        "awaiting_character_identity",
        "awaiting_quest_journal",
        "awaiting_distinct_quest_completions",
    }
)

# Runtime bootstrap uses these fail-closed reasons when an exact-build mapping
# exists but is not safe enough for the reviewed current quest contract. They
# must enter calibration just like a missing mapping; otherwise an old Atlas
# lqn mapping would be disabled correctly but never upgraded to safe live idz.
_RUNTIME_REASONS_REQUIRING_CALIBRATION = frozenset(
    {
        "mapping_no_exact_match",
        "mapping_missing_required_events",
        "mapping_current_profile_noncanonical",
    }
)
_CLIENT_RETRY_REASONS = frozenset(
    {"no_window_handles", "build_fingerprint_unavailable", "runtime_stopped", "build_changed"}
)


@dataclass(frozen=True, slots=True)
class NetworkApplicationStatus:
    running: bool
    calibrating: bool
    reason: str
    build_sha256: str = ""
    mapping_path: Path | None = None
    distinct_completion_count: int = 0
    quest_journal_observation_count: int = 0
    quest_journal_verified_count: int = 0
    snapshot_candidate_count: int = 0
    snapshot_candidate_type_url: str = ""
    catchup_ready: bool = False


class NetworkApplicationCoordinator:
    """Keep protocol bootstrap/calibration work away from the Qt UI thread.

    The coordinator owns no progression data and no packet decoder itself. It
    serializes potentially expensive controller operations (notably exact-build
    fingerprinting) on one stoppable worker and forwards changed progression
    results through a queue. Missing exact-build mappings are calibrated
    fail-closed. Existing stale/noncanonical current-profile mappings are also
    sent through calibration so reviewed ``idz`` live completion can replace an
    old unsafe mapping without user intervention.

    A strictly decoded ``idr`` journal may reconcile finished quests only after
    the exact build and the same transport session have positively identified
    the Atlas character. Active quests remain informational and never become
    completed progress. Live completion still requires independently calibrated
    final-step ``idz`` evidence.
    """

    def __init__(
        self,
        window_handles_provider: Callable[[], Iterable[int]],
        *,
        logger: Logger | None = None,
    ) -> None:
        # Home imports NetworkApplicationStatus before the splash is shown. Keep
        # the capture/calibration/progression stacks out of module import time;
        # they are needed only when a real coordinator instance is requested.
        from app.core.logger import get_runtime_logger
        from app.network.calibration_controller import ProtocolCalibrationController
        from app.network.controller import NetworkControllerStatus, NetworkRuntimeController
        from app.network.elevated_capture import ElevatedWindowsProtocolSource

        self.window_handles_provider = window_handles_provider
        self.logger = logger or get_runtime_logger()
        self._capture_source = ElevatedWindowsProtocolSource(
            window_handles_provider,
            logger=self.logger,
            keep_helper_alive=True,
        )
        self.calibration = ProtocolCalibrationController(
            window_handles_provider,
            protocol_source=self._capture_source,
            logger=self.logger,
        )
        self.runtime = NetworkRuntimeController(
            window_handles_provider,
            protocol_source=self._capture_source,
            logger=self.logger,
        )
        self._commands: Queue[str] = Queue()
        self._results: Queue[EventApplicationResult] = Queue()
        self._statuses: Queue[NetworkApplicationStatus] = Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        # stop() is terminal for this coordinator. Only a crashed/interrupted
        # worker may restart; a late UI callback must never reopen UAC/capture.
        self._shutdown_requested = False
        self._operation_lock = threading.RLock()
        self._context_ready = False
        self._context: tuple[QuestCatalog, Any, Any] | None = None
        self._worker_compact_context_ready = False
        self._calibration_pending = False
        self._next_runtime_retry_at = 0.0
        self._applied_journal_evidence_keys: set[tuple[Any, ...]] = set()
        self._last_status = NetworkApplicationStatus(False, False, "waiting_context")
        self._last_calibration = self.calibration.status()
        self._last_runtime = NetworkControllerStatus(False, "waiting_context")

    @property
    def worker_compact_context_ready(self) -> bool:
        with self._lock:
            return self._worker_compact_context_ready and self._context_ready

    @property
    def is_worker_running(self) -> bool:
        with self._lock:
            thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def configure_context(
        self,
        *,
        quest_catalog: QuestCatalog,
        achievement_provider: Any,
        guide_provider: Any = None,
    ) -> None:
        from app.quest_catalog import QuestCatalog

        if not isinstance(quest_catalog, QuestCatalog):
            raise TypeError("quest_catalog must be a QuestCatalog")
        if achievement_provider is None:
            raise ValueError("achievement_provider is required")
        with self._lock:
            if self._shutdown_requested:
                # A late Encyclopedia/Qt initialization may finish after
                # close. Do not repopulate controllers that stop() disposed.
                return
            self.calibration.configure_context(quest_catalog=quest_catalog)
            self.runtime.configure_context(
                quest_catalog=quest_catalog,
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            first_context = not self._context_ready
            self._context_ready = True
            self._context = (quest_catalog, achievement_provider, guide_provider)
            # An external Encyclopedia context may retain huge UI catalogues.
            # Only the worker-created compact context has the small-memory flag.
            self._worker_compact_context_ready = False
            if first_context:
                self._applied_journal_evidence_keys.clear()
        if first_context:
            self._enqueue_command("start_runtime_on_context_ready")
        else:
            self.start_worker()

    def start_worker(self) -> bool:
        with self._lock:
            if self._shutdown_requested or not capture_retry_allowed(self._last_status.reason):
                return False
            if self.is_worker_running:
                return True
            if self._thread is not None and self._thread.is_alive():
                return False
            # A prior stop/crash must not replay privileged commands or
            # publish old progress/status events in a fresh worker session.
            # Valid progress is persisted by the bridge; the UI will refresh
            # from that source when its Encyclopedia page becomes visible.
            # The lock prevents a concurrent status publisher from being
            # interleaved with this reset.
            for queue in (self._commands, self._results, self._statuses):
                while True:
                    try:
                        queue.get_nowait()
                    except Empty:
                        break
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run,
                name="DofusAtlas-NetworkCoordinator",
                daemon=True,
            )
            self._thread = thread
            try:
                thread.start()
            except Exception:
                self._thread = None
                self._publish_status(NetworkApplicationStatus(False, False, "coordinator_start_failed"))
                self._stop_event.set()
                self.logger.exception("Network coordinator thread start failed.")
                return False
            return True

    def _enqueue_command(self, command: str) -> bool:
        """Atomically reject commands racing with explicit shutdown."""

        with self._lock:
            if (self._shutdown_requested
                    or not capture_retry_allowed(self._last_status.reason)
                    or not self.start_worker()):
                return False
            # start_worker() may be wrapped by a test or integration adapter
            # that synchronously triggers stop(). Never queue after that.
            if (self._shutdown_requested or self._stop_event.is_set()
                    or not capture_retry_allowed(self._last_status.reason)):
                return False
            self._commands.put(command)
            return True

    def request_start_calibration(self) -> bool:
        with self._lock:
            if self._shutdown_requested:
                return False
            if not capture_retry_allowed(self._last_status.reason):
                return False
            if not self._context_ready:
                self._publish_status(NetworkApplicationStatus(False, False, "waiting_context"))
                return False
        return self._enqueue_command("start_calibration")

    def request_prepare_capture(self) -> bool:
        """Trigger the Windows elevation prompt before catalogue preload."""

        return self._enqueue_command("prepare_capture")

    def request_start_verified_runtime(self) -> bool:
        with self._lock:
            if self._shutdown_requested or not self._context_ready:
                return False
        return self._enqueue_command("start_runtime")

    def request_start_compact_runtime(self) -> bool:
        """Start from Home without synchronously loading Quests on the Qt thread."""
        with self._lock:
            if self._shutdown_requested:
                return False
            ready = self._context_ready
        if ready:
            return self.request_start_verified_runtime()
        return self._enqueue_command("start_compact_runtime")

    def request_configure_compact_context(self) -> bool:
        """Replace the UI-owned context on the existing network worker."""
        with self._lock:
            if self._shutdown_requested:
                return False
            if self._worker_compact_context_ready and self._context_ready:
                return True
        return self._enqueue_command("configure_compact_context")

    def latest_status(self) -> NetworkApplicationStatus:
        with self._lock:
            return self._last_status

    def has_pending_ui_events(self) -> bool:
        """Cheap UI poll gate that avoids empty queue allocation churn."""

        return not self._statuses.empty() or not self._results.empty()

    def drain_statuses(self, limit: int = 50) -> list[NetworkApplicationStatus]:
        rows: list[NetworkApplicationStatus] = []
        for _ in range(max(0, int(limit))):
            if self._statuses.empty():
                break
            try:
                rows.append(self._statuses.get_nowait())
            except Empty:
                break
        return rows

    def drain_results(self, limit: int = 100) -> list[EventApplicationResult]:
        rows: list[EventApplicationResult] = []
        for _ in range(max(0, int(limit))):
            if self._results.empty():
                break
            try:
                rows.append(self._results.get_nowait())
            except Empty:
                break
        return rows

    def stop(self, join_timeout: float = 3.0) -> bool:
        with self._lock:
            self._shutdown_requested = True
            self._stop_event.set()
        components_stopped = self._stop_capture_components()
        with self._lock:
            self._calibration_pending = False
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, float(join_timeout)))
        worker_stopped = thread is None or not thread.is_alive()
        with self._lock:
            if worker_stopped and self._thread is thread:
                self._thread = None
        if not worker_stopped:
            self.logger.error("Network coordinator did not stop within timeout.")
        stopped = components_stopped and worker_stopped
        # A terminal shutdown owns the authoritative status, including callers
        # outside Qt. Old active notifications must not survive the shutdown.
        with self._lock:
            self._last_status = NetworkApplicationStatus(
                False, False, "stopped" if stopped else "stop_failed",
            )
            if worker_stopped:
                self._context = None
                self._context_ready = False
                self._worker_compact_context_ready = False
            for queue in (self._commands, self._results, self._statuses):
                while True:
                    try:
                        queue.get_nowait()
                    except Empty:
                        break
        return stopped

    def _run(self) -> None:
        try:
            self._publish_current("context_ready")
            while not self._stop_event.is_set():
                command = None
                try:
                    command = self._commands.get(timeout=0.15)
                except Empty:
                    command = None
                # stop() can arrive while Queue.get() is waiting. Do not
                # execute the just-received command after shutdown began.
                if self._stop_event.is_set():
                    break
                if command is not None:
                    self._handle_command(command)
                if self._stop_event.is_set():
                    break
                self._poll_calibration()
                self._drain_runtime_results()
                self._retry_when_client_appears()
        except Exception:
            self.logger.exception("Network coordinator worker failed.")
            self._publish_current("coordinator_error")
        finally:
            # Always attempt every cleanup step, even if a calibration
            # controller raises while a background worker is exiting.
            stopped = self._stop_capture_components()
            with self._lock:
                self._calibration_pending = False
                terminal_shutdown = self._shutdown_requested
            if not terminal_shutdown and not self._stop_event.is_set():
                # A dead worker cannot continue to advertise an active reader.
                # A failed cleanup also prohibits every restart path.
                reason = "coordinator_error" if stopped else "coordinator_cleanup_failed"
                self._publish_status(NetworkApplicationStatus(False, False, reason))

    def _stop_capture_components(self) -> bool:
        """Both explicit shutdown and worker failure use one cleanup contract."""
        with self._operation_lock:
            try:
                calibration_stopped = bool(self.calibration.stop())
            except Exception:
                self.logger.exception("Network calibration cleanup failed.")
                calibration_stopped = False
            try:
                runtime_stopped = bool(self.runtime.stop())
            except Exception:
                self.logger.exception("Network runtime cleanup failed.")
                runtime_stopped = False
            capture_stopped = self._close_capture_source()
        return calibration_stopped and runtime_stopped and capture_stopped

    def _close_capture_source(self) -> bool:
        try:
            self._capture_source.close()
        except Exception:
            self.logger.exception("Elevated network capture helper cleanup failed.")
            return False
        return True

    def _handle_command(self, command: str) -> None:
        reason = self.latest_status().reason
        if self._stop_event.is_set() or not capture_retry_allowed(reason):
            return
        if command == "prepare_capture":
            self._prepare_capture()
            return
        if command == "start_compact_runtime":
            self._publish_current("network_retry_starting")
            self._start_compact_runtime()
            return
        if command == "configure_compact_context":
            self._start_compact_runtime(replace_existing=True)
            return
        if command == "start_calibration":
            self._start_calibration()
            return
        if command == "start_runtime":
            self._publish_current("network_retry_starting")
            self._start_runtime()
        elif command == "start_runtime_on_context_ready" and reason != "capture_elevation_cancelled":
            self._start_runtime()

    def _start_compact_runtime(self, *, replace_existing: bool = False) -> None:
        """Resolve or replace the minimal context on the existing worker."""
        with self._lock:
            if self._shutdown_requested or self._stop_event.is_set():
                return
            already_ready = self._context_ready
            previous_context = self._context
            if replace_existing:
                if already_ready and self._worker_compact_context_ready:
                    return
                # An automatic context update can arrive after the Windows
                # prompt was dismissed. A cold start must wait for a user retry.
                if not already_ready and self._last_status.reason == "capture_elevation_cancelled":
                    return
        if already_ready and not replace_existing:
            self._start_runtime()
            return
        # Replacing a live rich context must not temporarily advertise a
        # disconnect or restart the capture. Only cold activation is pending.
        if not already_ready:
            self._publish_current("network_context_loading")
        try:
            from app.modules.encyclopedia.providers import (
                AchievementProvider, GuideProvider,
            )
            from app.quest_catalog_details import load_network_catalog

            catalog = load_network_catalog()
            achievements = AchievementProvider()
            guides = GuideProvider()
        except Exception:
            self.logger.exception("Cold network context loading failed.")
            self._publish_current("network_context_load_failed")
            return
        with self._lock:
            if self._shutdown_requested or self._stop_event.is_set():
                return
            if self._context_ready and (
                not replace_existing or self._context is not previous_context
            ):
                # A newer context arrived while reading disk. Do not overwrite
                # it or restart an already active capture during replacement.
                if not replace_existing:
                    self.request_start_verified_runtime()
                return
            self.configure_context(
                quest_catalog=catalog,
                achievement_provider=achievements,
                guide_provider=guides,
            )
            if not self._shutdown_requested and not self._stop_event.is_set():
                self._worker_compact_context_ready = True

    def _prepare_capture(self) -> None:
        """Launch and pause the reusable helper so UAC happens immediately."""

        with self._operation_lock:
            if self._stop_event.is_set():
                return
            if self.runtime.is_running or self.calibration.is_running:
                return
            try:
                self._capture_source.start()
                self._capture_source.stop()
            except Exception as exc:
                reason = str(
                    getattr(exc, "reason", "")
                    or getattr(self._capture_source, "start_failure_reason", "")
                    or "capture_helper_start_failed"
                )
                self.logger.exception("Early network capture preparation failed.")
                self._publish_current(reason)
                return
        if self._stop_event.is_set():
            return
        self._publish_current("capture_ready_waiting_context")

    def _start_calibration(self) -> None:
        """Start passive exact-build calibration for safe live idz."""

        with self._operation_lock:
            if self._stop_event.is_set():
                return
            if self.runtime.is_running and not self.runtime.stop():
                self._publish_current("runtime_stop_failed_before_calibration")
                return
            self._last_calibration = self.calibration.start()
        # stop() may have been requested while calibration.start() held the
        # operation lock. Do not re-arm calibration after stop cleared it.
        if self._stop_event.is_set():
            return
        pending = self._last_calibration.reason in _CALIBRATION_PENDING_REASONS
        with self._lock:
            # Also check inside the state lock: stop() may finish clearing
            # this flag between the earlier stop guard and this assignment.
            if self._stop_event.is_set():
                return
            self._calibration_pending = pending
        self._publish_current(self._last_calibration.reason)
        if self._last_calibration.reason == "mapping_already_ready":
            self._start_runtime()

    def _start_runtime(self) -> None:
        with self._operation_lock:
            if self._stop_event.is_set():
                return
            with self._lock:
                calibration_pending = self._calibration_pending
            if calibration_pending or self.calibration.is_running:
                self._publish_current("calibration_running")
                return
            self._last_runtime = self.runtime.start_if_ready()
        if self._stop_event.is_set():
            return
        self._publish_current(self._last_runtime.reason)
        if self._last_runtime.reason in _RUNTIME_REASONS_REQUIRING_CALIBRATION:
            self._start_calibration()
        elif self._last_runtime.reason in _CLIENT_RETRY_REASONS:
            self._next_runtime_retry_at = monotonic() + 2.5

    def _retry_when_client_appears(self) -> None:
        with self._lock:
            ready = self._context_ready
            pending = self._calibration_pending
            reason = self._last_status.reason
        if self._stop_event.is_set() or monotonic() < self._next_runtime_retry_at:
            return
        self._next_runtime_retry_at = monotonic() + 2.5
        calibrating = pending or self.calibration.is_running
        running = self.runtime.is_running
        if not (
            ready
            and reason != "capture_elevation_cancelled"
            and capture_retry_allowed(reason)
            and (calibrating or running or reason in _CLIENT_RETRY_REASONS)
        ):
            # Keep the existing local window view current even when capture
            # is unavailable. Looking up windows never opens the UAC prompt.
            if not calibrating and not running:
                try:
                    self.window_handles_provider()
                except Exception:
                    self.logger.exception("Network window discovery failed.")
            return
        if calibrating or running:
            expected = self._last_calibration.build_sha256 if calibrating else self._last_runtime.build_sha256
            if not expected:
                return
            if self.runtime.active_build_sha256() == expected:
                if not (
                    calibrating and self._last_runtime.reason == "mapping_no_exact_match"
                    and self.runtime.has_new_exact_mapping(expected)
                ):
                    return
                restart_reason = "mapping_ready_restarting"
            else:
                restart_reason = "build_changed"
            if not self._stop_readers_for_restart(calibrating=calibrating, reason=restart_reason):
                return
        self._start_runtime()

    def _stop_readers_for_restart(self, *, calibrating: bool, reason: str) -> bool:
        from app.network.calibration_controller import ProtocolCalibrationControllerStatus

        with self._operation_lock:
            if self._stop_event.is_set():
                return False
            controller = self.calibration if calibrating else self.runtime
            if not controller.stop():
                self._publish_current("calibration_stop_failed" if calibrating else "runtime_stop_failed")
                return False
            with self._lock:
                self._calibration_pending = False
                self._last_calibration = ProtocolCalibrationControllerStatus(False, "stopped")
                self._applied_journal_evidence_keys.clear()
            self._publish_current(reason)
            return True

    def _poll_calibration(self) -> None:
        if self._stop_event.is_set():
            return
        with self._lock:
            if not self._calibration_pending:
                return
        with self._operation_lock:
            if self._stop_event.is_set():
                return
            status = self.calibration.poll()
        # stop() signals before acquiring the operation lock. A poll already
        # in progress must not publish identities or apply Quest evidence
        # once shutdown has begun.
        if self._stop_event.is_set():
            return
        self._last_calibration = status
        for result in self.calibration.drain_identity_results():
            if self._stop_event.is_set():
                return
            self._results.put(result)
        if self._stop_event.is_set():
            return
        self._apply_calibration_journal_evidence()
        # Journal evidence may finish after stop() began. Do not publish its
        # old state or re-enable runtime as a final calibration side effect.
        if self._stop_event.is_set():
            return
        terminal = status.reason not in _CALIBRATION_PENDING_REASONS
        if terminal:
            with self._lock:
                self._calibration_pending = False
        self._publish_current(status.reason)
        if status.reason in {"mapping_installed_not_started", "mapping_already_installed"}:
            self._apply_calibration_evidence()
            self._start_runtime()

    def _bridge_for_calibration(self) -> NetworkProgressBridge | None:
        from app.constants import QUEST_PROGRESS_FILE
        from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
        from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
            AchievementProgressService,
        )
        from app.network.instrumentation import InstrumentedNetworkProgressBridge

        with self._lock:
            context = self._context
        if context is None:
            return None
        quest_catalog, achievement_provider, guide_provider = context
        return InstrumentedNetworkProgressBridge(
            quest_catalog=quest_catalog,
            quest_progress_service=QuestProgressService(QUEST_PROGRESS_FILE),
            achievement_progress_service=AchievementProgressService(),
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
            logger=self.logger,
        )

    def _identify_calibration_character(self, bridge: NetworkProgressBridge, evidence: Any) -> tuple[bool, str]:
        from app.network.events import CharacterIdentifiedEvent

        session_id = str(getattr(evidence, "session_id", "") or "calibration")
        identified = bridge.handle(
            CharacterIdentifiedEvent(
                session_id=session_id,
                event_id="calibration:identity",
                reliable=True,
                character_name=str(getattr(evidence, "character_name", "") or ""),
                character_id=int(getattr(evidence, "character_id", 0) or 0),
            )
        )
        if not identified.accepted:
            self.logger.warning("Verified calibration evidence could not resolve its character.")
            return False, session_id
        return True, session_id

    def _apply_calibration_journal_evidence(self) -> None:
        if self._stop_event.is_set():
            return
        from app.network.protocol_calibration import QuestJournalCalibrationEvidence

        evidences = tuple(getattr(self.calibration, "verified_journal_evidences", ()) or ())
        if not evidences:
            evidence = getattr(self.calibration, "verified_journal_evidence", None)
            evidences = (evidence,) if evidence is not None else ()
        for evidence in evidences:
            if self._stop_event.is_set():
                return
            if isinstance(evidence, QuestJournalCalibrationEvidence):
                self._apply_one_calibration_journal_evidence(evidence)

    def _apply_one_calibration_journal_evidence(self, evidence: Any) -> None:
        if self._stop_event.is_set():
            return
        from app.network.current_protocol_profile import (
            DOFUS_361010_PROFILE,
            dofus_361010_profile_digest,
        )
        from app.network.events import QuestJournalSnapshotEvent
        from app.network.protocol_calibration import QuestJournalCalibrationEvidence

        if not isinstance(evidence, QuestJournalCalibrationEvidence):
            return
        if (
            evidence.game_version != DOFUS_361010_PROFILE.game_version
            or evidence.evidence_revision != DOFUS_361010_PROFILE.evidence_revision
            or evidence.source_commit != DOFUS_361010_PROFILE.source_commit
            or evidence.profile_digest != dofus_361010_profile_digest()
            or evidence.quest_journal_type_url != DOFUS_361010_PROFILE.quest_journal_type_url
            or len(str(evidence.build_sha256 or "")) != 64
            or not str(evidence.session_id or "").strip()
            or not str(evidence.character_key or "").strip()
            or not str(evidence.character_name or "").strip()
            or int(evidence.character_id or 0) <= 0
            or int(evidence.journal_observation_count or 0) <= 0
        ):
            return
        expected_build = str(getattr(self._last_calibration, "build_sha256", "") or "")
        if expected_build and evidence.build_sha256 != expected_build:
            return

        journal_quest_ids = tuple(
            sorted({int(quest_id) for quest_id in evidence.journal_verified_quest_ids})
        )
        evidence_key = (
            evidence.build_sha256,
            evidence.session_id,
            evidence.character_key,
            evidence.character_id,
            journal_quest_ids,
            evidence.journal_observation_count,
        )
        with self._lock:
            if evidence_key in self._applied_journal_evidence_keys:
                return

        bridge = self._bridge_for_calibration()
        if bridge is None:
            return
        identified, session_id = self._identify_calibration_character(bridge, evidence)
        if not identified or self._stop_event.is_set():
            return

        journal_result = bridge.handle(
            QuestJournalSnapshotEvent(
                session_id=session_id,
                event_id="calibration:quest-journal",
                reliable=True,
                finished_quest_ids=journal_quest_ids,
                active_quest_ids=(),
            )
        )
        if not journal_result.accepted:
            return
        # Publish accepted no-op journals too: the Qt shell refreshes its
        # profile list and follows the Organizer favorite when one is defined.
        self._results.put(journal_result)

        with self._lock:
            self._applied_journal_evidence_keys.add(evidence_key)

    def _apply_calibration_evidence(self) -> None:
        if self._stop_event.is_set():
            return
        from app.network.events import QuestCompletedEvent

        certificate = getattr(self.calibration, "verified_certificate", None)
        if certificate is None:
            return
        bridge = self._bridge_for_calibration()
        if bridge is None:
            return
        identified, session_id = self._identify_calibration_character(bridge, certificate)
        if not identified or self._stop_event.is_set():
            return

        # The reviewed journal was already reconciled when exact-build,
        # same-session identity evidence became available. The full certificate
        # adds only independently verified live final-step completions.
        for quest_id in certificate.verified_quest_ids:
            if self._stop_event.is_set():
                return
            result = bridge.handle(
                QuestCompletedEvent(
                    session_id=session_id,
                    event_id=f"calibration:quest:{int(quest_id)}",
                    reliable=True,
                    quest_id=int(quest_id),
                )
            )
            if result.accepted and result.changed:
                self._results.put(result)

    def _drain_runtime_results(self) -> None:
        if self._stop_event.is_set():
            return
        for result in self.runtime.drain_results(100):
            if self._stop_event.is_set():
                return
            reason = str(result.reason or "")
            activates_character = bool(
                result.accepted
                and result.character_key
                and reason in {
                    "character_identified",
                    "character_identified_with_quest_journal",
                }
            )
            # Session routing is not quest progression. Avoid rebuilding
            # views on character identification or disconnect when no quest
            # or achievement actually changed. Journal reconciliation and
            # other genuine progress mutations still reach the Qt bridge.
            progress_changed = bool(
                result.accepted
                and result.changed
                and reason not in {
                    "character_identified", "session_closed",
                }
            )
            # A confirmed session close needs one lightweight connected-
            # accounts refresh, but must never invalidate progress widgets.
            connection_changed = bool(
                result.accepted and result.changed and result.character_key
                and reason == "session_closed"
            )
            if progress_changed or activates_character or connection_changed:
                self._results.put(result)
        if self._stop_event.is_set():
            return
        if self._last_runtime.running and not self.runtime.is_running:
            self._last_runtime = self.runtime.status()
            self._publish_current(self._last_runtime.reason)

    def _publish_current(self, reason: str) -> None:
        if self._stop_event.is_set():
            return
        calibration = self._last_calibration
        runtime = self._last_runtime
        calibrating = bool(
            self._calibration_pending
            or self.calibration.is_running
            or str(calibration.reason or "") in _CALIBRATION_PENDING_REASONS
        )
        running = self.runtime.is_running
        build_sha256 = str(
            calibration.build_sha256 or runtime.build_sha256 or ""
        )
        mapping_path = calibration.mapping_path or runtime.mapping_path
        status = NetworkApplicationStatus(
            running=running,
            calibrating=calibrating,
            reason=str(reason or ""),
            build_sha256=build_sha256,
            mapping_path=mapping_path,
            distinct_completion_count=int(calibration.distinct_completion_count or 0),
            quest_journal_observation_count=int(
                getattr(calibration, "quest_journal_observation_count", 0) or 0
            ),
            quest_journal_verified_count=int(
                getattr(calibration, "quest_journal_verified_count", 0) or 0
            ),
            snapshot_candidate_count=int(calibration.snapshot_candidate_count or 0),
            snapshot_candidate_type_url=str(calibration.snapshot_candidate_type_url or ""),
            catchup_ready=bool(runtime.catchup_ready),
        )
        self._publish_status(status)

    def _publish_status(self, status: NetworkApplicationStatus) -> None:
        with self._lock:
            if self._stop_event.is_set() or status == self._last_status:
                return
            self._last_status = status
        record_validation("network_status", running=status.running,
                          calibrating=status.calibrating, reason=status.reason,
                          mapping_present=status.mapping_path is not None,
                          catchup_ready=status.catchup_ready,
                          completed=status.distinct_completion_count,
                          journal_observed=status.quest_journal_observation_count,
                          journal_verified=status.quest_journal_verified_count)
        if self._stop_event.is_set():
            return
        self.logger.info("Network status: reason=%s running=%s calibrating=%s",
                         status.reason, status.running, status.calibrating)
        with self._lock:
            if not self._stop_event.is_set():
                self._statuses.put(status)
