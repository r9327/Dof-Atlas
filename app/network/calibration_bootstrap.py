from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Callable, Iterable

from app.core.logger import get_runtime_logger
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.calibration_runtime import ProtocolCalibrationRuntime
from app.network.character_resolver import CharacterSlotResolver
from app.network.character_runtime_decoder import CharacterRuntimeProtocolMessageDecoder
from app.network.contracts import DEFAULT_PROTOCOL_MAPPING_DIR
from app.network.current_protocol_profile import dofus_361010_candidate_manifest
from app.network.instrumentation import InstrumentedCurrentProtocolCalibration
from app.network.mapping_registry import ProtocolMappingRegistry
from app.network.elevated_capture import ElevatedWindowsProtocolSource
from app.network.request_response_diagnostics import DiagnosticProtocolMessageSource
from app.network.transport import ProtocolMessageSource
from app.quest_catalog import QuestCatalog


@dataclass(frozen=True, slots=True)
class ProtocolCalibrationBootstrapResult:
    runtime: ProtocolCalibrationRuntime | None
    reason: str
    build_sha256: str = ""
    existing_mapping_path: Path | None = None

    @property
    def ready(self) -> bool:
        return self.runtime is not None and self.reason == "ready_to_calibrate"


def build_windows_protocol_calibration(
    *,
    window_handles_provider: Callable[[], Iterable[int]],
    quest_catalog: QuestCatalog,
    mapping_roots: Iterable[str | Path] | None = None,
    character_resolver: CharacterSlotResolver | None = None,
    build_sha256_provider: Callable[[], str | None] | None = None,
    protocol_source: ProtocolMessageSource | None = None,
    logger: Logger | None = None,
) -> ProtocolCalibrationBootstrapResult:
    """Compose, but do not start, the reviewed current-profile calibration.

    Calibration may be skipped only when the one exact-build mapping selected
    from disk equals Atlas's current canonical kvi/kva + final-step idz live
    manifest. Historical idr journal rules are deliberately not part of the
    authoritative runtime mapping and therefore cannot make calibration ready.
    Capability names alone are insufficient: an old lqn mapping or a custom
    quest_completed decoder must not inherit trust merely because it exposes
    the same abstract event labels.

    Outbound traffic is retained only by the bounded passive diagnostic wrapper
    for request/response logs. CurrentProtocolCalibration independently rejects
    client-to-server messages before semantic calibration.
    """

    log = logger or get_runtime_logger()
    fingerprint_provider = build_sha256_provider or ActiveProtocolBuildFingerprintProvider(
        window_handles_provider
    )
    try:
        build_sha256 = str(fingerprint_provider() or "").strip().casefold()
    except Exception:
        log.exception("Protocol calibration build fingerprint lookup failed.")
        return ProtocolCalibrationBootstrapResult(None, "build_fingerprint_error")
    if not _is_sha256(build_sha256):
        return ProtocolCalibrationBootstrapResult(None, "build_fingerprint_unavailable")

    registry = ProtocolMappingRegistry(
        tuple(mapping_roots) if mapping_roots is not None else (DEFAULT_PROTOCOL_MAPPING_DIR,)
    )
    existing = registry.select(build_sha256)
    canonical = dofus_361010_candidate_manifest(build_sha256)
    if (
        existing.usable
        and existing.manifest is not None
        and existing.manifest == canonical
        and len(existing.matched_paths) == 1
    ):
        return ProtocolCalibrationBootstrapResult(
            None,
            "mapping_already_ready",
            build_sha256=build_sha256,
            existing_mapping_path=existing.matched_paths[0],
        )
    if existing.reason == "ambiguous_exact_match":
        return ProtocolCalibrationBootstrapResult(
            None,
            "existing_mapping_ambiguous",
            build_sha256=build_sha256,
        )

    try:
        calibration = InstrumentedCurrentProtocolCalibration(
            build_sha256=build_sha256,
            active_build_sha256_provider=fingerprint_provider,
            quest_catalog=quest_catalog,
            character_resolver=character_resolver,
        )
        calibration.decoder = CharacterRuntimeProtocolMessageDecoder(
            calibration.decoder, logger=log,
        )
        raw_source = (
            protocol_source
            if protocol_source is not None
            else ElevatedWindowsProtocolSource(window_handles_provider, logger=log)
        )
        source = DiagnosticProtocolMessageSource(
            raw_source,
            logger=log,
            phase="calibration",
        )
        runtime = ProtocolCalibrationRuntime(source, calibration, logger=log)
    except Exception:
        log.exception("Protocol calibration composition failed.")
        return ProtocolCalibrationBootstrapResult(
            None,
            "composition_error",
            build_sha256=build_sha256,
        )

    return ProtocolCalibrationBootstrapResult(
        runtime,
        "ready_to_calibrate",
        build_sha256=build_sha256,
    )


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = ["ProtocolCalibrationBootstrapResult", "build_windows_protocol_calibration"]
