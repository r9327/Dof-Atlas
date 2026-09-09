from __future__ import annotations

from dataclasses import dataclass, replace
from logging import Logger
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable

from app.constants import QUEST_PROGRESS_FILE
from app.core.logger import get_runtime_logger
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    ACHIEVEMENT_PROGRESS_FILE,
    AchievementProgressService,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.character_resolver import CharacterSlotResolver
from app.network.character_runtime_decoder import CharacterRuntimeProtocolMessageDecoder
from app.network.contracts import (
    DEFAULT_PROTOCOL_MAPPING_DIR,
    REQUIRED_RUNTIME_EVENTS,
    missing_runtime_capabilities,
)
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL,
    dofus_361010_candidate_manifest,
)
from app.network.instrumentation import (
    DiagnosticProtocolMessageDecoder,
    InstrumentedNetworkProgressBridge,
)
from app.network.known_session_recovery import (
    KnownSessionProgressBridge,
    KnownSessionProtocolMessageDecoder,
    VerifiedKnownSessionRecovery,
)
from app.network.mapping_registry import ProtocolMappingRegistry, ProtocolMappingSelection
from app.network.quest_final_step_filter import FinalQuestStepEvidenceDecoder
from app.network.request_response_diagnostics import DiagnosticProtocolMessageSource
from app.network.runtime import NetworkEventRuntime
from app.network.elevated_capture import ElevatedWindowsProtocolSource
from app.network.transport import DecodedNetworkEventSource, ProtocolMessageSource
from app.quest_catalog import QuestCatalog


@dataclass(frozen=True, slots=True)
class NetworkBootstrapResult:
    runtime: NetworkEventRuntime | None
    reason: str
    build_sha256: str = ""
    mapping_path: Path | None = None
    invalid_mapping_paths: tuple[Path, ...] = ()
    missing_required_events: tuple[str, ...] = ()
    catchup_ready: bool = False

    @property
    def ready(self) -> bool:
        return self.runtime is not None and self.reason == "ready"


