"""Correlation Doctor: provenance, safety, and non-causal diagnostics."""
from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.diagnostic_correlation import (
    _catalog_tools, correlate_diagnostics, plan_investigation,
)
from tools.atlas_doctor_lib.optimization_report import optimization_report, render_markdown

SHA = "a" * 40
OTHER = "b" * 40


def app(**changes):
    value = {
        "git_head": SHA, "status": "PASS", "preload_ms": 9000,
        "idle_tree_rss_delta_mib": 16.0,
        "revisit_comparison": {
            "quests": {"home_tree_delta_first_to_last_mib": 15.0},
        },
        "cost_attribution": {
            "status": "OBSERVED", "shares": [
                {"phase": "functional_preload", "wall_ms": 9300.0},
            ],
        },
        "preload_status": "PASS", "routes": [], "idle_samples": [{}],
    }
    value.update(changes)
    return value


def catalog() -> dict:
    def row(path, capability, *, safe=True, ready=True, preferred=True):
        return {
            "path": path, "invocation": "py -3.13 -m " + path[:-3].replace("/", "."),
            "capabilities": [capability],
            "cost_hint": "cheap",
            "side_effects": "read_only",
            "preferred_for_agent": preferred,
            "safe_for_agent": safe,
            "automation_ready": ready,
            "readiness_score": 100 if ready else 10,
        }

    return {"tools": [
        row("tools/atlas_doctor.py", "performance"),
        row("tools/quest_scan.py", "quest_data", safe=False),
        row("tools/coverage_scan.py", "coverage"),
        row("tools/guide_integrity.py", "guide"),
        row("tools/atlas_integrity.py", "validation"),
        row("tools/graphify_reader.py", "graphify"),
        row("tools/ram_profile.py", "memory"),
        row("tools/runtime_trace_reader.py", "runtime_trace"),
        row("tools/untrusted_perf.py", "performance", safe=False),
    ]}


