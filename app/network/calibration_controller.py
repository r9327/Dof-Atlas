from __future__ import annotations

import threading
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

from app.core.logger import get_runtime_logger
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.character_resolver import CharacterSlotResolver
from app.network.contracts import DEFAULT_PROTOCOL_MAPPING_DIR
from app.quest_catalog import QuestCatalog

if TYPE_CHECKING:
    from app.network.calibration_bootstrap import ProtocolCalibrationBootstrapResult
    from app.network.calibration_runtime import ProtocolCalibrationRuntime
    from app.network.mapping_install import ProtocolMappingInstallResult
    from app.network.protocol_calibration import ProtocolCalibrationStatus
    from app.network.transport import ProtocolMessageSource


@dataclass(frozen=True, slots=True)
class ProtocolCalibrationControllerStatus:
    running: bool
    reason: str
    build_sha256: str = ""
    distinct_completion_count: int = 0
    quest_journal_observation_count: int = 0
    quest_journal_verified_count: int = 0
    snapshot_candidate_count: int = 0
    snapshot_candidate_type_url: str = ""
    installed: bool = False
    mapping_path: Path | None = None


class ProtocolCalibrationController:
    """Own explicit in-app calibration without touching progression."""

    def __init__(
        self,
        window_handles_provider: Callable[[], Iterable[int]],
        *,
        mapping_roots: Iterable[str | Path] | None = None,
        destination_root: str | Path = DEFAULT_PROTOCOL_MAPPING_DIR,
        protocol_source: ProtocolMessageSource | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.window_handles_provider = window_handles_provider
        self.mapping_roots = tuple(mapping_roots) if mapping_roots is not None else None
        self.destination_root = Path(destination_root)
        self.protocol_source = protocol_source
        self.logger = logger or get_runtime_logger()
        self._fingerprint_provider = ActiveProtocolBuildFingerprintProvider(window_handles_provider)
        self._lock = threading.RLock()
        self._quest_catalog: QuestCatalog | None = None
        self._character_resolver: CharacterSlotResolver | None = None
        self._runtime: ProtocolCalibrationRuntime | None = None
        self._last_bootstrap: ProtocolCalibrationBootstrapResult | None = None
        self._last_calibration_status: ProtocolCalibrationStatus | None = None
        self._install_result: ProtocolMappingInstallResult | None = None
        self._last_reason = "waiting_context"
        self._identity_results: list = []

    @property
    def is_running(self) -> bool:
        with self._lock:
            runtime = self._runtime
        return bool(runtime is not None and runtime.is_running)

    @property
    def verified_certificate(self):
        with self._lock:
            status = self._last_calibration_status
        return status.certificate if status is not None and status.ready else None

    @property
    def verified_journal_evidence(self):
        """Return reviewed idr evidence even while live idz remains calibrating."""

        with self._lock:
            status = self._last_calibration_status
        return status.journal_evidence if status is not None else None

    @property
    def verified_journal_evidences(self):
        """Return reviewed journal evidence for all identified sessions."""

        with self._lock:
            status = self._last_calibration_status
        if status is None:
            return ()
        evidences = tuple(getattr(status, "journal_evidences", ()) or ())
        if evidences:
            return evidences
        evidence = getattr(status, "journal_evidence", None)
        return (evidence,) if evidence is not None else ()

    def configure_context(
        self,
        *,
        quest_catalog: QuestCatalog,
        character_resolver: CharacterSlotResolver | None = None,
    ) -> None:
        if not isinstance(quest_catalog, QuestCatalog):
            raise TypeError("quest_catalog must be a QuestCatalog")
        with self._lock:
            self._quest_catalog = quest_catalog
            self._character_resolver = character_resolver
            if self._last_reason == "waiting_context":
                self._last_reason = "context_ready"

    def start(self) -> ProtocolCalibrationControllerStatus:
        with self._lock:
            runtime = self._runtime
            quest_catalog = self._quest_catalog
            resolver = self._character_resolver
        if runtime is not None and runtime.is_running:
            return self.status("calibrating")
        if quest_catalog is None:
            with self._lock:
                self._last_reason = "waiting_context"
            return self.status("waiting_context")

        if runtime is not None:
            if not runtime.stop():
                with self._lock:
                    self._last_reason = "stale_calibration_stop_failed"
                return self.status("stale_calibration_stop_failed")
            with self._lock:
                if self._runtime is runtime:
                    self._runtime = None

        # Calibration composition imports raw capture/protobuf/runtime modules.
        # Home imports this controller before the splash; defer that stack until
        # a configured calibration actually starts on the coordinator worker.
        from app.network.calibration_bootstrap import build_windows_protocol_calibration

        bootstrap = build_windows_protocol_calibration(
            window_handles_provider=self.window_handles_provider,
            quest_catalog=quest_catalog,
            mapping_roots=self.mapping_roots,
            character_resolver=resolver,
            build_sha256_provider=self._fingerprint_provider,
            protocol_source=self.protocol_source,
            logger=self.logger,
        )
        with self._lock:
            self._last_bootstrap = bootstrap
            self._last_calibration_status = None
            self._install_result = None
            self._last_reason = bootstrap.reason

        if bootstrap.reason == "mapping_already_ready":
            return self.status("mapping_already_ready")
        if not bootstrap.ready or bootstrap.runtime is None:
            return self.status(bootstrap.reason)

        candidate = bootstrap.runtime
        if not candidate.start():
            start_reason = str(
                getattr(candidate, "start_failure_reason", "")
                or "calibration_start_failed"
            )
            cleanup_ok = candidate.stop()
            resolved_reason = (
                "calibration_start_cleanup_failed" if not cleanup_ok else start_reason
            )
            with self._lock:
                if not cleanup_ok:
                    self._runtime = candidate
                self._last_reason = resolved_reason
            return self.status(resolved_reason)

        with self._lock:
            self._runtime = candidate
            self._last_reason = "calibrating"
        return self.status("calibrating")

    def poll(self) -> ProtocolCalibrationControllerStatus:
        """Drain calibration transitions and install once a certificate is ready."""

        with self._lock:
            runtime = self._runtime
            existing_install = self._install_result
            last_reason = self._last_reason
        if runtime is None:
            return self.status(last_reason)

        statuses = runtime.drain_statuses(100)
        self._identity_results.extend(runtime.drain_identity_results())
        latest = statuses[-1] if statuses else runtime.latest_status
        with self._lock:
            self._last_calibration_status = latest

        if latest.reason in {"build_changed", "quest_snapshot_ambiguous", "quest_snapshot_missed", "capture_helper_disconnected"}:
            stopped = bool(runtime.stop())
            resolved = latest.reason if stopped else "calibration_stop_failed"
            with self._lock:
                if stopped and self._runtime is runtime:
                    self._runtime = None
                self._last_reason = resolved
            return self.status(resolved)

        if latest.ready and existing_install is None:
            if not runtime.stop():
                with self._lock:
                    self._last_reason = "calibration_stop_failed_before_install"
                return self.status("calibration_stop_failed_before_install")
            with self._lock:
                if self._runtime is runtime:
                    self._runtime = None
            try:
                from app.network.calibrated_mapping_install import (
                    install_calibrated_current_profile,
                )

                result = install_calibrated_current_profile(
                    latest,
                    destination_root=self.destination_root,
                )
            except Exception:
                self.logger.exception("Calibrated protocol mapping installation failed.")
                with self._lock:
                    self._last_reason = "calibration_install_error"
                return self.status("calibration_install_error")
            with self._lock:
                self._install_result = result
                self._last_reason = result.reason
            return self.status(result.reason)

        if latest.ready and existing_install is not None:
            return self.status(existing_install.reason)
        if latest.reason in {
            "awaiting_character_identity",
            "awaiting_distinct_quest_completions",
            "awaiting_quest_journal",
        }:
            with self._lock:
                self._last_reason = latest.reason
            return self.status(latest.reason)
        return self.status("calibrating")

    def drain_identity_results(self) -> list:
        results, self._identity_results = self._identity_results, []
        return results

    def stop(self) -> bool:
        with self._lock:
            runtime = self._runtime
        if runtime is None:
            with self._lock:
                self._last_reason = "stopped"
            return True
        stopped = bool(runtime.stop())
        with self._lock:
            if stopped and self._runtime is runtime:
                self._runtime = None
                self._last_reason = "stopped"
            elif not stopped:
                self._last_reason = "calibration_stop_failed"
        return stopped

    def status(self, reason: str | None = None) -> ProtocolCalibrationControllerStatus:
        with self._lock:
            runtime = self._runtime
            bootstrap = self._last_bootstrap
            calibration = self._last_calibration_status
            install = self._install_result
            resolved_reason = str(reason if reason is not None else self._last_reason)
        build_sha256 = ""
        mapping_path = None
        if bootstrap is not None:
            build_sha256 = str(bootstrap.build_sha256 or "")
            mapping_path = bootstrap.existing_mapping_path
        if install is not None:
            build_sha256 = str(install.build_sha256 or build_sha256)
            mapping_path = install.destination or mapping_path
        return ProtocolCalibrationControllerStatus(
            running=bool(runtime is not None and runtime.is_running),
            reason=resolved_reason,
            build_sha256=build_sha256,
            distinct_completion_count=(
                int(calibration.max_distinct_completion_count)
                if calibration is not None
                else 0
            ),
            quest_journal_observation_count=(
                int(calibration.quest_journal_observation_count)
                if calibration is not None
                else 0
            ),
            quest_journal_verified_count=(
                int(calibration.quest_journal_verified_count)
                if calibration is not None
                else 0
            ),
            snapshot_candidate_count=(
                int(calibration.snapshot_candidate_count)
                if calibration is not None
                else 0
            ),
            snapshot_candidate_type_url=(
                str(calibration.snapshot_candidate_type_url or "")
                if calibration is not None
                else ""
            ),
            installed=bool(install is not None and install.success),
            mapping_path=mapping_path,
        )


__all__ = [
    "ProtocolCalibrationController",
    "ProtocolCalibrationControllerStatus",
]

