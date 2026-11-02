"""Audit the actual authored offline instruction coverage of the Ganymède library.

Observed links, route IDs, inferred quest commands and the 20 technical
TRUSTED_SOURCE_STEPS cutovers are not counted as complete instructions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.modules.encyclopedia.views.guide_library_sources import (
    INDEX_PATH, load_ganymede_listings, load_ganymede_local_instructions,
)


def audit_instruction_coverage(
    index_path: Path = INDEX_PATH,
    *,
    data_dir: Path | None = None,
    expected_routes: int = 95,
) -> dict:
    root = Path(data_dir) if data_dir is not None else Path(index_path).parent
    try:
        listings = load_ganymede_listings(Path(index_path))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"status": "FAIL", "error": str(exc), "expected_routes": expected_routes}
    complete, missing, invalid = [], [], []
    total = sum(row.step_count or 0 for row in listings)
    authored_steps = 0
    for entry in listings:
        try:
            steps = load_ganymede_local_instructions(entry, data_dir=root)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            invalid.append({"source_id": entry.source_id, "problem": str(exc)})
            continue
        if steps is None:
            missing.append(entry.source_id)
            continue
        complete.append(entry.source_id)
        authored_steps += len(steps)
    return {
        "status": (
            "PASS_INSTRUCTION_COVERAGE"
            if len(listings) == expected_routes and len(complete) == expected_routes
            else "INCOMPLETE"
        ),
        "source_inventory": len(listings),
        "expected_routes": expected_routes,
        "listed_steps": total,
        "complete_offline_instruction_routes": len(complete),
        "complete_offline_instruction_steps": authored_steps,
        "missing_instruction_routes": missing,
        "invalid_instruction_routes": invalid,
        "evidence": "authored_step_instructions_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail the gate while any of the 95 authored routes remains incomplete",
    )
    args = parser.parse_args()
    result = audit_instruction_coverage(args.index, data_dir=args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] == "FAIL" or (
        args.strict and result["status"] != "PASS_INSTRUCTION_COVERAGE"
    ))


if __name__ == "__main__":
    raise SystemExit(main())