class DiagnosticCorrelationTests(unittest.TestCase):
    def test_same_sha_multi_signal_correlation_is_a_hypothesis_only(self):
        result = correlate_diagnostics(SHA, app(), catalog_report=catalog())
        self.assertEqual(result["status"], "REVIEW")
        self.assertFalse(result["causes_proven"])
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["tools_executed"])
        self.assertFalse(result["certification"])
        by_id = {h["id"]: h for h in result["hypotheses"]}
        self.assertIn("PRELOAD_WALL_CORRELATION", by_id)
        self.assertIn("HOME_REVISIT_CORRELATION", by_id)
        preload = by_id["PRELOAD_WALL_CORRELATION"]
        self.assertEqual(preload["inference"], "CORRELATION_NOT_CAUSATION")
        self.assertEqual(
            [x["path"] for x in preload["tool_plan"]["selected"]],
            ["tools/atlas_doctor.py", "tools/runtime_trace_reader.py",
             "tools/coverage_scan.py"],
        )
        self.assertEqual(preload["tool_plan"]["unresolved_capabilities"], ["quest_data"])
        self.assertFalse(preload["root_cause_proven"])

    def test_home_drift_selects_memory_tools_but_never_executes(self):
        result = correlate_diagnostics(SHA, app(), catalog_report=catalog())
        row = next(h for h in result["hypotheses"] if h["id"] == "HOME_REVISIT_CORRELATION")
        self.assertEqual(
            [t["capability"] for t in row["tool_plan"]["selected"]],
            ["memory", "performance", "runtime_trace", "coverage"],
        )
        self.assertTrue(row["tool_plan"]["not_executed"])
        self.assertFalse(row["root_cause_proven"])

    def test_investigation_deduplicates_tools_and_preserves_approval_boundaries(self):
        result = correlate_diagnostics(SHA, app(), catalog_report=catalog())
        plan = result["investigation_plan"]
        self.assertEqual(plan["status"], "REVIEW_REQUIRED")
        paths = [step["tool"] for step in plan["steps"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(paths.count("tools/atlas_doctor.py"), 1)
        self.assertTrue(all(step["requires_same_sha"] for step in plan["steps"]))
        self.assertTrue(all(not step["mutation_authorized"] for step in plan["steps"]))
        self.assertFalse(plan["certification_granted"])
        self.assertFalse(plan["tools_executed"])
        self.assertEqual(plan["verification_contract"]["final_phase_certification"],
                         "REQUIRED_NOT_RUN")

    def test_unsafe_or_mutating_tool_cannot_enter_read_only_investigation(self):
        report = catalog()
        for row in report["tools"]:
            if row["path"] == "tools/atlas_doctor.py":
                row["side_effects"] = "repo_mutation_explicit"
            if row["path"] == "tools/untrusted_perf.py":
                row["safe_for_agent"] = False
        result = correlate_diagnostics(SHA, app(), catalog_report=report)
        plans = [h["tool_plan"] for h in result["hypotheses"]]
        self.assertTrue(all(
            "tools/atlas_doctor.py" not in {r["path"] for r in p["selected"]}
            for p in plans
        ))
        self.assertTrue(any("performance" in p["unresolved_capabilities"]
                            for p in plans))

    def test_stale_evidence_must_not_generate_an_executable_plan(self):
        result = correlate_diagnostics(SHA, app(git_head=OTHER),
                                       catalog_report=catalog())
        plan = result["investigation_plan"]
        self.assertEqual(plan["status"], "BLOCKED_MISSING_EVIDENCE")
        self.assertEqual(plan["steps"], [])
        self.assertFalse(plan["certification_granted"])

    def test_validation_is_not_scheduled_before_code_complete(self):
        guide = {"observed_sha": SHA, "status": "PASS", "bottleneck_candidates": [
            {"kind": "python_method", "location": "Guide.load", "cost_ms": 250},
        ]}
        result = correlate_diagnostics(SHA, app(), guides=guide,
                                       catalog_report=catalog())
        by_capability = {c: step for step in result["investigation_plan"]["steps"]
                         for c in step["capabilities"]}
        self.assertEqual(by_capability["validation"]["phase"],
                         "VALIDATION_AFTER_CODE_COMPLETE")
        self.assertTrue(by_capability["validation"]["requires_prior_evidence_review"])

    def test_adaptive_probes_reuse_canonical_benchmarks_and_keep_sentinels(self):
        guide = {"observed_sha": SHA, "status": "PASS", "bottleneck_candidates": [
            {"kind": "python_method", "location": "Guide.render",
             "cost_ms": 180},
        ]}
        result = correlate_diagnostics(
            SHA, app(), guides=guide, catalog_report=catalog(),
        )
        plan = result["investigation_plan"]
        scenarios = {x["scenario"]: x for x in plan["adaptive_benchmark_probes"]}
        self.assertEqual(set(scenarios), {
            "preload_cold_warm", "home_module_home_stabilized",
            "guides_cold_warm_regression",
        })
        self.assertEqual(scenarios["preload_cold_warm"]["owner"],
                         "tools.atlas_doctor perf --app")
        self.assertEqual(scenarios["guides_cold_warm_regression"]["owner"],
                         "tools.atlas_doctor perf --deep")
        self.assertTrue(all(p["status"] == "NOT_RUN" and p["repeat_count_min"] >= 3
                            for p in scenarios.values()))
        self.assertTrue(plan["all_required_certification_scenarios_retained"])
        self.assertFalse(plan["tests_executed"])

    def test_report_shows_adaptive_investigation_without_claiming_pass(self):
        doc = optimization_report(SHA, app(), tool_catalog_report=catalog())
        rendered = render_markdown(doc)
        self.assertIn("Plan de décision adaptatif", rendered)
        self.assertIn("preload_cold_warm", rendered)
        self.assertEqual(doc["diagnostic_correlation"]["investigation_plan"]
                         ["verification_contract"]["final_phase_certification"],
                         "REQUIRED_NOT_RUN")
        self.assertIn("REQUIRED_NOT_RUN", rendered)
        self.assertFalse(doc["diagnostic_correlation"]["investigation_plan"]
                         ["certification_granted"])

    def test_tool_selection_budget_reports_skipped_capabilities(self):
        capabilities = tuple("cap_" + str(i) for i in range(7))
        report = {"tools": [
            {
                "path": "tools/a" + str(i) + ".py",
                "invocation": "tool " + str(i),
                "capabilities": [capability],
                "safe_for_agent": True, "automation_ready": True,
                "preferred_for_agent": True, "cost_hint": "cheap",
                "side_effects": "read_only", "readiness_score": 100,
            }
            for i, capability in enumerate(capabilities)
        ]}
        result = _catalog_tools(capabilities, report)
        self.assertEqual(len(result["selected"]), 5)
        self.assertEqual(
            result["unresolved_capabilities"],
            ["TOOL_BUDGET_EXCEEDED:cap_5", "TOOL_BUDGET_EXCEEDED:cap_6"],
        )
        self.assertEqual(result["status"], "PARTIAL_TOOL_COVERAGE")

    def test_large_plan_never_silently_discards_tools(self):
        hypotheses = [
            {"id": "H" + str(i), "tool_plan": {
                "unresolved_capabilities": [], "selected": [
                    {"path": "tools/t" + str(i) + "_" + str(j) + ".py",
                     "invocation": "not executed", "capability": "coverage",
                     "cost_hint": "cheap"}
                    for j in range(5)
                ]}}
            for i in range(10)
        ]
        result = plan_investigation(SHA, hypotheses, [])
        self.assertEqual(result["tools_considered"], 50)
        self.assertEqual(len(result["steps"]), 32)
        self.assertTrue(result["tools_truncated"])
        self.assertIn("TOOL_PLAN_TRUNCATED:18", result["unresolved"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertFalse(result["tools_executed"])

    def test_stale_benchmark_is_blocked_not_recycled_into_positive_diagnosis(self):
        result = correlate_diagnostics(SHA, app(git_head=OTHER),
                                       catalog_report=catalog())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["hypotheses"], [])
        self.assertEqual(result["evidence_gaps"], ["app: STALE_OR_NOT_PASS"])

    def test_failed_benchmark_is_blocked(self):
        result = correlate_diagnostics(SHA, app(status="FAIL"),
                                       catalog_report=catalog())
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_cost_attribution_cannot_confirm_preload_correlation(self):
        result = correlate_diagnostics(SHA, app(cost_attribution={"status": "BLOCKED"}))
        self.assertNotIn(
            "PRELOAD_WALL_CORRELATION",
            {row["id"] for row in result["hypotheses"]},
        )
        self.assertIn(
            "preload: MISSING_VALID_COST_ATTRIBUTION", result["evidence_gaps"],
        )

    def test_stale_guide_hotspot_ignored_even_when_value_is_large(self):
        stale = {"observed_sha": OTHER, "status": "PASS", "bottleneck_candidates": [
            {"kind": "python_method", "location": "Old Guide", "cost_ms": 25000},
        ]}
        result = correlate_diagnostics(SHA, app(), guides=stale)
        self.assertNotIn("GUIDE_METHOD_HOTSPOT",
                         {row["id"] for row in result["hypotheses"]})
        self.assertIn("guides: STALE_OR_NOT_PASS", result["evidence_gaps"])

    def test_same_sha_guide_hotspot_routes_to_guide_capability(self):
        guide = {"observed_sha": SHA, "status": "PASS", "bottleneck_candidates": [
            {"kind": "python_method", "location": "Guide.step_build",
             "cost_ms": 170.0},
        ]}
        result = correlate_diagnostics(SHA, app(), guides=guide,
                                       catalog_report=catalog())
        row = next(x for x in result["hypotheses"] if x["id"] == "GUIDE_METHOD_HOTSPOT")
        self.assertEqual(row["observations"][0]["value"], 170.0)
        self.assertEqual(row["tool_plan"]["selected"][0]["path"],
                         "tools/guide_integrity.py")
        self.assertFalse(row["tool_plan"]["selected"][0]["automation_executed"])

    def test_guide_and_navigation_reports_correlate_without_proving_causality(self):
        guide = {"observed_sha": SHA, "status": "PASS", "bottleneck_candidates": [
            {"kind": "python_method", "location": "Guide.load", "cost_ms": 250.0},
        ]}
        data = app(cost_attribution={
            "status": "OBSERVED",
            "shares": [{"phase": "functional_preload", "wall_ms": 9300}],
            "repeated_work_suspects": [
                {"route": "guide_ultime", "max_warm_ms": 425},
            ],
        })
        result = correlate_diagnostics(
            SHA, data, guides=guide, catalog_report=catalog(),
        )
        row = next(x for x in result["hypotheses"] if x["id"] == "GUIDE_HOTSPOT_AND_REVISIT")
        self.assertEqual(row["priority"], "P0")
        self.assertEqual(len(row["observations"]), 2)
        self.assertEqual(row["observations"][0]["source"], "guides")
        self.assertEqual(row["observations"][1]["source"], "app_navigation")
        self.assertFalse(row["root_cause_proven"])

    def test_memory_drift_without_revisit_is_not_labeled_a_leak(self):
        result = correlate_diagnostics(SHA, app(revisit_comparison={}))
        self.assertNotIn("HOME_REVISIT_CORRELATION",
                         {row["id"] for row in result["hypotheses"]})
        self.assertIn("home_ram: MISSING_REVISIT_CORROBORATION",
                      result["evidence_gaps"])

    def test_nan_boolean_values_and_unavailable_tool_catalog_do_not_infer_cause(self):
        result = correlate_diagnostics(
            SHA, app(preload_ms=True, idle_tree_rss_delta_mib=float("nan"),
                     cost_attribution={"status": "OBSERVED", "shares": [
                         {"phase": "functional_preload", "wall_ms": 50000}]}),
            catalog_report={"tools": None},
        )
        self.assertEqual(result["hypotheses"], [])
        self.assertEqual(result["status"], "NO_CORRELATION")

    def test_invalid_sha_rejected(self):
        with self.assertRaises(ValueError):
            correlate_diagnostics("abc", app())

    def test_report_uses_correlations_without_claiming_certification(self):
        report = optimization_report(
            SHA, app(), tool_catalog_report=catalog(),
        )
        correlation = report["diagnostic_correlation"]
        self.assertEqual(correlation["status"], "REVIEW")
        self.assertFalse(report["is_certification"])
        rendered = render_markdown(report)
        self.assertIn("Corrélation Doctor", rendered)
        self.assertIn("PRELOAD_WALL_CORRELATION", rendered)
        self.assertIn("non exécuté", rendered)


if __name__ == "__main__":
    unittest.main()
