from __future__ import annotations

import threading
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from queue import Empty, Queue
from time import monotonic
from typing import Any, Callable, Iterable, TYPE_CHECKING

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
        self._operation_lock = threading.RLock()
        self._context_ready = False
        self._context: tuple[QuestCatalog, Any, Any] | None = None
        self._calibration_pending = False
        self._next_runtime_retry_at = 0.0
        self._applied_journal_evidence_keys: set[tuple[Any, ...]] = set()
        self._last_status = NetworkApplicationStatus(False, False, "waiting_context")
        self._last_calibration = self.calibration.status()
        self._last_runtime = NetworkControllerStatus(False, "waiting_context")

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
        self.calibration.configure_context(quest_catalog=quest_catalog)
        self.runtime.configure_context(
            quest_catalog=quest_catalog,
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
        )
        with self._lock:
            first_context = not self._context_ready
            self._context_ready = True
            self._context = (quest_catalog, achievement_provider, guide_provider)
            if first_context:
                self._applied_journal_evidence_keys.clear()
        self.start_worker()
        if first_context:
            self.request_start_verified_runtime()

    def start_worker(self) -> bool:
        with self._lock:
            if self.is_worker_running:
                return True
            if self._thread is not None and self._thread.is_alive():
                return False
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
                self._stop_event.set()
                self.logger.exception("Network coordinator thread start failed.")
                return False
            return True

    def request_start_calibration(self) -> bool:
        with self._lock:
            if not self._context_ready:
                self._publish_status(NetworkApplicationStatus(False, False, "waiting_context"))
                return False
        if not self.start_worker():
            return False
        self._commands.put("start_calibration")
        return True

    def request_prepare_capture(self) -> bool:
        """Trigger the Windows elevation prompt before catalogue preload."""

        if not self.start_worker():
            return False
        self._commands.put("prepare_capture")
        return True

    def request_start_verified_runtime(self) -> bool:
        with self._lock:
            if not self._context_ready:
                return False
        if not self.start_worker():
            return False
        self._commands.put("start_runtime")
        return True

    def latest_status(self) -> NetworkApplicationStatus:
        with self._lock:
            return self._last_status

    def drain_statuses(self, limit: int = 50) -> list[NetworkApplicationStatus]:
        rows: list[NetworkApplicationStatus] = []
        for _ in range(max(0, int(limit))):
            try:
                rows.append(self._statuses.get_nowait())
            except Empty:
                break
        return rows

    def drain_results(self, limit: int = 100) -> list[EventApplicationResult]:
        rows: list[EventApplicationResult] = []
        for _ in range(max(0, int(limit))):
            try:
                rows.append(self._results.get_nowait())
            except Empty:
                break
        return rows

    def stop(self, join_timeout: float = 3.0) -> bool:
        self._stop_event.set()
        with self._operation_lock:
            calibration_stopped = bool(self.calibration.stop())
            runtime_stopped = bool(self.runtime.stop())
            capture_stopped = self._close_capture_source()
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
        return calibration_stopped and runtime_stopped and capture_stopped and worker_stopped

    def _run(self) -> None:
        try:
            self._publish_current("context_ready")
            while not self._stop_event.is_set():
                command = None
                try:
                    command = self._commands.get(timeout=0.15)
                except Empty:
                    pass
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
            with self._operation_lock:
                self.calibration.stop()
                self.runtime.stop()
                self._close_capture_source()
            with self._lock:
                self._calibration_pending = False

    def _close_capture_source(self) -> bool:
        try:
            self._capture_source.close()
        except Exception:
            self.logger.exception("Elevated network capture helper cleanup failed.")
            return False
        return True

    def _handle_command(self, command: str) -> None:
        if command == "prepare_capture":
            self._prepare_capture()
            return
        if command == "start_calibration":
            self._start_calibration()
            return
        if command == "start_runtime":
            self._start_runtime()

    def _prepare_capture(self) -> None:
        """Launch and pause the reusable helper so UAC happens immediately."""

        with self._operation_lock:
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
        self._publish_current("capture_ready_waiting_context")

    def _start_calibration(self) -> None:
        """Start passive exact-build calibration for safe live idz."""

        with self._operation_lock:
            if self.runtime.is_running and not self.runtime.stop():
                self._publish_current("runtime_stop_failed_before_calibration")
                return
            self._last_calibration = self.calibration.start()
        pending = self._last_calibration.reason in _CALIBRATION_PENDING_REASONS
        with self._lock:
            self._calibration_pending = pending
        self._publish_current(self._last_calibration.reason)
        if self._last_calibration.reason == "mapping_already_ready":
            self._start_runtime()

    def _start_runtime(self) -> None:
        with self._operation_lock:
            with self._lock:
                calibration_pending = self._calibration_pending
            if calibration_pending or self.calibration.is_running:
                self._publish_current("calibration_running")
                return
            self._last_runtime = self.runtime.start_if_ready()
        self._publish_current(self._last_runtime.reason)
        if self._last_runtime.reason in _RUNTIME_REASONS_REQUIRING_CALIBRATION:
            self._start_calibration()
        elif self._last_runtime.reason == "build_fingerprint_unavailable":
            self._next_runtime_retry_at = monotonic() + 2.5

    def _retry_when_client_appears(self) -> None:
        with self._lock:
            ready = self._context_ready
            pending = self._calibration_pending
        if not ready or pending or self.runtime.is_running or self.calibration.is_running:
            return
        if self._last_runtime.reason != "build_fingerprint_unavailable":
            return
        if monotonic() < self._next_runtime_retry_at:
            return
        self._next_runtime_retry_at = monotonic() + 2.5
        self._start_runtime()

    def _poll_calibration(self) -> None:
        with self._lock:
            if not self._calibration_pending:
                return
        with self._operation_lock:
            status = self.calibration.poll()
        self._last_calibration = status
        for result in self.calibration.drain_identity_results():
            self._results.put(result)
        self._apply_calibration_journal_evidence()
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
        from app.network.protocol_calibration import QuestJournalCalibrationEvidence

        evidences = tuple(getattr(self.calibration, "verified_journal_evidences", ()) or ())
        if not evidences:
            evidence = getattr(self.calibration, "verified_journal_evidence", None)
            evidences = (evidence,) if evidence is not None else ()
        for evidence in evidences:
            if isinstance(evidence, QuestJournalCalibrationEvidence):
                self._apply_one_calibration_journal_evidence(evidence)

    def _apply_one_calibration_journal_evidence(self, evidence: Any) -> None:
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
        if not identified:
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
        from app.network.events import QuestCompletedEvent

        certificate = getattr(self.calibration, "verified_certificate", None)
        if certificate is None:
            return
        bridge = self._bridge_for_calibration()
        if bridge is None:
            return
        identified, session_id = self._identify_calibration_character(bridge, certificate)
        if not identified:
            return

        # The reviewed journal was already reconciled when exact-build,
        # same-session identity evidence became available. The full certificate
        # adds only independently verified live final-step completions.
        for quest_id in certificate.verified_quest_ids:
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
        for result in self.runtime.drain_results(100):
            reason = str(result.reason or "")
            activates_character = bool(
                result.accepted
                and result.character_key
                and (
                    reason.startswith("character_")
                    or reason.startswith("quest_journal_")
                )
            )
            if result.changed or activates_character:
                self._results.put(result)
        if self._last_runtime.running and not self.runtime.is_running:
            self._last_runtime = self.runtime.status()
            self._publish_current(self._last_runtime.reason)

    def _publish_current(self, reason: str) -> None:
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
            if status == self._last_status:
                return
            self._last_status = status
        self.logger.info("Network status: reason=%s running=%s calibrating=%s",
                         status.reason, status.running, status.calibrating)
        self._statuses.put(status)
