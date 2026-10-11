from __future__ import annotations

"""Explicit, exact-SHA Atlas user journey contract runner.

This runs existing, real integration/contract tests on Windows/Qt. It does
NOT claim a real Dofus server, visual end-to-end run, Phase FULL, or measured
RAM/preload budgets. Expensive builders remain with #131.
"""
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_SELECTED = 5

SCENARIOS = {
    "guide_quest_succes": {
        "modules": [
            "tests.test_guide_ultime_manual_quest_links",
            "tests.test_guide_ultime_manual_success_sync",
            "tests.test_achievement_progress_logic",
            "tests.test_quest_detail_guide_ui_contract",
            "tests.test_quest_detail_navigation",
        ],
        "metrics": [],
        "description": "Guide cards -> Quest links -> Success mapping, real UI contracts",
    },
    "home_qt_lifecycle": {
        "modules": [
            "tests.test_atlas_window_runtime_cleanup",
            "tests.test_qt_async_non_accumulation",
            "tests.test_runtime_hook_lifecycle",
        ],
        "metrics": ["qt_lifecycle", "steady_rss_home", "process_tree_peak"],
        "description": "Startup/return Home/Qt cleanup contracts; RSS still needs benchmark",
    },
    "progress_persistence": {
        "modules": [
            "tests.test_guide_progress_persistence",
            "tests.test_quest_progress_batch_contract",
            "tests.test_achievement_progress_json_store",
        ],
        "metrics": [],
        "description": "Guide/Quest/Success persisted progress boundaries",
    },
    "guide_full_fixture_budget": {
        "modules": [
            "tests.test_guide_full_suite_fixture_budget",
            "tests.test_ci_guide_full_evidence",
        ],
        "metrics": [],
        "description": "Guard one Guide catalog build and exact successful FULL test ID reuse",
    },
    "startup_preload": {
        "modules": [
            "tests.test_startup_resource_contracts",
            "tests.test_startup_preloader",
            "tests.test_functional_preload_v2",
        ],
        "metrics": ["preload_time", "steady_rss_home"],
        "description": "Startup/preload unit contracts; resource measurements not inferred",
    },
}


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True,
                            text=True, timeout=12, check=False)
    if result.returncode:
        raise RuntimeError("Cannot verify immutable Git candidate")
    return result.stdout.strip()


def contract_plan(root: Path, sha: str, scenarios: list[str]) -> dict[str, Any]:
    """Never run anything or infer a PASS in the plan."""
    errors = []
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        errors.append("INVALID_SHA")
    if not scenarios or len(scenarios) > MAX_SELECTED or len(set(scenarios)) != len(scenarios):
        errors.append("INVALID_SCENARIO_SELECTION")
    unknown = sorted(set(scenarios) - SCENARIOS.keys())
    if unknown:
        errors.append("UNKNOWN_SCENARIOS")
    modules: list[str] = []
    metrics: set[str] = set()
    for name in scenarios:
        if name not in SCENARIOS:
            continue
        spec = SCENARIOS[name]
        modules.extend(spec["modules"])
        metrics.update(spec["metrics"])
    modules = sorted(set(modules))
    missing = [m for m in modules if not
               (root / Path(*m.split(".")).with_suffix(".py")).is_file()]
    if missing:
        errors.append("MISSING_SCENARIO_CONTRACTS")
    return {
        "kind": "doctor_scenario_contract_plan",
        "candidate_sha": sha, "selected_scenarios": scenarios,
        "required_test_modules": modules, "missing_test_modules": missing,
        "required_metrics": sorted(metrics), "metrics_executed": [],
        "status": "BLOCKED" if errors else "READY_TO_RUN_CONTRACTS",
        "errors": errors,
        "tests_executed": False, "all_end_to_end_certified": False,
        "phase_certified": False, "full_suite_waived": False,
    }


def execute_scenarios(
    root: Path, sha: str, scenario_names: list[str],
    *,
    runner: Callable[[Path, list[str]], int] | None = None,
) -> dict[str, Any]:
    report = contract_plan(root, sha, scenario_names)
    if report["status"] == "BLOCKED":
        return report
    try:
        actual = _git(root, "rev-parse", "HEAD")
        if actual != sha or _git(root, "status", "--porcelain", "--untracked-files=no"):
            raise RuntimeError("Dirty or wrong candidate SHA")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        report["status"] = "BLOCKED"
        report["errors"].append("UNTRUSTED_GIT_WORKTREE")
        return report
    if runner is None:
        from tools.ci_scope_gate import _run_scoped_modules
        runner = _run_scoped_modules
    started = time.perf_counter()
    try:
        exit_code = runner(root, report["required_test_modules"])
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        exit_code = 2
    report["tests_executed"] = True
    report["executed_test_modules"] = report["required_test_modules"]
    report["test_exit_code"] = exit_code
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    report["status"] = "CONTRACTS_PASS_METRICS_NOT_RUN" if exit_code == 0 else "BLOCKED"
    if exit_code != 0:
        report["errors"].append("SCENARIO_TESTS_FAILED")
    # The actual full UI journey and performance gate need independent
    # instrumentation and should NEVER be implied by these contracts.
    report["all_end_to_end_certified"] = False
    report["phase_certified"] = False
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", action="append", required=True,
                    choices=sorted(SCENARIOS))
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    plan = execute_scenarios(ROOT, args.expected_sha, args.scenario) if args.run else (
        contract_plan(ROOT, args.expected_sha, args.scenario)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0 if plan["status"] not in ("BLOCKED",) else 2


if __name__ == "__main__":
    raise SystemExit(main())
