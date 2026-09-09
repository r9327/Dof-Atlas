from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from app.network.deobfs_report import (
    DeobfuscationReportError,
    ankama_type_alias,
    load_deobfuscation_report,
)
from app.network.discovery_evidence import (
    ProtocolDiscoveryEvidenceError,
    ProtocolDiscoveryConsensus,
    parse_discovery_consensus,
)


@dataclass(frozen=True, slots=True)
class DeobfuscationEvidenceValidation:
    valid: bool
    reason: str
    event_type: str
    type_url: str = ""
    alias: str = ""
    original_message: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "purpose": "protocol_deobfuscation_evidence_audit",
            "authoritative_mapping": False,
            "valid": self.valid,
            "reason": self.reason,
            "event_type": self.event_type,
            "type_url": self.type_url,
            "alias": self.alias,
            "original_message": self.original_message,
            "confidence": self.confidence,
        }


def load_consensus(path: str | Path) -> ProtocolDiscoveryConsensus:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolDiscoveryEvidenceError(f"cannot load discovery consensus: {source}") from exc
    return parse_discovery_consensus(raw)


def validate_consensus_deobfuscation(
    consensus: ProtocolDiscoveryConsensus,
    report_path: str | Path,
    *,
    expected_message: str,
    minimum_confidence: float = 100.0,
) -> DeobfuscationEvidenceValidation:
    return validate_consensus_deobfuscation_reports(
        consensus,
        (report_path,),
        expected_message=expected_message,
        minimum_confidence=minimum_confidence,
    )


def validate_consensus_deobfuscation_reports(
    consensus: ProtocolDiscoveryConsensus,
    report_paths: Iterable[str | Path],
    *,
    expected_message: str,
    minimum_confidence: float = 100.0,
) -> DeobfuscationEvidenceValidation:
    """Validate one discovered alias against one or more dofus-deobfs reports.

    Dofus-deobfs emits separate enum- and strict-structure reports. A definitive
    match in either report may support the semantic alias, but evidence fails
    closed if the alias is marked uncertain anywhere or if definitive reports
    disagree on the original message. Reports are evidence only and never
    install or enable a runtime mapping.
    """

    event_type = str(consensus.event_type or "").strip().casefold()
    expected = str(expected_message or "").strip()
    if not expected:
        raise ValueError("expected_message cannot be empty")
    if not consensus.unambiguous or len(consensus.candidates) != 1:
        return DeobfuscationEvidenceValidation(False, "consensus_not_unambiguous", event_type)

    candidate = consensus.candidates[0]
    type_url = str(candidate.type_url or "").strip()
    alias = ankama_type_alias(type_url)
    if not alias:
        return DeobfuscationEvidenceValidation(
            False,
            "unsupported_type_url_alias",
            event_type,
            type_url=type_url,
        )

    paths = tuple(Path(path) for path in report_paths)
    if not paths:
        raise ValueError("at least one deobfuscation report is required")

    matches = []
    for path in paths:
        report = load_deobfuscation_report(path)
        if alias in report.uncertain_aliases:
            return DeobfuscationEvidenceValidation(
                False,
                "uncertain_deobfuscation_alias",
                event_type,
                type_url=type_url,
                alias=alias,
            )
        match = report.definitive_for_alias(
            alias,
            minimum_confidence=float(minimum_confidence),
        )
        if match is not None:
            matches.append(match)

    if not matches:
        return DeobfuscationEvidenceValidation(
            False,
            "no_definitive_deobfuscation_match",
            event_type,
            type_url=type_url,
            alias=alias,
        )

    originals = {match.original_message for match in matches}
    if len(originals) != 1:
        return DeobfuscationEvidenceValidation(
            False,
            "conflicting_deobfuscation_matches",
            event_type,
            type_url=type_url,
            alias=alias,
        )

    original = next(iter(originals))
    confidence = min(float(match.confidence) for match in matches)
    if original != expected:
        return DeobfuscationEvidenceValidation(
            False,
            "deobfuscated_message_mismatch",
            event_type,
            type_url=type_url,
            alias=alias,
            original_message=original,
            confidence=confidence,
        )
    return DeobfuscationEvidenceValidation(
        True,
        "deobfuscated_message_match",
        event_type,
        type_url=type_url,
        alias=alias,
        original_message=original,
        confidence=confidence,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check one unambiguous network discovery alias against local "
            "dofus-deobfs match reports. This is evidence only and never installs a mapping."
        )
    )
    parser.add_argument("--consensus", required=True)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="dofus-deobfs report path; repeat for enum_matches and structure_matches.",
    )
    parser.add_argument("--expected-message", required=True)
    parser.add_argument("--minimum-confidence", type=float, default=100.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        consensus = load_consensus(args.consensus)
        validation = validate_consensus_deobfuscation_reports(
            consensus,
            args.report,
            expected_message=args.expected_message,
            minimum_confidence=args.minimum_confidence,
        )
    except (ProtocolDiscoveryEvidenceError, DeobfuscationReportError, ValueError) as exc:
        print(f"network deobfuscation audit failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(validation.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if validation.valid else 3


if __name__ == "__main__":
    raise SystemExit(main())
