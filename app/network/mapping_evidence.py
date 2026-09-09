from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.network.contracts import DIRECT_MAPPING_EVIDENCE_EVENTS
from app.network.discovery_evidence import ProtocolDiscoveryConsensus
from app.network.mapping_manifest import ProtocolMappingManifest


_REQUIRED_EVENT_OUTPUT = {
    "character_identified": ("character_name", "string"),
    "quest_completed": ("quest_id", "positive_int"),
    "achievement_completed": ("achievement_id", "positive_int"),
}


@dataclass(frozen=True, slots=True)
class MappingEvidenceValidation:
    valid: bool
    reason: str
    checked_events: tuple[str, ...]
    missing_events: tuple[str, ...] = ()
    mismatched_events: tuple[str, ...] = ()


def validate_mapping_against_consensus(
    manifest: ProtocolMappingManifest,
    consensuses: Iterable[ProtocolDiscoveryConsensus],
    *,
    required_events: Iterable[str] = DIRECT_MAPPING_EVIDENCE_EVENTS,
) -> MappingEvidenceValidation:
    """Check direct singular-field mappings against discovery consensus.

    This validator deliberately does not interpret runtime capabilities or
    specialized decoders. Correlated identity, the current ``lqn`` completion
    profile and finished-quest snapshots have their own evidence paths. Keeping
    the scalar audit narrow prevents a specialized provider from being treated
    as if it had passed a field-path consensus it never produced.
    """

    required = tuple(
        dict.fromkeys(
            str(event or "").strip().casefold()
            for event in required_events
            if str(event or "").strip()
        )
    )
    unsupported = tuple(sorted(event for event in required if event not in _REQUIRED_EVENT_OUTPUT))
    if unsupported:
        return MappingEvidenceValidation(
            valid=False,
            reason="mapping_evidence_unsupported",
            checked_events=(),
            missing_events=unsupported,
        )

    evidence_by_event: dict[str, ProtocolDiscoveryConsensus] = {}
    conflicts: set[str] = set()

    for consensus in consensuses:
        event_type = str(consensus.event_type or "").strip().casefold()
        if event_type not in _REQUIRED_EVENT_OUTPUT:
            continue
        if not consensus.unambiguous or len(consensus.candidates) != 1:
            conflicts.add(event_type)
            continue
        if str(consensus.build_sha256 or "").strip().casefold() != manifest.build_sha256:
            conflicts.add(event_type)
            continue
        previous = evidence_by_event.get(event_type)
        if previous is not None and previous.candidates[0] != consensus.candidates[0]:
            conflicts.add(event_type)
            continue
        evidence_by_event[event_type] = consensus

    missing = tuple(sorted(event for event in required if event not in evidence_by_event))
    mismatched: set[str] = set(conflicts)

    for event_type, consensus in evidence_by_event.items():
        candidate = consensus.candidates[0]
        rule = manifest.rules.get(candidate.type_url)
        if rule is None or str(rule.event_type).strip().casefold() != event_type:
            mismatched.add(event_type)
            continue
        output_name, expected_kind = _REQUIRED_EVENT_OUTPUT[event_type]
        matching_fields = [
            field
            for field in rule.fields
            if field.output_name == output_name
            and field.required
            and field.kind == expected_kind
            and tuple(field.path) == tuple(candidate.path)
        ]
        if len(matching_fields) != 1:
            mismatched.add(event_type)

    mismatched_tuple = tuple(sorted(mismatched))
    if mismatched_tuple:
        reason = "mapping_evidence_mismatch"
    elif missing:
        reason = "mapping_evidence_missing"
    else:
        reason = "mapping_evidence_match"
    return MappingEvidenceValidation(
        valid=not missing and not mismatched_tuple,
        reason=reason,
        checked_events=tuple(sorted(evidence_by_event)),
        missing_events=missing,
        mismatched_events=mismatched_tuple,
    )


__all__ = ["MappingEvidenceValidation", "validate_mapping_against_consensus"]
