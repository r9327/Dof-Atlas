"""Correlation Doctor: provenance, safety, and non-causal diagnostics."""
from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.diagnostic_correlation import (
    _catalog_tools, correlate_diagnostics, plan_investigation,
    scenario_contract_recommendations,
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
        self.assertEqual(preload["evidence_strength"], "SINGLE_REPORT_LEAD")
        self.assertFalse(preload["root_cause_proven"])
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

    def test_shared_tool_keeps_all_capabilities_without_redundant_invocations(self):
        report = {"tools": [{
            "path": "tools/specialist.py", "invocation": "py -m tools.specialist",
            "capabilities": ["memory", "runtime_trace", "performance"],
            "safe_for_agent": True, "automation_ready": True,
            "preferred_for_agent": True, "cost_hint": "cheap",
            "side_effects": "read_only", "readiness_score": 100,
        }]}
        planned = _catalog_tools(("memory", "runtime_trace", "performance"), report)
        self.assertEqual(len(planned["selected"]), 1)
        self.assertEqual(planned["selected"][0]["capabilities"],
                         ["memory", "runtime_trace", "performance"])
        graph = plan_investigation(SHA, [{
            "id": "RAM", "tool_plan": planned,
        }], [])
        self.assertEqual(len(graph["steps"]), 1)
        self.assertEqual(graph["steps"][0]["capabilities"],
                         ["memory", "runtime_trace", "performance"])
        self.assertFalse(graph["tools_executed"])

    def test_low_cost_multicapability_specialist_beats_expensive_single_use(self):
        report = {"tools": [
            {
                "path": "tools/preferred_expensive.py",
                "invocation": "inspect heavy", "capabilities": ["performance"],
                "cost_hint": "expensive", "preferred_for_agent": True,
                "safe_for_agent": True, "automation_ready": True,
                "side_effects": "read_only", "readiness_score": 100,
            },
            {
                "path": "tools/reuse_cheap.py",
                "invocation": "inspect focused",
                "capabilities": ["performance", "runtime_trace", "memory"],
                "cost_hint": "cheap", "preferred_for_agent": False,
                "safe_for_agent": True, "automation_ready": True,
                "side_effects": "read_only", "readiness_score": 90,
            },
            {
                "path": "tools/mutates.py",
                "invocation": "write",
                "capabilities": ["memory", "runtime_trace"],
                "cost_hint": "cheap", "preferred_for_agent": True,
                "safe_for_agent": True, "automation_ready": True,
                "side_effects": "repo_mutation_explicit", "readiness_score": 100,
            },
        ]}
        result = _catalog_tools(
            ("performance", "runtime_trace", "memory"), report,
        )
        self.assertEqual(
            [tool["path"] for tool in result["selected"]], ["tools/reuse_cheap.py"],
        )
        self.assertEqual(
            result["selected"][0]["capabilities"],
            ["performance", "runtime_trace", "memory"],
        )
        self.assertEqual(result["unresolved_capabilities"], [])
        self.assertTrue(result["not_executed"])

    def test_full_tool_budget_still_covers_existing_shared_capability(self):
        capabilities = tuple("cap_" + str(i) for i in range(6))
        inventory = [
            {
                "path": "tools/t" + str(i) + ".py",
                "invocation": "read " + str(i),
                "capabilities": (["cap_0", "cap_5"] if i == 0
                                 else ["cap_" + str(i)]),
                "safe_for_agent": True, "automation_ready": True,
                "preferred_for_agent": True,
                "side_effects": "read_only", "cost_hint": "cheap",
                "readiness_score": 100,
            }
            for i in range(5)
        ]
        result = _catalog_tools(capabilities, {"tools": inventory})
        self.assertEqual(len(result["selected"]), 5)
        self.assertEqual(result["unresolved_capabilities"], [])
        self.assertEqual(result["selected"][0]["capabilities"],
                         ["cap_0", "cap_5"])

    def test_unknown_tool_cost_is_not_assumed_free(self):
        plan = plan_investigation(SHA, [{
            "id": "X", "tool_plan": {
                "selected": [{
                    "path": "tools/unknown.py", "invocation": "tool",
                    "capability": "validation", "cost_hint": "unknown",
                }],
                "unresolved_capabilities": [],
            },
        }], [])
        self.assertEqual(plan["steps"][0]["phase"],
                         "VALIDATION_AFTER_CODE_COMPLETE")

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

    def test_phase8_cold_details_use_real_rendered_fixture_and_same_sha(self):
        phase8 = {"metrics": {
            "git_head": SHA, "deep_first_content": {
                "all_details_rendered": True, "quest_id": 18,
                "achievement_id": 20, "guide_id": "bonta",
            },
            "deep_quest_detail_ms": 7080.0,
            "deep_achievement_detail_ms": 5430.0,
            "deep_guide_detail_ms": 2480.0,
            "deep_first_content_total_ms": 14990.0,
        }}
        result = correlate_diagnostics(
            SHA, app(), phase8=phase8, catalog_report=catalog(),
        )
        rows = {h["id"]: h for h in result["hypotheses"]}
        self.assertEqual(rows["COLD_QUEST_DETAIL"]["priority"], "P0")
        self.assertEqual(rows["COLD_ACHIEVEMENT_DETAIL"]["priority"], "P0")
        self.assertEqual(rows["COLD_GUIDE_DETAIL"]["priority"], "P1")
        self.assertFalse(rows["COLD_QUEST_DETAIL"]["root_cause_proven"])
        plan = result["investigation_plan"]
        self.assertIn("phase8_deep_first_use_same_fixture", {
            item["scenario"] for item in plan["adaptive_benchmark_probes"]
        })
        self.assertFalse(plan["tools_executed"])

    def test_correlated_symptoms_select_real_scenario_runner_contracts(self):
        findings = [
            {"id": "COLD_QUEST_DETAIL"},
            {"id": "COLD_ACHIEVEMENT_DETAIL"},
            {"id": "HOME_REVISIT_CORRELATION"},
            {"id": "PRELOAD_WALL_CORRELATION"},
        ]
        plan = scenario_contract_recommendations(findings)
        self.assertEqual(plan["status"], "PLANNED_NOT_RUN")
        self.assertEqual(
            [row["scenario"] for row in plan["selected"]],
            ["startup_preload", "home_qt_lifecycle", "success_cold_detail",
             "quest_cold_detail"],
        )
        self.assertEqual(plan["uncovered_hypotheses"], [])
        self.assertTrue(all(row["execution_status"] == "NOT_RUN"
                            for row in plan["selected"]))
        self.assertTrue(all(row["required_sha_check"] for row in plan["selected"]))
        self.assertFalse(plan["tests_executed"])
        self.assertFalse(plan["perf_benchmarks_executed"])
        self.assertFalse(plan["certification_granted"])

    def test_all_five_perf_scenarios_fit_the_existing_execution_budget(self):
        result = scenario_contract_recommendations([
            {"id": "PRELOAD_WALL_CORRELATION"},
            {"id": "HOME_REVISIT_CORRELATION"},
            {"id": "COLD_ACHIEVEMENT_DETAIL"},
            {"id": "SUCCESS_MAIN_THREAD_SUBPROCESS"},
            {"id": "COLD_QUEST_DETAIL"},
            {"id": "COLD_GUIDE_DETAIL"},
        ])
        self.assertEqual(len(result["selected"]), 5)
        self.assertEqual(result["uncovered_hypotheses"], [])
        self.assertEqual(result["status"], "PLANNED_NOT_RUN")
        self.assertEqual(result["selected"][2]["scenario"], "success_cold_detail")
        self.assertIn("SUCCESS_MAIN_THREAD_SUBPROCESS",
                      result["selected"][2]["covered_hypotheses"])
        self.assertFalse(result["certification_granted"])

    def test_unknown_hypotheses_are_reported_not_silently_certified(self):
        plan = scenario_contract_recommendations([
            {"id": "UNMAPPED_SPECIALIST"}, {"id": "COLD_GUIDE_DETAIL"},
        ])
        self.assertEqual(plan["status"], "PARTIAL_COVERAGE")
        self.assertEqual(plan["uncovered_hypotheses"], ["UNMAPPED_SPECIALIST"])
        self.assertEqual(plan["selected"][0]["scenario"], "guide_cold_detail")
        self.assertFalse(plan["certification_granted"])
        self.assertEqual(scenario_contract_recommendations([])["status"], "NOT_SELECTED")

    def test_tools_have_just_one_catalog_selection_per_capability(self):
        # The integration remains delegated to the canonical selector; a
        # manifest with malformed metadata must be an explicit unavailable
        # capability rather than an unhandled exception.
        report = {"tools": [{
            "path": "tools/malformed.py", "capabilities": ["memory"],
            "safe_for_agent": True, "automation_ready": True,
        }]}
        routed = _catalog_tools(("memory",), report)
        self.assertEqual(routed["selected"], [])
        self.assertEqual(routed["unresolved_capabilities"],
                         ["INVALID_TOOL_METADATA:memory"])

    def test_main_thread_success_wait_is_measured_not_guessed(self):
        phase8 = {"metrics": {
            "git_head": SHA,
            "deep_first_content": {
                "all_details_rendered": True,
                "quest_id": 18, "achievement_id": 20, "guide_id": "bonta",
                "achievement_detail_phases_ms": {
                    "provider_last_detail_breakdown_ms": {
                        "thread": "MainThread", "subprocess_path_used": True,
                        "synchronous_subprocess_ms": 5100,
                        "decode_ms": 72, "cache_source": "cold",
                    }
                },
            },
            "deep_quest_detail_ms": 7080,
            "deep_achievement_detail_ms": 5430,
            "deep_guide_detail_ms": 2480,
            "deep_first_content_total_ms": 14990,
        }}
        result = correlate_diagnostics(SHA, app(), phase8=phase8,
                                       catalog_report=catalog())
        evidence = {item["id"]: item for item in result["hypotheses"]}
        self.assertEqual(evidence["SUCCESS_MAIN_THREAD_SUBPROCESS"]["priority"], "P0")
        self.assertEqual(
            evidence["SUCCESS_MAIN_THREAD_SUBPROCESS"]["evidence_strength"],
            "SINGLE_REPORT_LEAD",
        )
        self.assertEqual(
            evidence["SUCCESS_MAIN_THREAD_SUBPROCESS"]["observations"][1]["value"],
            5100,
        )
        self.assertFalse(evidence["SUCCESS_MAIN_THREAD_SUBPROCESS"]["root_cause_proven"])

        # Misaligned subprocess timings are not laundered into a diagnosis.
        phase8["metrics"]["deep_first_content"]["achievement_detail_phases_ms"][
            "provider_last_detail_breakdown_ms"
        ]["synchronous_subprocess_ms"] = 9000
        invalid = correlate_diagnostics(SHA, app(), phase8=phase8)
        self.assertIn("phase8_first_use: SUCCESS_WORKER_TIMING_MISMATCH",
                      invalid["evidence_gaps"])
        self.assertNotIn("SUCCESS_MAIN_THREAD_SUBPROCESS",
                         {x["id"] for x in invalid["hypotheses"]})

        # A worker-thread execution is not a blocking UI call.
        phase8["metrics"]["deep_first_content"]["achievement_detail_phases_ms"][
            "provider_last_detail_breakdown_ms"
        ].update({"synchronous_subprocess_ms": 5100, "thread": "atlas-achievement"})
        background = correlate_diagnostics(SHA, app(), phase8=phase8)
        self.assertNotIn("SUCCESS_MAIN_THREAD_SUBPROCESS",
                         {x["id"] for x in background["hypotheses"]})

    def test_phase8_incomplete_or_stale_data_cannot_claim_first_detail_diagnosis(self):
        complete = {
            "git_head": SHA,
            "deep_first_content": {
                "all_details_rendered": True, "quest_id": 18,
                "achievement_id": 20, "guide_id": "bonta",
            },
            "deep_quest_detail_ms": 7000.0,
            "deep_achievement_detail_ms": 5000.0,
            "deep_guide_detail_ms": 3000.0,
            "deep_first_content_total_ms": 15000.0,
        }
        altered = (
            ({**complete, "git_head": OTHER}, "phase8_first_use: STALE_OR_INVALID"),
            ({**complete, "deep_first_content": {
                **complete["deep_first_content"], "all_details_rendered": False,
            }}, "phase8_first_use: DETAILS_NOT_RENDERED"),
            ({**complete, "deep_quest_detail_ms": True},
             "phase8_first_use: INCOMPLETE_OR_INVALID_TIMINGS"),
            ({**complete, "deep_first_content_total_ms": 10000.0},
             "phase8_first_use: INVALID_TIMING_ACCOUNTING"),
        )
        for metrics, missing in altered:
            with self.subTest(missing=missing):
                result = correlate_diagnostics(
                    SHA, app(), phase8={"metrics": metrics},
                )
                self.assertIn(missing, result["evidence_gaps"])
                self.assertFalse(any(
                    row["id"].startswith("COLD_") for row in result["hypotheses"]
                ))

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
        self.assertEqual(row["evidence_strength"], "SINGLE_REPORT_LEAD")
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
        self.assertEqual(row["evidence_strength"], "MULTI_SPECIALIST_LEAD")
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
