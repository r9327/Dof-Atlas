from __future__ import annotations

"""Doctor shadow certification audit of previously completed FULL reports.

Never starts FULL, never declares scoped == exhaustive and never authorizes
a merge. Flags where proposed scope would have hidden observed FULL failures.
"""
import json
from pathlib import Path
from typing import Any

MAX_FULL_REPORT_BYTES = 5_000_000


def evaluate_shadow(plan: dict[str, Any], full: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    expected_head = plan.get("candidate_sha")
    full_head = full.get("head")
    if not isinstance(expected_head, str) or len(expected_head) != 40 or full_head != expected_head:
        errors.append("CANDIDATE_SHA_MISMATCH")
    required = list(full.get("validations_required") or [])
    groups = full.get("groups") or {}
    if not isinstance(groups, dict) or not isinstance(required, list):
        errors.append("MALFORMED_FULL_GROUPS")
        groups, required = {}, []
    if any(not isinstance(name, str) or not isinstance(groups.get(name), dict)
           for name in required):
        errors.append("MALFORMED_FULL_GROUPS")
    required = [name for name in required if isinstance(name, str)]
    for group in ("FULL_SUITE", "DATA_INTEGRITY"):
        if group not in required or not isinstance(groups.get(group), dict):
            errors.append("FULL_EVIDENCE_MISSING:" + group)
    if not full.get("verdict") in {"PASS", "FAIL", "BLOCKED"}:
        errors.append("UNKNOWN_FULL_VERDICT")
    if not expected_head or plan.get("plan_fingerprint") is None:
        errors.append("INVALID_PLAN")
    group_failures = sorted(
        group for group in required
        if not isinstance(groups.get(group), dict)
        or groups[group].get("status") != "PASS"
    )
    full_pass = (not errors and full.get("verdict") == "PASS"
                 and not group_failures and not full.get("blockers"))
    scoped_result = (plan.get("execution") or {}).get("status")
    would_be_scoped_pass = (plan.get("status") == "READY_TO_RUN_SCOPED"
                            and scoped_result == "SCOPED_TESTS_PASS")
    if errors:
        status = "INVALID_EVIDENCE"
    elif not full_pass and would_be_scoped_pass:
        status = "POTENTIAL_MISSED_REGRESSION"
    elif not full_pass:
        status = "FULL_BLOCKED"
    elif would_be_scoped_pass:
        status = "NO_OBSERVED_DIVERGENCE"
    elif plan.get("status") == "FULL_REQUIRED":
        status = "FULL_REMAINED_REQUIRED"
    else:
        status = "NOT_COMPARABLE"
    return {
        "kind": "doctor_certification_shadow_comparison",
        "candidate_sha": expected_head,
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "status": status,
        "errors": errors,
        "full_verdict": full.get("verdict"),
        "failed_or_blocked_groups": group_failures,
        "scoped_verdict": scoped_result,
        "full_suite_not_waived": True,
        "phase_certified": False,
        "merge_authorized": False,
        "note": "A PASS shadow comparison is not proof that this selector is safe on future changes.",
    }


def load_full_report(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FULL_REPORT_BYTES:
        raise ValueError("FULL report must be an existing, bounded JSON file")
    parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(parsed, dict):
        raise ValueError("Expected FULL report object")
    return parsed


def aggregate_shadows(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    if not comparisons:
        return {"status": "INSUFFICIENT_EVIDENCE", "samples": 0, "safe_to_relax_full": False}
    missed = sum(r.get("status") == "POTENTIAL_MISSED_REGRESSION" for r in comparisons)
    invalid = sum(r.get("status") == "INVALID_EVIDENCE" for r in comparisons)
    return {
        "kind": "doctor_certification_shadow_aggregate",
        "samples": len(comparisons),
        "potential_missed_regressions": missed,
        "invalid_samples": invalid,
        "status": "BLOCKED" if missed or invalid else "ADVISORY",
        "safe_to_relax_full": False,
        "full_coverage_proven": False,
        "limitations": "Historical outcomes cannot establish zero future selection errors.",
    }
