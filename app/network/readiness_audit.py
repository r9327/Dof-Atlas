from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from app.network.contracts import DIRECT_MAPPING_EVIDENCE_EVENTS, REQUIRED_RUNTIME_SEMANTICS
from app.network.deobfs_audit import (
    DeobfuscationEvidenceValidation,
    validate_consensus_deobfuscation_reports,
)
from app.network.deobfs_bundle import (
    DeobfuscationEvidenceBundleError,
    load_deobfuscation_evidence_bundle,
    verify_deobfuscation_evidence_bundle,
)
from app.network.deobfs_report import DeobfuscationReportError
from app.network.discovery_evidence import (
    ProtocolDiscoveryEvidenceError,
    ProtocolDiscoveryConsensus,
)
from app.network.mapping_audit import audit_mapping_evidence
from app.network.mapping_evidence import MappingEvidenceValidation
from app.network.mapping_manifest import ProtocolMappingError, ProtocolMappingManifest


DEFAULT_REQUIRED_SEMANTICS: Mapping[str, str] = MappingProxyType(
    {
        event: REQUIRED_RUNTIME_SEMANTICS[event]
        for event in DIRECT_MAPPING_EVIDENCE_EVENTS
        if event in REQUIRED_RUNTIME_SEMANTICS
    }
)


@dataclass(frozen=True, slots=True)
class ProtocolMappingReadinessValidation:
    valid: bool
    reason: str
    mapping_validation: MappingEvidenceValidation
    semantic_validations: tuple[DeobfuscationEvidenceValidation, ...]
    missing_semantic_events: tuple[str, ...] = ()
    invalid_semantic_events: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "purpose": "protocol_mapping_candidate_readiness_audit",
            "authoritative_mapping": False,
            "valid": self.valid,
            "reason": self.reason,
            "mapping_evidence": {
                "valid": self.mapping_validation.valid,
                "reason": self.mapping_validation.reason,
                "checked_events": list(self.mapping_validation.checked_events),
                "missing_events": list(self.mapping_validation.missing_events),
                "mismatched_events": list(self.mapping_validation.mismatched_events),
            },
            "semantic_evidence": [row.to_dict() for row in self.semantic_validations],
            "missing_semantic_events": list(self.missing_semantic_events),
            "invalid_semantic_events": list(self.invalid_semantic_events),
        }


def validate_protocol_mapping_readiness(
    manifest: ProtocolMappingManifest,
    consensuses: Iterable[ProtocolDiscoveryConsensus],
    mapping_validation: MappingEvidenceValidation,
    report_paths: Iterable[str | Path],
    *,
    required_semantics: Mapping[str, str] = DEFAULT_REQUIRED_SEMANTICS,
    minimum_confidence: float = 100.0,
) -> ProtocolMappingReadinessValidation:
    """Combine direct mapping evidence with semantic deobfuscation evidence.

    This is intentionally the legacy/direct evidence path: one semantic event,
    one scalar field path, one deobfuscated clear name. Specialized providers
    such as correlated character identity, the current ``lqn`` quest-completion
    profile and full quest snapshots use dedicated proof paths and must not be
    smuggled through this validator as if they had direct scalar consensus.

    Report paths supplied here are expected to have already been verified against
    an exact-build deobfuscation evidence bundle by the higher-level audit
    function. This validator remains pure and does not install or enable a
    mapping.
    """

    required = {
        str(event or "").strip().casefold(): str(message or "").strip()
        for event, message in required_semantics.items()
        if str(event or "").strip() and str(message or "").strip()
    }
    if not required:
        raise ValueError("required_semantics cannot be empty")
    uncovered_direct_events = tuple(sorted(DIRECT_MAPPING_EVIDENCE_EVENTS - set(required)))
    if uncovered_direct_events:
        raise ValueError(
            "required_semantics does not cover direct mapping evidence events: "
            + ", ".join(uncovered_direct_events)
        )

    rows = tuple(consensuses)
    reports = tuple(Path(path) for path in report_paths)
    if not reports:
        raise ValueError("at least one deobfuscation report is required")

    by_event: dict[str, list[ProtocolDiscoveryConsensus]] = {}
    for consensus in rows:
        event_type = str(consensus.event_type or "").strip().casefold()
        if event_type in required:
            by_event.setdefault(event_type, []).append(consensus)

    semantic_validations: list[DeobfuscationEvidenceValidation] = []
    missing_semantics: list[str] = []
    invalid_semantics: set[str] = set()

    for event_type, expected_message in required.items():
        event_consensuses = by_event.get(event_type, [])
        if not event_consensuses:
            missing_semantics.append(event_type)
            continue
        for consensus in event_consensuses:
            if str(consensus.build_sha256 or "").strip().casefold() != manifest.build_sha256:
                invalid_semantics.add(event_type)
                semantic_validations.append(
                    DeobfuscationEvidenceValidation(
                        False,
                        "semantic_build_mismatch",
                        event_type,
                    )
                )
                continue
            validation = validate_consensus_deobfuscation_reports(
                consensus,
                reports,
                expected_message=expected_message,
                minimum_confidence=minimum_confidence,
            )
            semantic_validations.append(validation)
            if not validation.valid:
                invalid_semantics.add(event_type)

    missing_tuple = tuple(sorted(set(missing_semantics)))
    invalid_tuple = tuple(sorted(invalid_semantics))

    if not mapping_validation.valid:
        reason = "mapping_evidence_invalid"
    elif missing_tuple:
        reason = "semantic_evidence_missing"
    elif invalid_tuple:
        reason = "semantic_evidence_invalid"
    else:
        reason = "candidate_evidence_complete"

    return ProtocolMappingReadinessValidation(
        valid=(
            mapping_validation.valid
            and not missing_tuple
            and not invalid_tuple
        ),
        reason=reason,
        mapping_validation=mapping_validation,
        semantic_validations=tuple(semantic_validations),
        missing_semantic_events=missing_tuple,
        invalid_semantic_events=invalid_tuple,
    )


