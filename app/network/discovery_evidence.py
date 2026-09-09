from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_EXPECTED_KIND_BY_EVENT = {
    "character_identified": "string",
    "quest_completed": "positive_int",
    "achievement_completed": "positive_int",
}
_EXPECTED_PURPOSE = "protocol_mapping_discovery_evidence_only"
_EXPECTED_CONSENSUS_PURPOSE = "protocol_mapping_discovery_consensus_only"
_EXPECTED_DIRECTION = "server_to_client"
_EXPECTED_PRIVACY = "no_payload_no_scalar_value_no_session_no_address_storage"
_ANKAMA_TYPE_PREFIXES = ("type.ankama.com/", "ankama.com/")


class ProtocolDiscoveryEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryEvidenceCandidate:
    type_url: str
    path: tuple[int, ...]
    kind: str
    supporting_report_count: int
    total_matching_message_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_url": self.type_url,
            "path": list(self.path),
            "kind": self.kind,
            "supporting_report_count": self.supporting_report_count,
            "total_matching_message_count": self.total_matching_message_count,
        }


@dataclass(frozen=True, slots=True)
class ProtocolDiscoveryConsensus:
    build_sha256: str
    event_type: str
    report_count: int
    candidates: tuple[DiscoveryEvidenceCandidate, ...]
    reason: str

    @property
    def unambiguous(self) -> bool:
        return self.reason == "single_consensus_candidate" and len(self.candidates) == 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "purpose": _EXPECTED_CONSENSUS_PURPOSE,
            "authoritative_mapping": False,
            "build_sha256": self.build_sha256,
            "event_type": self.event_type,
            "report_count": self.report_count,
            "reason": self.reason,
            "unambiguous": self.unambiguous,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def build_discovery_consensus(
    reports: Iterable[Mapping[str, Any]],
    *,
    minimum_reports: int = 2,
) -> ProtocolDiscoveryConsensus:
    parsed = tuple(_parse_report(report) for report in reports)
    minimum = max(2, int(minimum_reports))
    if len(parsed) < minimum:
        raise ProtocolDiscoveryEvidenceError(
            f"at least {minimum} discovery reports are required"
        )

    capture_ids = {report["capture_id"] for report in parsed}
    if len(capture_ids) != len(parsed):
        raise ProtocolDiscoveryEvidenceError(
            "discovery reports must come from distinct capture_id values"
        )
    builds = {report["build_sha256"] for report in parsed}
    if len(builds) != 1:
        raise ProtocolDiscoveryEvidenceError("discovery reports use different build_sha256 values")
    events = {report["event_type"] for report in parsed}
    if len(events) != 1:
        raise ProtocolDiscoveryEvidenceError("discovery reports use different event_type values")

    candidate_sets = [set(report["candidates"]) for report in parsed]
    common = set.intersection(*candidate_sets) if candidate_sets else set()
    rows: list[DiscoveryEvidenceCandidate] = []
    for type_url, path, kind in sorted(common, key=lambda row: (row[0], row[2], row[1])):
        total_matching = 0
        supporting = 0
        for report in parsed:
            count = report["candidate_counts"].get((type_url, path, kind), 0)
            if count > 0:
                supporting += 1
                total_matching += count
        rows.append(
            DiscoveryEvidenceCandidate(
                type_url=type_url,
                path=path,
                kind=kind,
                supporting_report_count=supporting,
                total_matching_message_count=total_matching,
            )
        )

    reason = _reason_for_candidate_count(len(rows))
    return ProtocolDiscoveryConsensus(
        build_sha256=next(iter(builds)),
        event_type=next(iter(events)),
        report_count=len(parsed),
        candidates=tuple(rows),
        reason=reason,
    )


