from __future__ import annotations

import json
from pathlib import Path

from app.network.contracts import (
    DEFAULT_PROTOCOL_MAPPING_DIR,
    runtime_capabilities_ready,
)
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL,
    dofus_361010_candidate_manifest,
    dofus_361010_candidate_mapping_payload,
    dofus_361010_profile_digest,
)
from app.network.mapping_install import ProtocolMappingInstallResult
from app.network.mapping_manifest import ProtocolMappingError, ProtocolMappingManifest
from app.network.mapping_registry import ProtocolMappingRegistry
from app.network.protocol_calibration import (
    ProtocolCalibrationCertificate,
    ProtocolCalibrationStatus,
)


def install_calibrated_current_profile(
    calibration: ProtocolCalibrationStatus,
    *,
    destination_root: str | Path = DEFAULT_PROTOCOL_MAPPING_DIR,
) -> ProtocolMappingInstallResult:
    """Install the reviewed idz live profile after causal runtime proof.

    No capture is opened and no progression is mutated here. The volatile
    certificate must prove character identity, two independent live idz events
    that reached the final local step of their quests, and at least one strictly
    decoded idr journal observation on the same exact-build transport session.
    The idr observation is calibration-only evidence: its historical mapping is
    never persisted into the authoritative runtime decoder.

    Exact mappings created by older Atlas lqn/snapshot/idr implementations are
    recognized only to be atomically replaced; none of those legacy rules is
    accepted as current business evidence. Arbitrary/custom mappings remain
    protected from overwrite.
    """

    certificate = calibration.certificate
    if not calibration.ready or calibration.reason != "profile_calibrated" or certificate is None:
        return ProtocolMappingInstallResult(False, False, "calibration_not_ready")

    reason = _certificate_error(certificate)
    if reason:
        return ProtocolMappingInstallResult(
            False,
            False,
            reason,
            build_sha256=str(certificate.build_sha256 or "").strip().casefold(),
        )
    if str(calibration.build_sha256 or "").strip().casefold() != certificate.build_sha256:
        return ProtocolMappingInstallResult(
            False,
            False,
            "calibration_build_mismatch",
            build_sha256=certificate.build_sha256,
        )

    try:
        payload = dofus_361010_candidate_mapping_payload(certificate.build_sha256)
        manifest = dofus_361010_candidate_manifest(certificate.build_sha256)
        historical_full_manifest = dofus_361010_candidate_manifest(
            certificate.build_sha256,
            include_quest_journal=True,
        )
    except ValueError:
        return ProtocolMappingInstallResult(
            False,
            False,
            "calibration_rule_invalid",
            build_sha256=certificate.build_sha256,
        )
    if not runtime_capabilities_ready(manifest.provided_event_types):
        return ProtocolMappingInstallResult(
            False,
            False,
            "candidate_missing_runtime_capabilities",
            build_sha256=certificate.build_sha256,
        )
    candidate_bytes = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    root = Path(destination_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProtocolMappingError(f"cannot create protocol mapping directory: {root}") from exc

    registry = ProtocolMappingRegistry((root,))
    existing = registry.select(certificate.build_sha256)
    destination: Path
    previous_bytes: bytes | None = None
    if existing.usable and existing.manifest is not None and len(existing.matched_paths) == 1:
        existing_path = existing.matched_paths[0]
        if existing.manifest == manifest:
            return ProtocolMappingInstallResult(
                True,
                False,
                "mapping_already_installed",
                build_sha256=certificate.build_sha256,
                destination=existing_path,
            )
        if (
            existing.manifest != historical_full_manifest
            and not _is_known_legacy_lqn_mapping(existing.manifest, manifest)
        ):
            return ProtocolMappingInstallResult(
                False,
                False,
                "different_mapping_already_installed",
                build_sha256=certificate.build_sha256,
                destination=existing_path,
            )
        # Downgrade either Atlas's former idz+idr mapping or an exact legacy
        # lqn[/snapshot][/idr] mapping in place, avoiding a second exact-build
        # file and the ambiguity that would create.
        destination = existing_path
        try:
            previous_bytes = destination.read_bytes()
        except OSError as exc:
            raise ProtocolMappingError(
                f"cannot read canonical mapping before upgrade: {destination}"
            ) from exc
    elif existing.reason == "ambiguous_exact_match":
        return ProtocolMappingInstallResult(
            False,
            False,
            "existing_mapping_ambiguous",
            build_sha256=certificate.build_sha256,
        )
    else:
        destination = root / f"mapping_{certificate.build_sha256[:16]}.json"
        if destination.exists():
            return ProtocolMappingInstallResult(
                False,
                False,
                "destination_exists_unselected",
                build_sha256=certificate.build_sha256,
                destination=destination,
            )

    temporary = destination.with_name(destination.name + ".tmp")
    installed = False
    try:
        temporary.write_bytes(candidate_bytes)
        temporary.replace(destination)
        installed = True

        selected = registry.select(certificate.build_sha256)
        if (
            not selected.usable
            or selected.manifest is None
            or len(selected.matched_paths) != 1
            or selected.matched_paths[0] != destination
            or selected.manifest != manifest
            or not runtime_capabilities_ready(selected.manifest.provided_event_types)
        ):
            _rollback(destination, "post-install verification", previous_bytes=previous_bytes)
            installed = False
            return ProtocolMappingInstallResult(
                False,
                False,
                "post_install_selection_failed",
                build_sha256=certificate.build_sha256,
                destination=destination,
            )
    except OSError as exc:
        if installed:
            try:
                _rollback(destination, "install I/O failure", previous_bytes=previous_bytes)
            except ProtocolMappingError as rollback_exc:
                raise ProtocolMappingError(
                    f"calibrated protocol mapping install failed and rollback failed: {destination}"
                ) from rollback_exc
        raise ProtocolMappingError(f"cannot install calibrated protocol mapping: {destination}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    return ProtocolMappingInstallResult(
        True,
        True,
        "mapping_installed_not_started",
        build_sha256=certificate.build_sha256,
        destination=destination,
    )


def _is_known_legacy_lqn_mapping(
    existing: ProtocolMappingManifest,
    current_live: ProtocolMappingManifest,
) -> bool:
    """Recognize only Atlas's exact disproved legacy mapping for replacement.

    Old Atlas builds could persist the lqn message-56 completion rule alone or
    beside the historical shape-only finished snapshot. The snapshot alias was
    discovered, not authoritative, so its exact generated field contract is
    migration baggage: it may be removed only when every other part also matches
    the old Atlas mapping. A custom alias/shape never qualifies.
    """

    completion = existing.quest_completion_info
    if completion is None or completion.type_url != LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL:
        return False
    if (
        completion.message_type_field != 1
        or completion.completion_message_type != 0
        or completion.message_id_field != 2
        or completion.completion_message_id != 56
        or completion.parameters_field != 4
        or completion.quest_id_parameter_index != 0
    ):
        return False
    if existing.game_version != DOFUS_361010_PROFILE.game_version:
        return False
    if existing.build_sha256 != current_live.build_sha256:
        return False
    if existing.character_identity != current_live.character_identity:
        return False
    if existing.rules:
        return False
    if not _is_known_legacy_snapshot(existing):
        return False

    journal = existing.quest_journal_snapshot
    if journal is not None:
        current_full = dofus_361010_candidate_manifest(
            existing.build_sha256,
            include_quest_journal=True,
        )
        if journal != current_full.quest_journal_snapshot:
            return False
    return True


def _is_known_legacy_snapshot(existing: ProtocolMappingManifest) -> bool:
    """Accept no snapshot or exactly the old Atlas generated snapshot shape."""

    snapshot = existing.finished_quests_snapshot
    if snapshot is None:
        return True
    type_url = str(snapshot.type_url or "").strip()
    prefix = "type.ankama.com/"
    alias = type_url[len(prefix) :] if type_url.startswith(prefix) else ""
    if len(alias) != 3 or not alias.isascii() or not alias.isalpha() or not alias.islower():
        return False
    if type_url in {
        DOFUS_361010_PROFILE.character_roster_type_url,
        DOFUS_361010_PROFILE.character_selected_type_url,
        DOFUS_361010_PROFILE.quest_step_validated_type_url,
        DOFUS_361010_PROFILE.quest_journal_type_url,
        LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL,
    }:
        return False
    return (
        int(snapshot.finished_entry_field) == 1
        and tuple(snapshot.quest_id_path_from_entry) == (1,)
        and int(snapshot.player_id_field or 0) == 4
    )


def _certificate_error(certificate: ProtocolCalibrationCertificate) -> str:
    if certificate.game_version != DOFUS_361010_PROFILE.game_version:
        return "calibration_version_mismatch"
    if certificate.evidence_revision != DOFUS_361010_PROFILE.evidence_revision:
        return "calibration_evidence_revision_mismatch"
    if certificate.source_commit != DOFUS_361010_PROFILE.source_commit:
        return "calibration_source_revision_mismatch"
    if certificate.profile_digest != dofus_361010_profile_digest():
        return "calibration_profile_digest_mismatch"
    if not _is_sha256(certificate.build_sha256):
        return "calibration_invalid_build"
    character_id = _positive_int(certificate.character_id)
    if character_id is None:
        return "calibration_invalid_character_id"
    if _character_id_from_key(certificate.character_key) != character_id:
        return "calibration_invalid_character_key"
    quest_ids = tuple(certificate.verified_quest_ids)
    if len(quest_ids) < 2 or len(set(quest_ids)) != len(quest_ids):
        return "calibration_insufficient_distinct_quests"
    if any(_positive_int(quest_id) is None for quest_id in quest_ids):
        return "calibration_invalid_quest_id"

    # A live idr observation remains an independent calibration sanity check,
    # but it authorizes no idr decoder and is never written to the installed
    # runtime mapping.
    journal_type_url = str(certificate.quest_journal_type_url or "").strip()
    if journal_type_url != DOFUS_361010_PROFILE.quest_journal_type_url:
        return "calibration_quest_journal_unverified"
    journal_ids = tuple(certificate.journal_verified_quest_ids)
    if certificate.journal_observation_count < 1:
        return "calibration_quest_journal_unverified"
    if len(journal_ids) != len(set(journal_ids)):
        return "calibration_quest_journal_unverified"
    if any(_positive_int(quest_id) is None for quest_id in journal_ids):
        return "calibration_quest_journal_unverified"

    if (
        str(certificate.finished_quests_snapshot_type_url or "").strip()
        or certificate.snapshot_verified_quest_ids
        or certificate.snapshot_observation_count
    ):
        return "calibration_unverified_snapshot_evidence"
    return ""


def _rollback(
    destination: Path,
    reason: str,
    *,
    previous_bytes: bytes | None = None,
) -> None:
    rollback_temporary = destination.with_name(destination.name + ".rollback.tmp")
    try:
        if previous_bytes is None:
            destination.unlink(missing_ok=True)
        else:
            rollback_temporary.write_bytes(previous_bytes)
            rollback_temporary.replace(destination)
    except OSError as exc:
        raise ProtocolMappingError(
            f"cannot rollback calibrated protocol mapping after {reason}: {destination}"
        ) from exc
    finally:
        try:
            rollback_temporary.unlink(missing_ok=True)
        except OSError:
            pass
    if previous_bytes is None and destination.exists():
        raise ProtocolMappingError(
            f"calibrated mapping still exists after rollback ({reason}): {destination}"
        )
    if previous_bytes is not None:
        try:
            restored = destination.read_bytes()
        except OSError as exc:
            raise ProtocolMappingError(
                f"cannot verify calibrated mapping rollback after {reason}: {destination}"
            ) from exc
        if restored != previous_bytes:
            raise ProtocolMappingError(
                f"calibrated mapping rollback content mismatch ({reason}): {destination}"
            )


def _character_id_from_key(value: object) -> int | None:
    raw = str(value or "").strip().casefold()
    if not raw.startswith("character:"):
        return None
    try:
        character_id = int(raw.split(":", 1)[1])
    except (TypeError, ValueError, OverflowError):
        return None
    return character_id if character_id > 0 else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = ["install_calibrated_current_profile"]
