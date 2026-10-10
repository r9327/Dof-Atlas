from __future__ import annotations

"""Attested-shape (NOT signed) advisory certificates bound to one exact SHA.

The file hashes detect accidental artifact corruption. Trust still depends
on GitHub's workflow provenance: an arbitrary JSON file is not a certificate.
"""
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

from .certification_engine import fingerprint
from .certification_policy import POLICY_ID

MAX_PASSPORT_BYTES = 1_000_000
ALLOWED_VERDICTS = frozenset({
    "SCOPED_PASS_NOT_FULL", "FULL_PENDING", "BLOCKED",
})


def environment(root: Path) -> dict[str, Any]:
    """Reproducible constraints, not a claim of an isolated/hermetic runner."""
    requirements = root / "requirements-pyside.txt"
    try:
        requirements_sha = hashlib.sha256(requirements.read_bytes()).hexdigest()
    except OSError:
        requirements_sha = "UNAVAILABLE"
    return {
        "os": os.name,
        "platform": platform.system(),
        "python": sys.version.split()[0],
        "requirements_sha256": requirements_sha,
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
    }


def build_passport(plan: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Explicit evidence status per scenario; never invent executed tests."""
    policy = plan.get("independent_policy") or {}
    execution = plan.get("execution") or {}
    policy_ok = (plan.get("independent_verdict") or {}).get("status") == "POLICY_CONFORMING"
    exact = (
        isinstance(plan.get("candidate_sha"), str)
        and isinstance(plan.get("base_sha"), str)
        and len(plan["candidate_sha"]) == 40
        and len(plan["base_sha"]) == 40
    )
    modules = list(plan.get("test_modules") or [])
    passed = (
        policy_ok and exact and plan.get("status") == "READY_TO_RUN_SCOPED"
        and execution.get("status") == "SCOPED_TESTS_PASS"
        and execution.get("executed_modules") == modules
        and execution.get("exit_code") == 0
    )
    verdict = ("SCOPED_PASS_NOT_FULL" if passed else
               "FULL_PENDING" if policy_ok and plan.get("status") == "FULL_REQUIRED"
               else "BLOCKED")
    scenario_rows = {}
    for name, scenario in sorted((policy.get("scenarios") or {}).items()):
        required = list(scenario.get("tests") or [])
        scenario_rows[name] = {
            "triggered_by": scenario.get("triggered_by", []),
            "required_tests": required,
            "tests_status": ("SCOPED_TESTS_PASS" if passed and all(
                module in modules for module in required
            ) else "NOT_EXECUTED_OR_INCOMPLETE"),
            "metrics": scenario.get("metrics", []),
            "metrics_status": ("NOT_REQUIRED" if not scenario.get("metrics")
                               else "NOT_RUN"),
        }

    payload = {
        "schema_version": 1,
        "kind": "doctor_certification_passport",
        "candidate_sha": plan.get("candidate_sha"),
        "base_sha": plan.get("base_sha"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "policy_id": POLICY_ID,
        "environment": environment(root),
        "verdict": verdict,
        "phase_certified": False,
        "release_certified": False,
        "full_suite_waived": False,
        "merge_authorized": False,
        "tests_passed": modules if passed else [],
        "scenario_evidence": scenario_rows,
        "metrics_required": list(policy.get("required_metrics") or []),
        "metrics_executed": [],
        "unresolved_reasons": list(plan.get("reasons") or []),
        "source_impact": plan.get("source_impact"),
        "traceability": plan.get("test_selection_explanations", {}),
        "execution": {
            "status": execution.get("status", "NOT_RUN"),
            "duration_seconds": execution.get("duration_seconds"),
            "exit_code": execution.get("exit_code"),
        },
        "authority": "ADVISORY_ONLY",
        "limitations": [
            "SHA identity without trusted workflow provenance is not a cryptographic attestation.",
            "No cross-SHA reuse; no Phase or release certificate can be granted here.",
            "Static import analysis cannot prove absent Qt/dynamic consumers.",
            "Scenarios with required metrics remain unverified until measured.",
        ],
    }
    payload["content_digest"] = fingerprint(payload)
    return payload


def verify_passport(passport: dict[str, Any], *, head_sha: str,
                    plan_fingerprint: str, runner_environment: dict[str, Any]) -> dict[str, Any]:
    """Check expected identity, shape and checksum; not trusted provenance."""
    errors = []
    if passport.get("verdict") not in ALLOWED_VERDICTS:
        errors.append("UNKNOWN_VERDICT")
    if passport.get("candidate_sha") != head_sha:
        errors.append("CANDIDATE_MISMATCH")
    if passport.get("plan_fingerprint") != plan_fingerprint:
        errors.append("PLAN_MISMATCH")
    if passport.get("environment") != runner_environment:
        errors.append("ENVIRONMENT_MISMATCH")
    raw = dict(passport)
    actual = raw.pop("content_digest", None)
    if not isinstance(actual, str) or actual != fingerprint(raw):
        errors.append("DIGEST_MISMATCH")
    for key in ("phase_certified", "release_certified", "full_suite_waived", "merge_authorized"):
        if passport.get(key) is not False:
            errors.append("FORBIDDEN_CERTIFICATION_CLAIM:" + key)
    if passport.get("authority") != "ADVISORY_ONLY" or passport.get("policy_id") != POLICY_ID:
        errors.append("WRONG_POLICY_OR_AUTHORITY")
    if passport.get("verdict") == "SCOPED_PASS_NOT_FULL":
        execution = passport.get("execution")
        if not isinstance(execution, dict) or execution.get("status") != "SCOPED_TESTS_PASS":
            errors.append("UNSUPPORTED_SCOPED_PASS")
        if not passport.get("tests_passed"):
            errors.append("NO_EXECUTED_TESTS")
    return {"status": "BLOCKED" if errors else "INTEGRITY_CHECKED_NOT_ATTESTED",
            "errors": sorted(set(errors)), "phase_certified": False,
            "reuse_on_other_sha": False}


def load_passport(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PASSPORT_BYTES:
        raise ValueError("Missing, unsafe or oversized passport")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Passport must be a JSON object")
    return data


def compare_passports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Explain changed obligations, never waive unexecuted coverage."""
    if before.get("kind") != "doctor_certification_passport" or after.get("kind") != "doctor_certification_passport":
        raise ValueError("Expected Doctor certification passports")
    old = set((before.get("scenario_evidence") or {}).keys())
    new = set((after.get("scenario_evidence") or {}).keys())
    old_metrics = set(before.get("metrics_required") or [])
    new_metrics = set(after.get("metrics_required") or [])
    return {
        "kind": "doctor_certification_change_comparison",
        "before_sha": before.get("candidate_sha"),
        "after_sha": after.get("candidate_sha"),
        "new_scenarios": sorted(new - old),
        "removed_scenarios": sorted(old - new),
        "added_metrics": sorted(new_metrics - old_metrics),
        "removed_metrics": sorted(old_metrics - new_metrics),
        "before_verdict": before.get("verdict"),
        "after_verdict": after.get("verdict"),
        "proof_of_non_regression": False,
        "cross_sha_evidence_reuse": False,
    }
