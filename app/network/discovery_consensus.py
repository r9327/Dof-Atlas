from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.network.discovery_evidence import (
    ProtocolDiscoveryEvidenceError,
    build_discovery_consensus,
)


def load_report(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolDiscoveryEvidenceError(
            f"cannot read discovery report: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProtocolDiscoveryEvidenceError(
            f"discovery report root must be an object: {source}"
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Intersect multiple payload-free Dofus protocol discovery reports. "
            "Consensus is evidence only and never becomes a runtime mapping automatically."
        )
    )
    parser.add_argument(
        "reports",
        nargs="+",
        help="Two or more JSON reports produced by app.network.discovery_probe.",
    )
    parser.add_argument(
        "--minimum-reports",
        type=int,
        default=2,
        help="Minimum evidence report count (default: 2, never less than 2).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        reports = [load_report(path) for path in args.reports]
        consensus = build_discovery_consensus(
            reports,
            minimum_reports=args.minimum_reports,
        )
    except ProtocolDiscoveryEvidenceError as exc:
        print(f"network discovery consensus failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(consensus.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
