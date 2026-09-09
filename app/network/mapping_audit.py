from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.network.discovery_evidence import (
    ProtocolDiscoveryEvidenceError,
    ProtocolDiscoveryConsensus,
    parse_discovery_consensus,
)
from app.network.mapping_evidence import MappingEvidenceValidation, validate_mapping_against_consensus
from app.network.mapping_manifest import ProtocolMappingError, ProtocolMappingManifest, load_protocol_mapping


def load_consensus(path: str | Path) -> ProtocolDiscoveryConsensus:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolDiscoveryEvidenceError(f"cannot load discovery consensus: {source}") from exc
    return parse_discovery_consensus(raw)


def audit_mapping_evidence(
    mapping_path: str | Path,
    consensus_paths: Sequence[str | Path],
) -> tuple[ProtocolMappingManifest, tuple[ProtocolDiscoveryConsensus, ...], MappingEvidenceValidation]:
    manifest = load_protocol_mapping(mapping_path)
    consensuses = tuple(load_consensus(path) for path in consensus_paths)
    validation = validate_mapping_against_consensus(manifest, consensuses)
    return manifest, consensuses, validation


def audit_payload(
    mapping_path: str | Path,
    manifest: ProtocolMappingManifest,
    consensuses: Sequence[ProtocolDiscoveryConsensus],
    validation: MappingEvidenceValidation,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "purpose": "protocol_mapping_evidence_audit",
        "mapping_path": str(Path(mapping_path)),
        "game_version": manifest.game_version,
        "build_sha256": manifest.build_sha256,
        "consensus_count": len(consensuses),
        "consensus_events": sorted({row.event_type for row in consensuses}),
        "valid": validation.valid,
        "reason": validation.reason,
        "checked_events": list(validation.checked_events),
        "missing_events": list(validation.missing_events),
        "mismatched_events": list(validation.mismatched_events),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit one explicit exact-build protocol mapping against strict "
            "payload-free discovery consensus files. This command never installs "
            "or enables a mapping."
        )
    )
    parser.add_argument("--mapping", required=True, help="Protocol mapping JSON to audit.")
    parser.add_argument(
        "consensus",
        nargs="+",
        help="Strict consensus JSON files produced by app.network.discovery_consensus.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest, consensuses, validation = audit_mapping_evidence(
            args.mapping,
            args.consensus,
        )
    except (ProtocolMappingError, ProtocolDiscoveryEvidenceError) as exc:
        print(f"network mapping evidence audit failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            audit_payload(args.mapping, manifest, consensuses, validation),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if validation.valid else 3


if __name__ == "__main__":
    raise SystemExit(main())
