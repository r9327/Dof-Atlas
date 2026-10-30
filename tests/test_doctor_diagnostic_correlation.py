"""Correlation Doctor: provenance, safety, and non-causal diagnostics."""
from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.diagnostic_correlation import correlate_diagnostics
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
