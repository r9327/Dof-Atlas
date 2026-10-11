from __future__ import annotations

"""Inspect REAL archived Atlas Integrity FULL JSON and shadow-compare plans.

No GitHub workflow, test suite, or Qt scenario is launched by this tool.
Archived local JSON has no independently authenticated GitHub provenance.
"""
import argparse
import json
from pathlib import Path
from typing import Any

from tools.atlas_doctor_lib.certification_shadow import (
    aggregate_shadows, evaluate_shadow, load_full_report,
)

MAX_PLAN_BYTES = 2_000_000
MAX_CASES = 12


def _load_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PLAN_BYTES:
        raise ValueError("Invalid, missing or oversized Doctor plan")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Doctor plan must be a JSON object")
    if data.get("kind") != "doctor_adaptive_certification_plan":
        raise ValueError("Unrecognized Doctor plan kind")
    return data


def campaign(*, inspect_full: list[Path] | None = None,
             pairs: list[list[Path]] | None = None) -> dict[str, Any]:
    standalone = inspect_full or []
    compared = pairs or []
    if not 1 <= len(standalone) + len(compared) <= MAX_CASES:
        raise ValueError("Expected 1..12 archived FULL reports and/or same-SHA plan pairs")
    records: list[dict[str, Any]] = []
    for path in standalone:
        archive = load_full_report(path)
        candidate = archive.get("head")
        # Inspection is not a generated Doctor selection on this historical SHA!
        inspection_plan = {
            "candidate_sha": candidate,
            "plan_fingerprint": "standalone-full-inspection-only",
            "status": "FULL_REQUIRED",
            "execution": {"status": "NOT_RUN"},
        }
        result = evaluate_shadow(inspection_plan, archive)
        records.append({
            "kind": "historical_full_inspection",
            "candidate_sha": candidate,
            "status": ("STRUCTURALLY_VALID_FULL_PASS"
                       if result["status"] == "FULL_REMAINED_REQUIRED"
                       else "STRUCTURALLY_VALID_FULL_BLOCKED"
                       if result["status"] == "FULL_BLOCKED" else "INVALID_EVIDENCE"),
            "shadow_comparison_performed": False,
            "observed_full_duration_seconds": archive.get("duration_seconds"),
            "observed_full_tests": ((archive.get("groups") or {}).get("FULL_SUITE") or {}).get("tests"),
            "errors": result["errors"],
            "trusted_workflow_provenance": False,
            "phase_certified": False,
        })
    comparisons = []
    for pair in compared:
        if len(pair) != 2:
            raise ValueError("Expected Doctor-plan.json plus full-report.json")
        plan, archive = _load_plan(pair[0]), load_full_report(pair[1])
        record = evaluate_shadow(plan, archive)
        comparisons.append(record)
        records.append(record)
    aggregate = aggregate_shadows(comparisons)
    invalid = sum(x["status"] == "INVALID_EVIDENCE" for x in records)
    missed = aggregate.get("potential_missed_regressions", 0)
    status = ("BLOCKED" if invalid or missed else
              "SHADOW_ADVISORY" if compared else
              "FULL_ARCHIVES_VALIDATED_ONLY")
    return {
        "kind": "doctor_archived_full_shadow_campaign",
        "status": status, "records": records,
        "pair_summary": aggregate,
        "inspected_archives": len(standalone),
        "shadow_pairs": len(compared),
        "false_negative_candidates": missed,
        "invalid_evidence": invalid,
        "historical_runs_executed": False,
        "trusted_workflow_provenance": False,
        "safe_to_replace_full": False,
        "full_suite_waived": False,
        "phase_certified": False,
        "limitations": "Standalone FULL inspections are not shadow comparisons. "
                       "Local report integrity is not workflow attestation.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-full", action="append", type=Path, default=[],
                        help="Read a completed archived FULL JSON without a Doctor plan")
    parser.add_argument("--pair", action="append", nargs=2, type=Path, default=[],
                        metavar=("DOCTOR_PLAN", "EXACT_SHA_FULL_JSON"),
                        help="Compare a Doctor plan with an archived FULL on the same SHA")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = campaign(inspect_full=args.inspect_full, pairs=args.pair)
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        report = {
            "kind": "doctor_archived_full_shadow_campaign", "status": "BLOCKED",
            "error": type(exc).__name__, "full_suite_waived": False,
            "safe_to_replace_full": False,
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] in {"SHADOW_ADVISORY", "FULL_ARCHIVES_VALIDATED_ONLY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
