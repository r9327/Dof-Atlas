from __future__ import annotations

"""Independent, additive certification obligations for Doctor Atlas.

This module does not consult or trust the scope selector's FAST verdict.
The existing Atlas Integrity FULL phase contract remains the final authority.
"""
from pathlib import Path
from typing import Any

from tools.atlas_integrity import affected_groups, classify_risk

POLICY_ID = "doctor-adaptive-independent-policy-v1"

# Paths match known, runnable test contracts in the canonical repository.
# Benchmarks are planned separately because ordinary unit tests cannot
# establish a memory, time, or process-tree budget.
SCENARIOS: dict[str, dict[str, Any]] = {
    "encyclopedia_navigation": {
        "triggers": ("app/modules/encyclopedia/",),
        "tests": ("tests.test_encyclopedia_on_demand_loading",
                  "tests.test_encyclopedia_tab_demand_loading"),
        "metrics": (),
    },
    "guide_progression": {
        "triggers": ("app/modules/encyclopedia/services/guide_",
                     "app/modules/encyclopedia/providers/guide_",
                     "data/routes/guide_ultime_manual/"),
        "tests": ("tests.test_guide_ultime_manual_prerequisites",),
        "metrics": (),
    },
    "startup_resource_contract": {
        "triggers": ("main.py", "launch.py", "DOFUS.bat",
                     "app/startup/", "app/ui/"),
        "tests": ("tests.test_startup_resource_contracts",),
        "metrics": ("startup_time",),
    },
    "qt_lifecycle": {
        "triggers": ("app/modules/encyclopedia/widgets/",
                     "app/modules/encyclopedia/views/",
                     "app/ui/", "app/pages/"),
        "tests": ("tests.test_performance_guardrails",),
        "metrics": ("qt_lifecycle",),
    },
    "memory_and_preload": {
        "triggers": ("app/modules/encyclopedia/widgets/",
                     "app/modules/encyclopedia/providers/__init__.py",
                     "app/modules/encyclopedia/views/",
                     "app/ui/", "app/pages/"),
        "tests": ("tests.test_startup_resource_contracts",),
        "metrics": ("steady_rss_home", "process_tree_peak", "preload_time"),
    },
    "data_integrity": {
        "triggers": ("data/", "local_dofus_data/", "app/core/json_store.py"),
        "tests": ("tests.test_critical_json_schema",),
        "metrics": ("data_integrity",),
    },
}


def _triggered(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def obligations(root: Path, changed: list[str], consumers: list[str]) -> dict[str, Any]:
    """Return additive contracts, without executing tests or inferring PASS.

    Missing required tests are blockers. An exact path mapping is not enough
    evidence to waive a FULL, and absence of a match is NOT lack of impact.
    """
    impacted = sorted(set(changed + consumers))
    triggered: dict[str, dict[str, Any]] = {}
    required_tests: set[str] = set()
    metrics: set[str] = set()
    missing: list[str] = []
    for name, rule in SCENARIOS.items():
        matched = [p for p in impacted if _triggered(p, rule["triggers"])]
        if not matched:
            continue
        tests = list(rule["tests"])
        for module in tests:
            target = root / Path(*module.split(".")).with_suffix(".py")
            if not target.is_file():
                missing.append(module)
        required_tests.update(tests)
        metrics.update(rule["metrics"])
        triggered[name] = {"triggered_by": matched, "tests": tests,
                           "metrics": list(rule["metrics"]),
                           "status": "PLANNED_NOT_EXECUTED"}
    classification = classify_risk(changed)
    return {
        "policy_id": POLICY_ID,
        "scenarios": triggered,
        "required_tests": sorted(required_tests),
        "required_metrics": sorted(metrics),
        "missing_contracts": sorted(set(missing)),
        "integrity_groups_affected": affected_groups(changed),
        "canonical_risk": classification["risk"],
        "root_of_trust_changed": bool(classification["root_of_trust"]["modified"]),
        "tests_executed": False,
        "benchmarks_executed": False,
        "certified": False,
        "phase_full_still_required": True,
    }


def enforce(plan: dict[str, Any]) -> dict[str, Any]:
    """Independent verdict: scoped proof can never claim FULL certification."""
    errors: list[str] = []
    status = plan.get("status")
    validations = plan.get("validation")
    if status not in {"FULL_REQUIRED", "READY_TO_RUN_SCOPED"}:
        errors.append("INVALID_PLAN_STATUS")
    if not isinstance(validations, dict):
        errors.append("MISSING_VALIDATION_CONTRACT")
    else:
        if validations.get("certified") is not False:
            errors.append("SCOPED_CANNOT_BE_CERTIFIED")
        if validations.get("phase_certified") is not False:
            errors.append("PHASE_FULL_CANNOT_BE_WAIVED")
        if validations.get("full_suite_waived") is not False:
            errors.append("FULL_SUITE_WAIVER_PROHIBITED")
    policy = plan.get("independent_policy")
    if not isinstance(policy, dict) or policy.get("policy_id") != POLICY_ID:
        errors.append("POLICY_NOT_PRESENT")
    elif (policy.get("missing_contracts")
          or policy.get("canonical_risk") in {"HIGH", "CRITICAL"}
          or policy.get("root_of_trust_changed")):
        if status != "FULL_REQUIRED":
            errors.append("UNSAFE_SCOPE_DOWNGRADE")
    if status == "READY_TO_RUN_SCOPED":
        if plan.get("reasons") or not plan.get("test_modules"):
            errors.append("INCOMPLETE_SCOPED_PLAN")
        elif policy:
            missing = set(policy.get("required_tests", ())) - set(plan["test_modules"])
            if missing:
                errors.append("REQUIRED_SCENARIO_TESTS_OMITTED")
    return {
        "status": "BLOCKED" if errors else "POLICY_CONFORMING",
        "errors": sorted(set(errors)),
        "independent_verifier": POLICY_ID,
        "full_suite_waived": False,
        "phase_certified": False,
    }
