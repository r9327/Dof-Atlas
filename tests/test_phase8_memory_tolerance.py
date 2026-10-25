from __future__ import annotations

import unittest
from pathlib import Path

from tools.phase8_memory_tolerance import (MARGIN, classify, hard_limit,
                                           require_peak_tree_rss, require_memory_observation)


ROOT = Path(__file__).resolve().parents[1]


class Phase8MemoryToleranceTests(unittest.TestCase):
    def test_exact_five_percent_ceiling_without_implicit_budget_growth(self):
        self.assertEqual(MARGIN, 0.05)
        for target, ceiling in ((2.0, 2.1), (1.0, 1.05),
                                (15.0, 15.75), (20.0, 21.0),
                                (95.0, 99.75), (220.0, 231.0)):
            with self.subTest(target=target):
                self.assertAlmostEqual(hard_limit(target), ceiling)
                self.assertEqual(classify(target, target), "PASS")
                self.assertEqual(classify(target * 1.025, target), "WARNING")
                self.assertEqual(classify(ceiling, target), "WARNING")
                self.assertEqual(classify(ceiling + 0.01, target), "FAIL")

    def test_craft_observation_at_260_still_fails(self):
        self.assertEqual(classify(2.60, 2.0), "FAIL")
        self.assertEqual(classify(2.05, 2.0), "WARNING")
        self.assertEqual(classify(1.91, 2.0), "PASS")
        self.assertEqual(classify(-0.55, 2.0), "FAIL")  # Invalid absolute RSS.
        self.assertEqual(classify(-0.55, 2.0, allow_negative=True), "PASS")

    def test_invalid_and_missing_memory_evidence_cannot_pass(self):
        for invalid in (float("nan"), float("inf"), -1.0):
            with self.subTest(invalid=invalid):
                self.assertEqual(classify(invalid, 2.0), "FAIL")
        for target in (0, -1, float("nan"), float("inf")):
            with self.subTest(target=target), self.assertRaises(ValueError):
                hard_limit(target)

    def test_missing_or_inconsistent_peak_evidence_fails_closed(self):
        self.assertEqual(require_peak_tree_rss({"peak_tree_rss_mb": 231.0}, preload_mb=95.0), 231.0)
        for metrics in ({}, {"peak_tree_rss_mb": None},
                        {"peak_tree_rss_mb": 0}, {"peak_tree_rss_mb": -1},
                        {"peak_tree_rss_mb": float("nan")},
                        {"peak_tree_rss_mb": float("inf")},
                        {"peak_tree_rss_mb": True},
                        {"peak_tree_rss_mb": "200"},
                        {"peak_tree_rss_mb": 90.0}):
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                require_peak_tree_rss(metrics, preload_mb=95.0)
        with self.assertRaises(ValueError):
            require_peak_tree_rss({"peak_tree_rss_mb": 200.0}, preload_mb=float("nan"))

    def test_required_memory_evidence_rejects_coercion_and_missing_values(self):
        self.assertEqual(require_memory_observation(0.0, label="retained"), 0.0)
        self.assertEqual(require_memory_observation(95.0, label="preload", positive=True), 95.0)
        self.assertEqual(require_memory_observation(-0.55, label="craft_retained_tree_delta_mb", allow_negative=True), -0.55)
        for value in (None, True, False, "0", "95", float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_memory_observation(value, label="required", positive=True)
            self.assertEqual(classify(value, 2.0), "FAIL")
        with self.assertRaises(ValueError):
            require_memory_observation(0.0, label="stage", positive=True)

    def test_windows_workflow_uses_common_bound_and_preserves_warnings(self):
        workflow = (ROOT / ".github/workflows/phase8-memory-benchmark.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("classify, hard_limit, require_peak_tree_rss, require_memory_observation", workflow)
        self.assertIn("require_memory_observation(row.get(kind)", workflow)
        self.assertIn("require_memory_observation(metrics.get(metric), label=metric, allow_negative=True)", workflow)
        self.assertIn("classify(measured, budget, allow_negative=True)", workflow)
        self.assertIn("peak_tree = require_peak_tree_rss(metrics, preload_mb=preload_mb)", workflow)
        self.assertNotIn('metrics.get("peak_tree_rss_mb") or 0.0', workflow)
        self.assertIn('preload_status = classify(preload_mb, preload_target_mb)', workflow)
        self.assertIn('peak_hard_limit_mb = hard_limit(peak_target_mb)', workflow)
        self.assertIn('state = classify(measured, budget, allow_negative=True)', workflow)
        self.assertIn('if state == "FAIL":', workflow)
        self.assertIn('if state == "WARNING":', workflow)
        self.assertNotIn('float(metrics[metric])', workflow)
        self.assertIn('hard ceiling: 2.10 MB with +5% tolerance', workflow)


if __name__ == "__main__":
    unittest.main()
