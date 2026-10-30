"""Doctor optimization-report contracts: no fabricated savings or certification."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.optimization_report import optimization_report, render_markdown, generate

HEAD = "a" * 40
OLD = "b" * 40


def sample(sha=HEAD, **kwargs):
    report = {
        "git_head": sha, "status": "PASS", "qt_platform": "offscreen",
        "cycles": 3, "one_core_requested": False, "idle_seconds_requested": 60,
        "home_stabilization_wait_ms": 750, "expected_routes": ["quests"],
        "preload_status": "PASS", "preload_ms": 2000,
        "constructor_to_visible_ms": 100, "elapsed_seconds": 8,
        "peak_process_tree_rss_mib": 200, "idle_tree_rss_delta_mib": 0,
        "idle_samples": [{"offset_seconds": 60}],
        "routes": [{"id": "quests", "cycle": 1, "status": "PASS"}],
        "cost_attribution": {"status": "OBSERVED", "shares": [
            {"phase": "functional_preload", "wall_ms": 2000,
             "wall_pct_of_entire_probe": 25, "process_cpu_ms": 500,
             "cpu_pct_of_measured_process_cpu": 50}],
            "repeated_work_suspects": []},
    }
    report.update(kwargs)
    return report


class OptimizationReportTests(unittest.TestCase):
    def test_costs_ranked_but_not_certified_or_fake_rss_split(self):
        doc = optimization_report(HEAD, sample(
            peak_process_tree_rss_mib=316, idle_tree_rss_delta_mib=15))
        self.assertEqual(doc["status"], "DIAGNOSTIC_READY")
        self.assertFalse(doc["is_certification"])
        self.assertIsNone(doc["memory"]["module_rss_percentages"])
        self.assertEqual(doc["priority_findings"][0]["id"], "RAM_PEAK")
        self.assertIn("RAM par module: NOT_MEASURED", render_markdown(doc))

    def test_benchmark_home_wait_is_not_ranked_as_atlas_hotspot(self):
        app = sample(cost_attribution={"status": "OBSERVED", "shares": [
            {"phase": "home_return", "wall_ms": 52133,
             "wall_pct_of_entire_probe": 81.19},
            {"phase": "functional_preload", "wall_ms": 9416,
             "wall_pct_of_entire_probe": 14.67},
        ], "repeated_work_suspects": []})
        doc = optimization_report(HEAD, app)
        hot = next(x for x in doc["priority_findings"] if x["id"] == "HOT_PHASE")
        self.assertIn("functional_preload", hot["title"])
        self.assertEqual(doc["non_actionable_benchmark_phases"][0]["phase"], "home_return")
        self.assertIn("pauses forcées", render_markdown(doc))

    def test_repeated_suspect_never_promises_savings(self):
        app = sample(cost_attribution={"status": "OBSERVED",
            "shares": [{"phase": "quests", "wall_ms": 400,
                        "wall_pct_of_entire_probe": 5}],
            "repeated_work_suspects": [{"route": "quests", "max_warm_ms": 450}]})
        doc = optimization_report(HEAD, app)
        self.assertTrue(any(x["id"] == "REPEAT_quests" for x in doc["priority_findings"]))
        self.assertNotIn("estimated_saving", doc)

    def test_stale_current_sha_blocks(self):
        doc = optimization_report(HEAD, sample(sha=OLD))
        self.assertEqual(doc["status"], "BLOCKED")
        self.assertEqual(doc["measured_costs"], [])

    def test_block_false_attribution(self):
        doc = optimization_report(HEAD, sample(cost_attribution={
            "status": "BLOCKED", "reason": "OVERLAPPING_OR_INVALID_TIMING_SPANS"}))
        self.assertEqual(doc["status"], "BLOCKED")
        self.assertTrue(any(x["id"] == "COST_MISSING" for x in doc["priority_findings"]))

    def test_baseline_configuration_mismatch_rejected(self):
        doc = optimization_report(HEAD, sample(), baseline=sample(sha=OLD, cycles=10))
        self.assertEqual(doc["comparison"]["status"], "NOT_COMPARABLE")

    def test_failed_baseline_rejected(self):
        doc = optimization_report(HEAD, sample(), baseline=sample(sha=OLD, status="FAIL"))
        self.assertEqual(doc["comparison"]["status"], "NOT_COMPARABLE")

    def test_comparable_baseline_only_directional(self):
        doc = optimization_report(HEAD, sample(preload_ms=1000),
                                  baseline=sample(sha=OLD, preload_ms=2000))
        self.assertEqual(doc["comparison"]["status"], "DIRECTIONAL_ONLY")
        self.assertEqual(next(x["delta_pct"] for x in doc["comparison"]["metrics"]
                              if x["name"] == "preload_ms"), -50)

    def test_not_run_cannot_claim_full_ui_or_launcher(self):
        doc = optimization_report(HEAD, sample())
        self.assertEqual(doc["functional_coverage"]["internal_screen_operations"], "NOT_RUN")
        self.assertEqual(doc["functional_coverage"]["public_network_rollback"], "NOT_RUN")
        self.assertEqual(doc["function_hotlist_status"], "NOT_RUN")

    def test_guide_method_cost_reused_without_startup_cprofile(self):
        evidence = {"status": "PASS", "observed_sha": HEAD,
            "bottleneck_candidates": [
                {"kind": "python_method", "location": "Guide.load",
                 "cost_ms": 175.0, "evidence": "instrumented_exclusive_time"},
                {"kind": "guide_open", "location": "guide1", "cost_ms": 250},
            ]}
        data = optimization_report(HEAD, sample(), guides=evidence)
        self.assertEqual(data["function_hotlist_status"], "OBSERVED")
        self.assertEqual(data["function_hotlist_scope"], "guide_instrumented_exclusive_method_time")
        self.assertEqual(data["function_hotlist"][0]["location"], "Guide.load")

    def test_guide_stale_hotspots_are_not_trusted(self):
        evidence = {"status": "PASS", "observed_sha": OLD,
            "bottleneck_candidates": [{"kind": "python_method",
                                       "location": "irrelevant", "cost_ms": 100}]}
        data = optimization_report(HEAD, sample(), guides=evidence)
        self.assertEqual(data["function_hotlist_status"], "NOT_RUN")

    def test_home_route_drift_is_evidence_not_a_leak_claim(self):
        doc = optimization_report(HEAD, sample(revisit_comparison={
            "quests": {"home_tree_delta_first_to_last_mib": 14.08},
            "crafts": {"home_tree_delta_first_to_last_mib": -2.0},
        }))
        self.assertEqual(doc["home_route_drift"][0]["route"], "quests")
        self.assertTrue(any(x["id"] == "HOME_ROUTE_quests" for x in doc["priority_findings"]))
        self.assertIn("sans preuve de fuite", render_markdown(doc))

    def test_ci_step_percentages_are_kept_per_job(self):
        doc = optimization_report(HEAD, sample(), ci_costs={"git_head": HEAD,
            "jobs": [{"job": "Windows Packaging", "steps": [
                {"step": "EXE", "duration_seconds": 30.0, "percent_of_job_measured_steps": 75.0}]}]})
        self.assertEqual(doc["ci_step_costs"][0]["job"], "Windows Packaging")
        self.assertIn("75.0% du job", render_markdown(doc))

    def test_report_reuses_canonical_agent_tool_catalog_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app_json = root / "artifacts" / "app.json"
            app_json.parent.mkdir(parents=True)
            import json
            app_json.write_text(json.dumps(sample()), encoding="utf-8")
            with (
                patch("tools.atlas_doctor_lib.core.git_state",
                      return_value={"head": HEAD, "dirty": False}),
                patch("tools.agent_planner._planning_catalog",
                      return_value={"schema_version": 1, "tools": []}) as cached,
            ):
                report = generate(root, sha=HEAD, app_report=Path("artifacts/app.json"))
            cached.assert_called_once()
            self.assertEqual(cached.call_args.kwargs["cache_info"],
                             report["tool_catalog_cache"])
            self.assertEqual(report["diagnostic_correlation"]["status"], "NO_CORRELATION")
            self.assertTrue((root / "artifacts" / "doctor_complete" /
                             "optimization.json").is_file())

    def test_catalog_routing_requires_same_clean_git_revision_as_benchmark(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app_json = root / "artifacts" / "app.json"
            app_json.parent.mkdir(parents=True)
            app_json.write_text(json.dumps(sample()), encoding="utf-8")
            for state in ({"head": OLD, "dirty": False},
                          {"head": HEAD, "dirty": True}):
                with (
                    self.subTest(state=state),
                    patch("tools.atlas_doctor_lib.core.git_state", return_value=state),
                    patch("tools.agent_planner._planning_catalog",
                          side_effect=AssertionError("stale or dirty worktree")) as scan,
                ):
                    report = generate(root, sha=HEAD,
                                      app_report=Path("artifacts/app.json"))
                    scan.assert_not_called()
                    self.assertEqual(
                        report["tool_catalog_cache"]["status"],
                        "SHA_OR_WORKTREE_MISMATCH",
                    )
                    self.assertEqual(
                        report["diagnostic_correlation"]["investigation_plan"]
                        ["steps"], [],
                    )
                    self.assertFalse(
                        report["diagnostic_correlation"]["tools_executed"],
                    )

    def test_stale_app_skips_expensive_tool_catalog_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app_json = root / "artifacts" / "app.json"
            app_json.parent.mkdir(parents=True)
            import json
            app_json.write_text(json.dumps(sample(sha=OLD)), encoding="utf-8")
            with patch("tools.agent_planner._planning_catalog",
                       side_effect=AssertionError("catalog must not scan stale data")):
                report = generate(root, sha=HEAD, app_report=Path("artifacts/app.json"))
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["tool_catalog_cache"]["status"], "NOT_REQUIRED")
            self.assertEqual(report["diagnostic_correlation"]["status"], "BLOCKED")

    def test_bad_rss_numbers_not_counted(self):
        doc = optimization_report(HEAD, sample(
            peak_process_tree_rss_mib=True, idle_tree_rss_delta_mib=float("nan")))
        self.assertIsNone(doc["memory"]["process_tree_peak_mib"])
        self.assertIsNone(doc["memory"]["idle_rss_delta_mib"])


if __name__ == "__main__":
    unittest.main()
