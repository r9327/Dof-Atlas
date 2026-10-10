"""Run bounded, exact-SHA behavioral checks for Doctor's 18 capabilities.

Never conflates AST wiring with a behavioral PASS. No FULL, RAM or preload run.
Scenarios are opt-in in the dedicated CI workflow, not the application.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from tools.atlas_doctor_lib.capability_matrix import CAPABILITIES, capability_inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "doctor_18_certification"
METHODS = {
    "G01": ["tests.test_atlas_doctor_file_coverage.FileCoverageTests.test_gaps_are_reported_without_claiming_dead_code"],
    "G02": ["tests.test_atlas_doctor_graph_intelligence.GraphIntelligenceTests.test_current_sources_confirm_cycle_or_reduce_to_review"],
    "G03": ["tests.test_atlas_doctor_graph_intelligence.GraphIntelligenceTests.test_community_review_never_forces_merges"],
    "G04": ["tests.test_atlas_doctor_deep_intelligence.DeepIntelligenceTests.test_reachability_labels_unobserved_not_dead",
            "tests.test_atlas_doctor_deep_intelligence.DeepIntelligenceTests.test_json_lineage_to_ui_uses_only_source_confirmed_import_edges"],
    "R05": ["tests.test_atlas_doctor_runtime_observation.RuntimeObservationTests.test_real_cross_file_function_call_is_recorded_by_symbol"],
    "R06": ["tests.test_atlas_doctor_runtime_observation.RuntimeObservationTests.test_dynamic_module_import_records_return_but_not_failed_import",
            "tests.test_atlas_doctor_runtime_observation.RuntimeObservationTests.test_real_source_file_open_is_attributed_to_test_script"],
    "R07": ["tests.test_atlas_doctor_qt_integration.DoctorRealQtSignalTests.test_real_qt_smoke_scenario_observes_callback_and_object_destruction"],
    "R08": ["tests.test_atlas_doctor_qt_integration.DoctorRealQtSignalTests.test_real_qt_smoke_scenario_observes_callback_and_object_destruction",
            "tests.test_atlas_doctor_runtime_observation.RuntimeObservationTests.test_qt_worker_unpaired_is_review_and_scenarios_do_not_cancel_each_other"],
    "R09": ["tests.test_atlas_doctor_runtime_observation.RuntimeObservationTests.test_bounded_qt_watch_distinguishes_invalid_cpp_wrapper_without_leak_claim"],
    "C10": ["tests.test_atlas_doctor_change_intelligence.ChangeIntelligenceTests.test_deleted_module_import_is_proven_and_linenumbered"],
    "C11": ["tests.test_atlas_doctor_source_impact.SourceImpactTests.test_static_relative_import_and_literal_dynamic_lead_are_separate"],
    "C12": ["tests.test_atlas_doctor_refactor_simulation.RefactorSimulationTests.test_simulation_preserves_hard_validation_and_never_edits"],
    "C13": ["tests.test_atlas_doctor_scenario_trends.DoctorScenarioTrendTests.test_repeated_absence_is_review_not_functional_regression"],
    "T14": ["tests.test_atlas_doctor_test_intelligence.TestCostEvidenceTests.test_advisory_order_keeps_all_required_groups_and_full_suite"],
    "T15": ["tests.test_atlas_doctor_test_intelligence.TestCostEvidenceTests.test_real_successful_costs_exclude_reused_full_and_failures"],
    "T16": ["tests.test_atlas_doctor_scenario_coverage.ScenarioCoverageTests.test_multiple_scenarios_accumulate_only_positive_exact_sha_coverage"],
    "U17": ["tests.test_atlas_doctor_graph_ui.DoctorGraphUiTests.test_interactive_view_has_real_navigation_and_filters",
            "tests.test_atlas_doctor_graph_ui.DoctorGraphUiTests.test_generated_interactive_javascript_passes_node_syntax_check"],
    "U18": ["tests.test_atlas_doctor_live_graph.LiveGraphTests.test_loopback_api_only_and_404",
            "tests.test_atlas_doctor_live_graph.LiveGraphTests.test_live_graph_adds_actual_local_import_edges_without_graph_rebuild"],
}
SCENARIOS = {
    "qt": {"qt_callback_invoked", "qt_destroyed_observed", "qt_worker_started",
           "qt_worker_finished", "module_import_returned"},
    "equipment": {"qt_destroyed_observed", "json_ui_bound", "qt_native_snapshot"},
    "encyclopedia": {"qt_destroyed_observed", "json_ui_bound", "qt_native_snapshot"},
    "webengine": {"qt_native_snapshot", "weak_watch_snapshot"},
}
SCENARIO_DEPENDENTS = {
    "qt": {"R07", "R08"},
    "equipment": {"R09"},
    "encyclopedia": {"G04"},
    "webengine": {"R09"},
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def call(label: str, args: list[str], *, timeout: int = 150) -> dict:
    start = time.monotonic()
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env=os.environ.copy())
        stdout, stderr, code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as ex:
        stdout = str(ex.stdout or "")
        stderr = str(ex.stderr or "") + "\nTIMEOUT"
        code = 124
    filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", label) + ".log"
    (OUT / filename).write_text(
        "COMMAND: " + " ".join(args) + "\nEXIT: " + str(code) +
        "\nSTDOUT:\n" + stdout + "\nSTDERR:\n" + stderr, encoding="utf-8")
    return {"exit_code": code, "seconds": round(time.monotonic() - start, 2),
            "stdout": stdout, "stderr": stderr, "log": filename}


def check_graph(head: str) -> dict:
    path = ROOT / "graphify-out" / "graph.json"
    if not path.is_file():
        return {"status": "FAIL", "reason": "Graphify exact-SHA output missing"}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        tracked = {
            p.replace("\\", "/") for p in
            git("ls-files", "--", "*.py").splitlines() if p
        }
        represented = {x["source_file"].replace("\\", "/") for x in d.get("nodes", [])
                       if isinstance(x.get("source_file"), str)
                       and x["source_file"].endswith(".py")}
        missing = sorted(tracked - represented)
        ok = d.get("built_at_commit") == head and bool(tracked) and not missing \
            and bool(d.get("nodes")) and bool(d.get("links", d.get("edges")))
        return {"status": "PASS" if ok else "FAIL", "graph_sha": d.get("built_at_commit"),
                "files_covered": len(tracked) - len(missing), "tracked_files": len(tracked),
                "missing_files": missing[:20], "nodes": len(d.get("nodes", [])),
                "relations": len(d.get("links", d.get("edges", [])))}
    except (OSError, ValueError, TypeError, KeyError) as ex:
        return {"status": "FAIL", "reason": repr(ex)}


def run_unittest(ident: str, targets: list[str]) -> dict:
    result = call(ident, [sys.executable, "-m", "unittest", "-v", *targets])
    output = result["stdout"] + "\n" + result["stderr"]
    found = re.search(r"Ran (\d+) tests? in", output)
    ran = int(found.group(1)) if found else 0
    skipped = bool(re.search(r"\bskipped\b|skip\s*=", output, flags=re.I))
    success = result["exit_code"] == 0 and ran >= len(targets) \
        and bool(re.search(r"(?m)^OK(?:\s|\(|$)", output)) and not skipped
    return {"status": "PASS" if success else "FAIL", "tests_run": ran,
            "skipped": skipped, "seconds": result["seconds"], "log": result["log"],
            "reason": "" if success else "Test failed, missing or skipped"}


def run_scenario(name: str, head: str) -> dict:
    result = call("scenario_" + name, [sys.executable, "-m", "tools.atlas_doctor",
                                      "capture-ui", name, "--json"], timeout=180)
    try:
        payload = json.loads(result["stdout"])
        trace = json.loads(Path(payload["trace_path"]).read_text(encoding="utf-8"))
        types = {event.get("type") for event in trace.get("events", [])
                 if isinstance(event, dict)}
        missing = sorted(SCENARIOS[name] - types)
        ok = (result["exit_code"] == 0 and payload["status"] == "RECORDED"
              and payload.get("truncated") is False
              and trace.get("candidate_sha") == head
              and trace.get("worktree_clean") is True
              and trace.get("truncated") is False
              and not missing)
        return {"status": "PASS" if ok else "FAIL", "missing_events": missing,
                "event_count": len(trace.get("events", [])),
                "trace_sha": trace.get("candidate_sha"), "log": result["log"],
                "seconds": result["seconds"],
                "limits": "Opt-in offscreen scenario: not exhaustive production UI or RAM proof"}
    except (OSError, ValueError, KeyError, TypeError) as ex:
        return {"status": "FAIL", "reason": str(ex), "log": result["log"],
                "seconds": result["seconds"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD")
    inventory = capability_inventory(ROOT)
    rows = {}
    valid_ids = {row[0] for row in CAPABILITIES}
    if set(METHODS) != valid_ids or len(METHODS) != 18:
        raise SystemExit("Certification mapping does not match canonical 18 capabilities")
    graph = check_graph(head)
    print("Exact SHA:", head, "| graph:", graph["status"], flush=True)
    for ident, _, name, _, _ in CAPABILITIES:
        rows[ident] = {"name": name, "methods": METHODS[ident],
                       **run_unittest(ident, METHODS[ident])}
        print(f"{ident}: {rows[ident]['status']} ({rows[ident]['tests_run']} tests)",
              flush=True)
    scenarios = {}
    for name in SCENARIOS:
        scenarios[name] = run_scenario(name, head)
        print("Scenario", name, scenarios[name]["status"], flush=True)
        if scenarios[name]["status"] != "PASS":
            for ident in SCENARIO_DEPENDENTS.get(name, set()):
                rows[ident]["status"] = "FAIL"
                rows[ident].setdefault("blocking_scenarios", []).append(name)
    if graph["status"] != "PASS":
        for ident in ("G01", "G02", "G03", "U17"):
            rows[ident]["status"] = "FAIL"
            rows[ident].setdefault("blocking_checks", []).append("graph_exact_sha")
    if inventory["status"] != "REVIEW_PENDING_FINAL_CERTIFICATION":
        for row in rows.values():
            row["status"] = "FAIL"
            row.setdefault("blocking_checks", []).append("canonical_ast_wiring")
    all_ok = (all(row["status"] == "PASS" for row in rows.values())
              and all(v["status"] == "PASS" for v in scenarios.values())
              and graph["status"] == "PASS")
    report = {"candidate_sha": head, "status": "PASS" if all_ok else "FAIL",
              "passed": sum(r["status"] == "PASS" for r in rows.values()),
              "total": 18, "graph": graph,
              "canonical_wiring": {"source_present": inventory["source_present"],
                                  "call_sites_wired": inventory["call_sites_wired"],
                                  "status": inventory["status"]},
              "capabilities": rows, "scenarios": scenarios,
              "not_claimed": ["FULL suite certification", "RAM/preload budgets",
                              "all manual Qt/WebEngine interactions",
                              "absence of dead code", "production memory ownership"]}
    (OUT / "verdict.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                      + "\n", encoding="utf-8")
    lines = [f"# Doctor 18-capability evidence — {head}",
             "", f"**Verdict: {report['status']} — {report['passed']}/18 PASS**",
             "", "| ID | Capability | Verdict | Tests | Evidence |",
             "|---|---|---|---:|---|"]
    for ident, _, name, _, _ in CAPABILITIES:
        row = rows[ident]
        lines.append(f"| {ident} | {name} | {row['status']} | {row['tests_run']} | {row['log']} |")
    lines += ["", "Scenarios: " + ", ".join(f"{n}={v['status']}"
                                           for n, v in scenarios.items()),
              "", "No FULL/RAM/preload rerun. PASS here certifies only the named automated",
              "tests and isolated offscreen scenarios; manual UI and cumulative phase",
              "gates remain separate."]
    (OUT / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
