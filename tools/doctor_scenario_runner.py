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
    "quest_cold_detail": {
        "modules": [
            "tests.test_lazy_quests_detail_cache",
            "tests.test_quest_detail_navigation",
            "tests.test_phase8_preload_benchmark_contract",
        ],
        "metrics": ["first_quest_detail_ms"],
        "description": "Actual first Quest detail + source-index tests; wall time separately measured",
    },
    "success_cold_detail": {
        "modules": [
            "tests.test_achievement_compact_subprocess_lifecycle",
            "tests.test_achievement_frozen_detail_runtime",
            "tests.test_phase8_preload_benchmark_contract",
        ],
        "metrics": ["first_success_detail_ms", "ui_thread_blocking"],
        "description": "Success detail subprocess/cache and packaged-app lifecycle contracts",
    },
    "guide_cold_detail": {
        "modules": [
            "tests.test_guide_manual_route_cache",
            "tests.test_guide_manual_long_layout",
            "tests.test_phase8_preload_benchmark_contract",
        ],
        "metrics": ["first_guide_detail_ms"],
        "description": "First Guide detail, indexed route and navigation contracts",
    },
    "doctor_intelligence": {
        "modules": [
            "tests.test_doctor_diagnostic_correlation",
            "tests.test_doctor_optimization_report",
            "tests.test_tool_catalog",
        ],
        "metrics": [],
        "description": "Read-only specialist routing, evidence and optimization report contracts",
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
    executed: list[str] = []
    module_results: list[dict[str, Any]] = []
    failures: list[str] = []
    # IMPORTANT: run each module in a distinct canonical runner subprocess.
    # Running all modules in one Qt interpreter can retain SQLite/WAL handles
    # and QTimers between otherwise independent scenario contracts.
    for module in report["required_test_modules"]:
        module_started = time.perf_counter()
        try:
            code = runner(root, [module])
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            code = 2
        if type(code) is not int:
            code = 2
        executed.append(module)
        module_results.append({
            "module": module, "exit_code": code,
            "duration_seconds": round(time.perf_counter() - module_started, 3),
            "process_isolated": True,
        })
        if code != 0:
            failures.append(module)
    report["tests_executed"] = bool(executed)
    report["executed_test_modules"] = executed
    report["module_results"] = module_results
    report["failed_modules"] = failures
    report["isolated_process_per_module"] = True
    # Budget feedback comes from this real run and can be inspected by Doctor
    # on the next planning cycle. It is test wall time, NOT app startup/CPU/RAM.
    report["observed_test_cost"] = {
        "status": "OBSERVED",
        "test_module_count": len(executed),
        "total_module_wall_seconds": round(sum(
            row["duration_seconds"] for row in module_results
        ), 3),
        "slowest_modules": sorted(
            ({"module": row["module"],
              "duration_seconds": row["duration_seconds"]}
             for row in module_results),
            key=lambda row: (-row["duration_seconds"], row["module"]),
        )[:8],
        "limits": ["Process-isolated test wall time, not application CPU or RSS",
                   "No app performance metric was executed by contract tests"],
    }
    report["test_exit_code"] = 0 if not failures and len(executed) == len(
        report["required_test_modules"]
    ) else 2
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    # The contract runner may execute many isolated modules. Nothing may
    # modify tracked code after the initial exact-SHA gate without invalidating
    # *every* check result from the batch.
    try:
        post_sha = _git(root, "rev-parse", "HEAD")
        post_dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
        changed = post_sha != sha or bool(post_dirty)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        changed = True
    report["worktree_changed_during_tests"] = changed
    report["status"] = (
        "CONTRACTS_PASS_METRICS_NOT_RUN"
        if report["test_exit_code"] == 0 and not changed else "BLOCKED"
    )
    if changed:
        report["errors"].append("WORKTREE_CHANGED_DURING_TESTS")
    if failures or len(executed) != len(report["required_test_modules"]):
        report["errors"].append("SCENARIO_TESTS_FAILED")
    # The actual full UI journey and performance gate need independent
    # instrumentation and should NEVER be implied by these contracts.
    report["all_end_to_end_certified"] = False
    report["phase_certified"] = False
    return report


def doctor_report_scenarios(document: dict[str, Any], sha: str) -> dict[str, Any]:
    """Accept only a current, successful diagnostic and registered contracts."""
    reasons: list[str] = []
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        reasons.append("INVALID_SHA")
    if not isinstance(document, dict) or document.get("kind") != "atlas_doctor_optimization_report":
        reasons.append("NOT_A_DOCTOR_OPTIMIZATION_REPORT")
        document = {}
    if document.get("git_head") != sha or document.get("status") != "DIAGNOSTIC_READY":
        reasons.append("STALE_OR_BLOCKED_DIAGNOSTIC")
    correlation = document.get("diagnostic_correlation")
    if not isinstance(correlation, dict) or correlation.get("candidate_sha") != sha:
        reasons.append("STALE_OR_MISSING_CORRELATION")
        correlation = {}
    if correlation.get("status") != "REVIEW" or correlation.get("certification") is not False:
        reasons.append("UNTRUSTED_CORRELATION")
    investigation = correlation.get("investigation_plan")
    if not isinstance(investigation, dict) or investigation.get("candidate_sha") != sha:
        reasons.append("STALE_OR_MISSING_INVESTIGATION")
        investigation = {}
    contracts = investigation.get("scenario_contracts")
    if not isinstance(contracts, dict) or contracts.get("status") != "PLANNED_NOT_RUN":
        reasons.append("SCENARIO_COVERAGE_NOT_COMPLETE")
        contracts = {}
    entries = contracts.get("selected")
    rows = entries if isinstance(entries, list) else []
    names = [row.get("scenario") if isinstance(row, dict) else None
             for row in rows]
    valid_names = all(isinstance(name, str) and name in SCENARIOS
                      for name in names)
    ids = correlation.get("hypotheses")
    expected_ids = (
        {str(row["id"]) for row in ids
         if isinstance(row, dict) and isinstance(row.get("id"), str)}
        if isinstance(ids, list) else set()
    )
    covered: set[str] = set()
    valid_rows = bool(expected_ids)
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("scenario"), str):
            valid_rows = False
            continue
        scenario = row["scenario"]
        matched = row.get("covered_hypotheses")
        if (
            scenario not in SCENARIOS
            or row.get("runner") != "tools.doctor_scenario_runner"
            or row.get("execution_status") != "NOT_RUN"
            or row.get("required_sha_check") is not True
            or row.get("test_modules") != SCENARIOS[scenario]["modules"]
            or not isinstance(matched, list) or not matched
            or any(not isinstance(x, str) or x not in expected_ids for x in matched)
        ):
            valid_rows = False
            continue
        covered.update(matched)
    if (
        not rows or len(rows) > MAX_SELECTED or not valid_names
        or (valid_names and len(names) != len(set(names)))
        or not valid_rows or covered != expected_ids
        or contracts.get("uncovered_hypotheses")
    ):
        reasons.append("INVALID_OR_INCOMPLETE_SCENARIO_SELECTION")
    if correlation.get("tests_executed") is not False or investigation.get("tests_executed") is not False:
        reasons.append("UNTRUSTED_PREEXECUTION_CLAIMS")
    raw_gaps = [
        row for row in (
            correlation.get("evidence_gaps"),
            investigation.get("unresolved"),
        ) if isinstance(row, list)
    ]
    gaps = sorted({item for group in raw_gaps
                   for item in group if isinstance(item, str)})
    return {
        "status": "BLOCKED" if reasons else "READY_TO_RUN_CONTRACTS",
        "selected_scenarios": names if not reasons else [],
        "errors": sorted(set(reasons)),
        "evidence_gaps": gaps,
        "completeness": "PARTIAL_REVIEW" if gaps else "SCENARIOS_MAPPED_NOT_EXECUTED",
        "candidate_sha": sha,
        "tests_executed": False, "phase_certified": False,
        "certification_granted": False,
    }