def audit_protocol_mapping_readiness(
    mapping_path: str | Path,
    consensus_paths: Sequence[str | Path],
    bundle_path: str | Path,
    report_paths: Sequence[str | Path],
    *,
    required_semantics: Mapping[str, str] = DEFAULT_REQUIRED_SEMANTICS,
    minimum_confidence: float = 100.0,
) -> tuple[
    ProtocolMappingManifest,
    tuple[ProtocolDiscoveryConsensus, ...],
    ProtocolMappingReadinessValidation,
]:
    manifest, consensuses, mapping_validation = audit_mapping_evidence(
        mapping_path,
        consensus_paths,
    )
    bundle = load_deobfuscation_evidence_bundle(bundle_path)
    verified_reports = verify_deobfuscation_evidence_bundle(
        bundle,
        report_paths,
        expected_build_sha256=manifest.build_sha256,
    )
    validation = validate_protocol_mapping_readiness(
        manifest,
        consensuses,
        mapping_validation,
        verified_reports,
        required_semantics=required_semantics,
        minimum_confidence=minimum_confidence,
    )
    return manifest, consensuses, validation


def audit_payload(
    mapping_path: str | Path,
    bundle_path: str | Path,
    manifest: ProtocolMappingManifest,
    validation: ProtocolMappingReadinessValidation,
) -> dict[str, Any]:
    payload = validation.to_dict()
    payload.update(
        {
            "mapping_path": str(Path(mapping_path)),
            "deobfs_bundle_path": str(Path(bundle_path)),
            "game_version": manifest.game_version,
            "build_sha256": manifest.build_sha256,
        }
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit one explicit direct exact-build mapping against strict network consensus "
            "and build-bound local dofus-deobfs semantic reports. Specialized current-profile "
            "decoders use their dedicated calibration path. This command never installs or "
            "enables a mapping."
        )
    )
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--bundle", required=True, help="Exact-build deobfs evidence bundle JSON.")
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="dofus-deobfs report path; the complete set must match the bundle exactly.",
    )
    parser.add_argument("--minimum-confidence", type=float, default=100.0)
    parser.add_argument(
        "consensus",
        nargs="+",
        help="Strict discovery consensus JSON files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest, _consensuses, validation = audit_protocol_mapping_readiness(
            args.mapping,
            args.consensus,
            args.bundle,
            args.report,
            minimum_confidence=args.minimum_confidence,
        )
    except (
        ProtocolMappingError,
        ProtocolDiscoveryEvidenceError,
        DeobfuscationReportError,
        DeobfuscationEvidenceBundleError,
        ValueError,
    ) as exc:
        print(f"network protocol readiness audit failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            audit_payload(args.mapping, args.bundle, manifest, validation),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if validation.valid else 3


__all__ = [
    "DEFAULT_REQUIRED_SEMANTICS",
    "ProtocolMappingReadinessValidation",
    "audit_protocol_mapping_readiness",
    "validate_protocol_mapping_readiness",
]


if __name__ == "__main__":
    raise SystemExit(main())
