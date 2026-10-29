"""Doctor optimization-report contracts: no fabricated savings or certification."""
from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.optimization_report import optimization_report, render_markdown

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

    def test_bad_rss_numbers_not_counted(self):
        doc = optimization_report(HEAD, sample(
            peak_process_tree_rss_mib=True, idle_tree_rss_delta_mib=float("nan")))
        self.assertIsNone(doc["memory"]["process_tree_peak_mib"])
        self.assertIsNone(doc["memory"]["idle_rss_delta_mib"])


if __name__ == "__main__":
    unittest.main()