def parse_discovery_consensus(raw: Mapping[str, Any]) -> ProtocolDiscoveryConsensus:
    """Strictly parse a serialized consensus artifact for later mapping audit."""

    if not isinstance(raw, Mapping):
        raise ProtocolDiscoveryEvidenceError("discovery consensus must be an object")
    if raw.get("schema_version") != 1:
        raise ProtocolDiscoveryEvidenceError("unsupported discovery consensus schema_version")
    if str(raw.get("purpose") or "").strip() != _EXPECTED_CONSENSUS_PURPOSE:
        raise ProtocolDiscoveryEvidenceError("unexpected discovery consensus purpose")
    if raw.get("authoritative_mapping") is not False:
        raise ProtocolDiscoveryEvidenceError("discovery consensus must remain non-authoritative")

    build_sha256 = str(raw.get("build_sha256") or "").strip().casefold()
    if not _is_sha256(build_sha256):
        raise ProtocolDiscoveryEvidenceError("invalid discovery consensus build_sha256")
    event_type = str(raw.get("event_type") or "").strip().casefold()
    expected_kind = _EXPECTED_KIND_BY_EVENT.get(event_type)
    if expected_kind is None:
        raise ProtocolDiscoveryEvidenceError(f"unsupported discovery consensus event_type: {event_type!r}")
    report_count = _positive_int(raw.get("report_count"), "report_count")
    if report_count < 2:
        raise ProtocolDiscoveryEvidenceError("discovery consensus requires at least two reports")

    raw_candidates = raw.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ProtocolDiscoveryEvidenceError("discovery consensus candidates must be a list")
    declared_count = _non_negative_int(raw.get("candidate_count"), "candidate_count")
    if declared_count != len(raw_candidates):
        raise ProtocolDiscoveryEvidenceError("discovery consensus candidate_count is inconsistent")

    rows: list[DiscoveryEvidenceCandidate] = []
    seen: set[tuple[str, tuple[int, ...], str]] = set()
    for candidate in raw_candidates:
        if not isinstance(candidate, Mapping):
            raise ProtocolDiscoveryEvidenceError("discovery consensus candidate must be an object")
        type_url = _type_url(candidate.get("type_url"), "discovery consensus candidate")
        kind = str(candidate.get("kind") or "").strip()
        if kind != expected_kind:
            raise ProtocolDiscoveryEvidenceError(
                f"discovery consensus event {event_type!r} requires candidate kind {expected_kind!r}"
            )
        path = _path(candidate.get("path"), "discovery consensus candidate path")
        supporting = _positive_int(candidate.get("supporting_report_count"), "supporting_report_count")
        total_matching = _positive_int(
            candidate.get("total_matching_message_count"),
            "total_matching_message_count",
        )
        if supporting != report_count:
            raise ProtocolDiscoveryEvidenceError(
                "consensus candidate must be supported by every source report"
            )
        if total_matching < supporting:
            raise ProtocolDiscoveryEvidenceError(
                "total_matching_message_count cannot be lower than supporting_report_count"
            )
        key = (type_url, path, kind)
        if key in seen:
            raise ProtocolDiscoveryEvidenceError("duplicate discovery consensus candidate")
        seen.add(key)
        rows.append(
            DiscoveryEvidenceCandidate(
                type_url=type_url,
                path=path,
                kind=kind,
                supporting_report_count=supporting,
                total_matching_message_count=total_matching,
            )
        )

    expected_reason = _reason_for_candidate_count(len(rows))
    reason = str(raw.get("reason") or "").strip()
    if reason != expected_reason:
        raise ProtocolDiscoveryEvidenceError("discovery consensus reason is inconsistent")
    unambiguous = raw.get("unambiguous")
    if not isinstance(unambiguous, bool) or unambiguous != (expected_reason == "single_consensus_candidate"):
        raise ProtocolDiscoveryEvidenceError("discovery consensus unambiguous flag is inconsistent")

    return ProtocolDiscoveryConsensus(
        build_sha256=build_sha256,
        event_type=event_type,
        report_count=report_count,
        candidates=tuple(rows),
        reason=reason,
    )


