from __future__ import annotations

"""Fail-closed comparison against a completed Atlas Integrity FULL report.

This is an offline shadow audit, never a phase verdict, and it cannot authenticate
an arbitrary local JSON file as a GitHub Actions attestation.
"""
import json
import re
from pathlib import Path
from typing import Any

from tools.atlas_integrity import load_policy

ROOT = Path(__file__).resolve().parents[2]
MAX_FULL_REPORT_BYTES = 5_000_000
SHA = re.compile(r"[0-9a-f]{40}\Z")


def _actual_required_groups() -> set[str]:
    policy = load_policy(ROOT)
    certification = policy.get("certification", {})
    mandatory = certification.get("required_groups", [])
    if certification.get("minimum_mode") != "FULL" or not isinstance(mandatory, list):
        raise ValueError("Invalid independent FULL certification policy")
    if not mandatory or any(not isinstance(name, str) or name not in policy["groups"]
                            for name in mandatory):
        raise ValueError("Missing independent FULL certification groups")
    return set(mandatory)


def evaluate_shadow(plan: dict[str, Any], full: dict[str, Any]) -> dict[str, Any]:
    """Review exact-SHA observed outcomes. A local report is never trusted provenance."""
    errors: list[str] = []
    expected_head = plan.get("candidate_sha")
    if (not isinstance(expected_head, str) or not SHA.fullmatch(expected_head)
            or full.get("head") != expected_head):
        errors.append("CANDIDATE_SHA_MISMATCH")
    if not isinstance(plan.get("plan_fingerprint"), str) or not plan["plan_fingerprint"]:
        errors.append("INVALID_PLAN")

    if full.get("schema_version") != 1 or full.get("mode") != "FULL":
        errors.append("NOT_AN_ATLAS_INTEGRITY_FULL_REPORT")
    if full.get("verdict") not in {"PASS", "BLOCKED"}:
        errors.append("UNKNOWN_FULL_VERDICT")

    try:
        mandatory = _actual_required_groups()
    except (ValueError, OSError, KeyError, TypeError):
        errors.append("INDEPENDENT_POLICY_UNAVAILABLE")
        mandatory = {"FULL_SUITE", "DATA_INTEGRITY"}
    raw_required = full.get("validations_required")
    required = set()
    if not isinstance(raw_required, list) or any(
        not isinstance(name, str) for name in raw_required
    ) or len(raw_required) != len(set(raw_required)):
        errors.append("MALFORMED_FULL_REQUIREMENTS")
    else:
        required = set(raw_required)
    missing = mandatory - required
    if missing:
        errors.append("REQUIRED_POLICY_GROUPS_MISSING")
    groups = full.get("groups")
    if not isinstance(groups, dict):
        errors.append("MALFORMED_FULL_GROUPS")
        groups = {}
    group_failures: list[str] = []
    for name in sorted(required | mandatory):
        group = groups.get(name)
        if not isinstance(group, dict):
            errors.append("FULL_EVIDENCE_MISSING:" + name)
            group_failures.append(name)
            continue
        if group.get("required") is not True:
            errors.append("FULL_GROUP_NOT_MARKED_REQUIRED:" + name)
        if group.get("status") != "PASS":
            group_failures.append(name)
        if group.get("status") == "PASS" and group.get("blockers"):
            errors.append("PASS_GROUP_WITH_BLOCKERS:" + name)
    blockers = full.get("blockers")
    if not isinstance(blockers, list):
        errors.append("MALFORMED_FULL_BLOCKERS")
        blockers = ["INVALID"]

    # A passed FULL_SUITE without a real successful command/test count is an
    # invalid report, even if a JSON object falsely says status=PASS.
    suite = groups.get("FULL_SUITE")
    if isinstance(suite, dict) and suite.get("status") == "PASS":
        commands = suite.get("commands")
        if (not isinstance(commands, list) or not commands or
                not all(isinstance(cmd, dict) and cmd.get("exit_code") == 0
                        and isinstance(cmd.get("tests"), int) and cmd["tests"] > 0
                        for cmd in commands)):
            errors.append("UNPROVEN_FULL_SUITE_EXECUTION")
    if full.get("verdict") == "PASS" and (group_failures or blockers):
        errors.append("INCONSISTENT_FULL_PASS")

    full_pass = (not errors and full.get("verdict") == "PASS"
                 and not group_failures and not blockers)
    scoped_result = (plan.get("execution") or {}).get("status")
    would_be_scoped_pass = (
        plan.get("status") == "READY_TO_RUN_SCOPED"
        and scoped_result == "SCOPED_TESTS_PASS"
    )
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
        "errors": sorted(set(errors)),
        "full_verdict": full.get("verdict"),
        "full_mode": full.get("mode"),
        "failed_or_blocked_groups": sorted(set(group_failures)),
        "scoped_verdict": scoped_result,
        "full_suite_not_waived": True,
        "phase_certified": False,
        "merge_authorized": False,
        "trusted_workflow_provenance": False,
        "note": "Local JSON is not a trusted GitHub attestation. Passing history does not prove the selector safe on future changes.",
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
        "limitations": "Historical outcomes cannot establish zero future selection errors or trusted attestation.",
    }
