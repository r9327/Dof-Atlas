"""Read-only Atlas preview of Documentalist JSON exchanges.

It prints the exact ID-level delta and unresolved reference errors without
updating the active quests, achievements, guides, progress or user files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .atlas_data_exchange import (
    InvalidDocumentExchange, load_documentalist_exchange, plan_documentalist_exchange,
)
from .atlas_data_plan import AtlasDataPlanError

_MAX_FILE_BYTES = 8 * 1024 * 1024


def _read(path: Path):
    if path.stat().st_size > _MAX_FILE_BYTES:
        raise InvalidDocumentExchange("input file exceeds 8 MiB")
    return load_documentalist_exchange(path.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview data changes by ID (no writes)")
    parser.add_argument("current", type=Path)
    parser.add_argument("incoming", type=Path)
    parser.add_argument("--json", action="store_true", help="Return structured report")
    args = parser.parse_args(argv)
    try:
        old = _read(args.current)
        new = _read(args.incoming)
        changes = plan_documentalist_exchange(old, new)
    except (OSError, ValueError, UnicodeError, InvalidDocumentExchange, AtlasDataPlanError) as exc:
        print(json.dumps({"status": "INVALID", "reason": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    rows = [{"kind": c.kind, "id": c.identifier, "action": c.action,
             "old_sha256": c.old_sha256, "new_sha256": c.new_sha256}
            for c in changes]
    report = {
        "status": "PREVIEW_ONLY",
        "source": new.source,
        "source_sha256": new.source_sha256,
        "changes": rows,
        "counts": {state: sum(x["action"] == state for x in rows)
                   for state in ("add", "update", "keep", "absent_in_batch")},
    }
    if args.json:
        print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    else:
        print(f"PREVIEW_ONLY: {len(rows)} IDs, source {new.source}")
        for row in rows:
            print(f'{row["action"]:16} {row["kind"]}:{row["id"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