def _parse_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise ProtocolDiscoveryEvidenceError("discovery report must be an object")
    if report.get("schema_version") != 1:
        raise ProtocolDiscoveryEvidenceError("unsupported discovery report schema_version")
    if str(report.get("purpose") or "").strip() != _EXPECTED_PURPOSE:
        raise ProtocolDiscoveryEvidenceError("unexpected discovery report purpose")
    if report.get("authoritative_mapping") is not False:
        raise ProtocolDiscoveryEvidenceError("discovery evidence must not claim authoritative mapping")
    if str(report.get("privacy") or "").strip() != _EXPECTED_PRIVACY:
        raise ProtocolDiscoveryEvidenceError("unexpected discovery report privacy contract")
    if str(report.get("direction") or "").strip().casefold() != _EXPECTED_DIRECTION:
        raise ProtocolDiscoveryEvidenceError("discovery evidence must be server_to_client only")

    capture_id = str(report.get("capture_id") or "").strip().casefold()
    if not _is_capture_id(capture_id):
        raise ProtocolDiscoveryEvidenceError("invalid discovery report capture_id")
    build_sha256 = str(report.get("build_sha256") or "").strip().casefold()
    if not _is_sha256(build_sha256):
        raise ProtocolDiscoveryEvidenceError("invalid discovery report build_sha256")
    event_type = str(report.get("event_type") or "").strip().casefold()
    expected_kind = _EXPECTED_KIND_BY_EVENT.get(event_type)
    if expected_kind is None:
        raise ProtocolDiscoveryEvidenceError(f"unsupported discovery event_type: {event_type!r}")
    if _non_negative_int(report.get("dropped_candidate_count"), "dropped_candidate_count") != 0:
        raise ProtocolDiscoveryEvidenceError("incomplete discovery report dropped candidate paths")

    raw_candidates = report.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ProtocolDiscoveryEvidenceError("discovery report candidates must be a list")
    declared_count = _non_negative_int(report.get("candidate_count"), "candidate_count")
    if declared_count != len(raw_candidates):
        raise ProtocolDiscoveryEvidenceError("discovery report candidate_count is inconsistent")

    candidates: set[tuple[str, tuple[int, ...], str]] = set()
    candidate_counts: dict[tuple[str, tuple[int, ...], str], int] = {}
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            raise ProtocolDiscoveryEvidenceError("discovery candidate must be an object")
        type_url = _type_url(raw.get("type_url"), "discovery candidate")
        kind = str(raw.get("kind") or "").strip()
        if kind != expected_kind:
            raise ProtocolDiscoveryEvidenceError(
                f"discovery event {event_type!r} requires candidate kind {expected_kind!r}"
            )
        path = _path(raw.get("path"), "candidate path")
        count = _positive_int(raw.get("matching_message_count"), "matching_message_count")
        key = (type_url, path, kind)
        if key in candidates:
            raise ProtocolDiscoveryEvidenceError("duplicate discovery candidate")
        candidates.add(key)
        candidate_counts[key] = count

    return {
        "capture_id": capture_id,
        "build_sha256": build_sha256,
        "event_type": event_type,
        "candidates": frozenset(candidates),
        "candidate_counts": candidate_counts,
    }


def _reason_for_candidate_count(count: int) -> str:
    if count <= 0:
        return "no_consensus_candidate"
    if count == 1:
        return "single_consensus_candidate"
    return "ambiguous_consensus_candidates"


def _type_url(value: object, label: str) -> str:
    type_url = str(value or "").strip()
    if not any(
        type_url.startswith(prefix) and len(type_url) > len(prefix)
        for prefix in _ANKAMA_TYPE_PREFIXES
    ):
        raise ProtocolDiscoveryEvidenceError(f"invalid {label} type_url")
    return type_url


def _path(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ProtocolDiscoveryEvidenceError(f"{label} must be a non-empty list")
    return tuple(_positive_int(field_number, label) for field_number in value)


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProtocolDiscoveryEvidenceError(f"{label} must contain positive integers")
    return int(value)


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProtocolDiscoveryEvidenceError(f"{label} must be a non-negative integer")
    return int(value)


def _is_capture_id(value: str) -> bool:
    if len(value) != 32:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = [
    "DiscoveryEvidenceCandidate",
    "ProtocolDiscoveryConsensus",
    "ProtocolDiscoveryEvidenceError",
    "build_discovery_consensus",
    "parse_discovery_consensus",
]
