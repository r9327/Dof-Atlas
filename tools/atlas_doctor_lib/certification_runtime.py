from __future__ import annotations

"""Candidate-bound runtime evidence for certification passports.

Leverages the existing Doctor runtime observation collector. A Python call
proves execution, not an assertion, a test pass, or a RAM/Qt budget.
"""
from pathlib import Path
from typing import Any

from tools.atlas_doctor_lib.scenario_coverage import load_scenario_coverage


def attach_runtime_trace(root: Path, plan: dict[str, Any],
                         trace_paths: list[Path]) -> dict[str, Any]:
    if not 1 <= len(trace_paths) <= 12:
        raise ValueError("Provide 1..12 existing Doctor runtime traces")
    head = plan.get("candidate_sha")
    app_files = sorted({
        p for p in plan.get("changed_paths", []) + (plan.get("source_impact") or {}).get("consumers", [])
        if isinstance(p, str) and p.startswith("app/") and p.endswith(".py")
    })
    try:
        outcome = load_scenario_coverage(
            root, trace_paths, required_files=app_files[:128]
        )
    except (ValueError, OSError, RuntimeError) as exc:
        outcome = {
            "status": "REVIEW",
            "candidate_sha": head,
            "reason": type(exc).__name__,
            "unobserved_required_files": app_files[:128],
        }
    if len(app_files) > 128 or outcome.get("candidate_sha") != head:
        outcome = {
            "status": "REVIEW",
            "candidate_sha": head,
            "reason": "OVER_BUDGET_OR_WRONG_SHA",
            "unobserved_required_files": app_files,
        }
    return {
        "kind": "doctor_certification_runtime_scenario_observation",
        "candidate_sha": head,
        "status": "OBSERVED_NOT_CERTIFIED" if outcome.get("status") == "OBSERVED" else "REVIEW",
        "trace_status": outcome.get("status"),
        "required_app_files": app_files,
        "observed_app_files": outcome.get("observed_required_files", []),
        "unobserved_app_files": outcome.get("unobserved_required_files", app_files),
        "traces_checked": outcome.get("traces_checked", 0),
        "traces_invalid": outcome.get("traces_invalid", 0),
        "truncated": outcome.get("truncated", False),
        "functional_tests_passed": False,
        "performance_budgets_passed": False,
        "qt_lifecycle_certified": False,
        "full_suite_waived": False,
        "limitations": "Observation proves entered Python paths only, not end-to-end correctness.",
        **({"reason": outcome["reason"]} if outcome.get("reason") else {}),
    }
