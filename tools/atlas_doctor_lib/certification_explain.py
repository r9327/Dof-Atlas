from __future__ import annotations

"""Human-readable selected/deferred test explanations for Doctor.

Do not misrepresent an unselected test as proven irrelevant: only canonical
selector and independent scenario coverage can set advisory targeted scope,
not full/phase certification equivalence.
"""
from pathlib import Path
from typing import Any

MAX_TESTS = 700


def explain_selection(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return {"status": "BLOCKED", "reason": "NO_TEST_DIRECTORY", "tests": []}
    files = sorted(tests_dir.glob("test_*.py"))
    if len(files) > MAX_TESTS or any(not file.is_file() or file.is_symlink() for file in files):
        return {"status": "BLOCKED", "reason": "UNSAFE_OR_OVERSIZE_TEST_INVENTORY", "tests": []}
    selected = set(plan.get("test_modules") or [])
    available = {"tests." + f.stem for f in files}
    if selected - available:
        return {"status": "BLOCKED", "reason": "SELECTED_TEST_NOT_IN_INVENTORY", "tests": []}
    root_reasons = list(plan.get("reasons") or [])
    profiles = plan.get("profile")
    justifications = plan.get("test_selection_explanations") or {}
    rows = []
    for module in sorted(available):
        if module in selected:
            owner = justifications.get(module) or {}
            rows.append({
                "test": module, "action": "RUN",
                "reason": owner.get("source", "CANONICAL_SCOPE"),
                "triggered_by": owner.get("triggered_by", []),
                "phase_certification_equivalent": False,
            })
        else:
            rows.append({
                "test": module,
                "action": "DEFER_TO_FULL" if profiles == "FULL_REQUIRED" else "NOT_IN_SCOPED_SET",
                "reason": (",".join(root_reasons[:4]) if profiles == "FULL_REQUIRED" else
                           "NO_DIRECT_SCENARIO_MAPPING_PROVIDED_TO_ADVISORY_ROUTER"),
                "absence_of_dynamic_dependency_proven": False,
                "phase_certification_equivalent": False,
            })
    return {
        "kind": "doctor_test_selection_audit",
        "status": "ADVISORY_NO_FULL_WAIVER",
        "profile": profiles,
        "inventory_count": len(rows),
        "selected_count": len(selected),
        "deferred_count": len(rows) - len(selected),
        "tests": rows,
        "all_exclusions_proven_safe": False,
        "full_suite_waived": False,
    }
