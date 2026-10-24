from __future__ import annotations

import unittest
from pathlib import Path

from tools.phase8_memory_tolerance import MARGIN, classify, hard_limit


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

    def test_invalid_and_missing_memory_evidence_cannot_pass(self):
        for invalid in (float("nan"), float("inf"), -1.0):
            with self.subTest(invalid=invalid):
                self.assertEqual(classify(invalid, 2.0), "FAIL")
        for target in (0, -1, float("nan"), float("inf")):
            with self.subTest(target=target), self.assertRaises(ValueError):
                hard_limit(target)

    def test_windows_workflow_uses_common_bound_and_preserves_warnings(self):
        workflow = (ROOT / ".github/workflows/phase8-memory-benchmark.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("from tools.phase8_memory_tolerance import classify, hard_limit", workflow)
        self.assertIn('preload_status = classify(preload_mb, preload_target_mb)', workflow)
        self.assertIn('peak_hard_limit_mb = hard_limit(peak_target_mb)', workflow)
        self.assertIn('state = classify(measured, budget)', workflow)
        self.assertIn('if state == "FAIL":', workflow)
        self.assertIn('if state == "WARNING":', workflow)
        self.assertIn('if metric not in metrics or metrics[metric] is None:', workflow)
        self.assertIn('hard ceiling: 2.10 MB with +5% tolerance', workflow)


if __name__ == "__main__":
    unittest.main()