def build_windows_network_runtime(
    *,
    window_handles_provider: Callable[[], Iterable[int]],
    quest_catalog: QuestCatalog,
    achievement_provider: Any,
    guide_provider: Any = None,
    mapping_roots: Iterable[str | Path] | None = None,
    quest_progress_service: QuestProgressService | None = None,
    achievement_progress_service: AchievementProgressService | None = None,
    character_resolver: CharacterSlotResolver | None = None,
    build_sha256_provider: Callable[[], str | None] | None = None,
    protocol_source: ProtocolMessageSource | None = None,
    logger: Logger | None = None,
) -> NetworkBootstrapResult:
    """Compose, but do not start, the trusted Windows network runtime.

    Current live completion uses reviewed idz step validation and a second local
    proof that the validated step is exactly the quest's final ordered step.
    Historical idr rules are fail-closed at runtime: they may remain in an old
    exact-build manifest for migration/diagnostics, but are stripped before
    capability checks and before any decoder is built, whether they were stored
    as the old specialized journal rule or as a generic message rule.

    Client-to-server messages remain available only through the passive bounded
    diagnostic source. They can be temporally correlated with later server
    messages for logs, but the transport direction guard still prevents them
    from reaching the business normalizer.

    For the reviewed 3.6.10.10 profile, capability labels are not enough: after
    stripping legacy unsafe rules, the manifest must equal Atlas's canonical
    kvi/kva + idz live mapping. This stops a custom or stale quest_completed
    decoder from inheriting current-profile trust merely because it exposes the
    same abstract event name.
    """

    log = logger or get_runtime_logger()
    fingerprint_provider = build_sha256_provider or ActiveProtocolBuildFingerprintProvider(
        window_handles_provider
    )
    try:
        build_sha256 = str(fingerprint_provider() or "").strip().casefold()
    except Exception:
        log.exception("Network build fingerprint lookup failed.")
        return NetworkBootstrapResult(None, "build_fingerprint_error")
    if not _is_sha256(build_sha256):
        return NetworkBootstrapResult(None, "build_fingerprint_unavailable")

    registry = ProtocolMappingRegistry(
        tuple(mapping_roots) if mapping_roots is not None else (DEFAULT_PROTOCOL_MAPPING_DIR,)
    )
    selection = registry.select(build_sha256)
    if not selection.usable or selection.manifest is None:
        return _disabled_selection(build_sha256, selection)

    manifest = selection.manifest
    is_current_profile = manifest.game_version == DOFUS_361010_PROFILE.game_version
    historical_idr = DOFUS_361010_PROFILE.quest_journal_type_url

    # The historical ``idr`` alias is never authoritative business input,
    # regardless of which old manifest/version happens to contain it. Keep the
    # on-disk rows as migration/diagnostic evidence only; strip both the old
    # specialized journal rule and any generic rule using the same type URL.
    journal = manifest.quest_journal_snapshot
    if journal is not None and str(journal.type_url or "").strip() == historical_idr:
        manifest = replace(manifest, quest_journal_snapshot=None)
    if historical_idr in manifest.rules:
        safe_rules = dict(manifest.rules)
        safe_rules.pop(historical_idr, None)
        manifest = replace(manifest, rules=MappingProxyType(safe_rules))

    if is_current_profile:
        # Historical shape-only finished snapshots are likewise non-authoritative
        # for the reviewed current profile.
        manifest = replace(manifest, finished_quests_snapshot=None)
    completion_info = manifest.quest_completion_info
    if (
        is_current_profile
        and completion_info is not None
        and completion_info.type_url == LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL
    ):
        manifest = replace(manifest, quest_completion_info=None)

    provided_events = manifest.provided_event_types
    catchup_ready = "quest_journal_snapshot" in provided_events
    missing_required_events = missing_runtime_capabilities(provided_events)
    if missing_required_events:
        return NetworkBootstrapResult(
            None,
            "mapping_missing_required_events",
            build_sha256=build_sha256,
            mapping_path=selection.matched_paths[0],
            invalid_mapping_paths=selection.invalid_paths,
            missing_required_events=missing_required_events,
            catchup_ready=catchup_ready,
        )

    if is_current_profile:
        canonical_live = dofus_361010_candidate_manifest(build_sha256)
        if manifest != canonical_live:
            return NetworkBootstrapResult(
                None,
                "mapping_current_profile_noncanonical",
                build_sha256=build_sha256,
                mapping_path=selection.matched_paths[0],
                invalid_mapping_paths=selection.invalid_paths,
                catchup_ready=catchup_ready,
            )

    # Success points are static catalogue data, not a second progress source.
    # Build this small index in normal runtime too because a verified Npcap
    # AchievementsEvent contains IDs, while the score itself is the sum of the
    # canonical point values already owned by AchievementProvider.
    try:
        achievement_points_by_id = {
            int(achievement.id): max(0, int(achievement.points))
            for achievement in achievement_provider.load_all()
            if int(achievement.id) > 0
        }
    except Exception:
        # Failure to build the optional profile index must never disable the
        # already-verified identity/quest runtime. It only means points stay
        # unavailable until the catalogue can be loaded successfully.
        log.exception("Achievement point index unavailable for character network profile.")
        achievement_points_by_id = {}

    effective_character_resolver = character_resolver or CharacterSlotResolver()
    known_session_recovery = VerifiedKnownSessionRecovery(
        effective_character_resolver,
        logger=log,
    )

    try:
        decoder = manifest.build_decoder(
            active_build_sha256_provider=fingerprint_provider,
        )
        decoder = FinalQuestStepEvidenceDecoder(decoder, quest_catalog)
        decoder = DiagnosticProtocolMessageDecoder(decoder, logger=log)
        decoder = CharacterRuntimeProtocolMessageDecoder(
            decoder,
            achievement_points_by_id=achievement_points_by_id,
            logger=log,
        )
        decoder = KnownSessionProtocolMessageDecoder(
            decoder,
            known_session_recovery,
            logger=log,
        )
        raw_source = (
            protocol_source
            if protocol_source is not None
            else ElevatedWindowsProtocolSource(window_handles_provider, logger=log)
        )
        diagnostic_source = DiagnosticProtocolMessageSource(
            raw_source,
            logger=log,
            phase="runtime",
        )
        source = DecodedNetworkEventSource(diagnostic_source, decoder, logger=log)
        bridge = InstrumentedNetworkProgressBridge(
            quest_catalog=quest_catalog,
            quest_progress_service=quest_progress_service or QuestProgressService(QUEST_PROGRESS_FILE),
            achievement_progress_service=(
                achievement_progress_service or AchievementProgressService(ACHIEVEMENT_PROGRESS_FILE)
            ),
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
            character_resolver=effective_character_resolver,
            logger=log,
        )
        bridge = KnownSessionProgressBridge(bridge, known_session_recovery)
        runtime = NetworkEventRuntime(source, bridge, logger=log)
    except Exception:
        log.exception("Verified network runtime composition failed.")
        return NetworkBootstrapResult(
            None,
            "composition_error",
            build_sha256=build_sha256,
            mapping_path=selection.matched_paths[0] if selection.matched_paths else None,
            invalid_mapping_paths=selection.invalid_paths,
            catchup_ready=catchup_ready,
        )

    return NetworkBootstrapResult(
        runtime,
        "ready",
        build_sha256=build_sha256,
        mapping_path=selection.matched_paths[0],
        invalid_mapping_paths=selection.invalid_paths,
        catchup_ready=catchup_ready,
    )


def _disabled_selection(
    build_sha256: str,
    selection: ProtocolMappingSelection,
) -> NetworkBootstrapResult:
    if selection.reason == "ambiguous_exact_match":
        reason = "mapping_ambiguous_exact_match"
    elif selection.invalid_paths:
        reason = "mapping_invalid"
    else:
        reason = "mapping_no_exact_match"
    return NetworkBootstrapResult(
        None,
        reason,
        build_sha256=build_sha256,
        mapping_path=selection.matched_paths[0] if selection.matched_paths else None,
        invalid_mapping_paths=selection.invalid_paths,
    )


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = [
    "NetworkBootstrapResult",
    "build_windows_network_runtime",
]