def execute_doctor_report(
    root: Path, sha: str, document: dict[str, Any], *,
    runner: Callable[[Path, list[str]], int] | None = None,
    run: bool = False,
) -> dict[str, Any]:
    """Reuse the canonical scenario runner; execution requires explicit --run."""
    selection = doctor_report_scenarios(document, sha)
    if selection["status"] == "BLOCKED":
        return selection
    selected = selection["selected_scenarios"]
    result = execute_scenarios(root, sha, selected, runner=runner) if run else (
        contract_plan(root, sha, selected)
    )
    result["doctor_report_selection"] = selection
    result["diagnostic_evidence_gaps"] = selection["evidence_gaps"]
    result["all_end_to_end_certified"] = False
    result["phase_certified"] = False
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--scenario", action="append", choices=sorted(SCENARIOS))
    source.add_argument("--doctor-report", type=Path,
                        help="Existing Doctor optimization JSON under artifacts/")
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    output_target = (ROOT / args.output).resolve() if args.output else None
    if output_target is not None and (
        output_target.suffix.lower() != ".json"
        or not output_target.is_relative_to((ROOT / "artifacts").resolve())
    ):
        print(json.dumps({
            "status": "BLOCKED", "errors": ["OUTPUT_MUST_BE_ARTIFACT_JSON"],
            "candidate_sha": args.expected_sha,
            "tests_executed": False, "phase_certified": False,
        }))
        return 2
    if args.doctor_report is not None:
        from tools.atlas_doctor_lib.optimization_report import load
        try:
            report = load(ROOT, args.doctor_report)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            plan = {
                "status": "BLOCKED", "candidate_sha": args.expected_sha,
                "errors": ["INVALID_OR_UNREADABLE_DOCTOR_REPORT", type(exc).__name__],
                "tests_executed": False, "phase_certified": False,
            }
        else:
            plan = execute_doctor_report(
                ROOT, args.expected_sha, report or {}, run=args.run,
            )
    else:
        plan = execute_scenarios(ROOT, args.expected_sha, args.scenario) if args.run else (
            contract_plan(ROOT, args.expected_sha, args.scenario)
        )
    if output_target is not None:
        output_target.parent.mkdir(parents=True, exist_ok=True)
        output_target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0 if plan["status"] not in ("BLOCKED",) else 2


if __name__ == "__main__":
    raise SystemExit(main())
