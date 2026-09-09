from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.atlas_performance_budget import evaluate_metric


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "tools/atlas_performance_budgets.json"


class PerformanceBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))

    def test_budget_policy_has_deterministic_owners_and_measured_only_timings(self) -> None:
        self.assertEqual(self.policy["schema_version"], 1)
        self.assertGreaterEqual(len(self.policy["metrics"]), 5)
        for budget in self.policy["metrics"].values():
            self.assertTrue((ROOT / budget["owner"]).is_file())
            self.assertLessEqual(budget["baseline"], budget["regression_limit"])
            self.assertLessEqual(budget["regression_limit"], budget["hard_limit"])
        self.assertIn("startup_stabilized_ms", self.policy["measured_only"]["metrics"])

    def test_measurement_under_budget_passes(self) -> None:
        result = evaluate_metric(1, {"baseline": 1, "regression_limit": 2, "hard_limit": 4})
        self.assertEqual(result["status"], "PASS")

    def test_hard_limit_exceeded_fails(self) -> None:
        result = evaluate_metric(5, {"baseline": 1, "regression_limit": 2, "hard_limit": 4})
        self.assertEqual(result["status"], "HARD_LIMIT_EXCEEDED")

    def test_regression_limit_exceeded_fails(self) -> None:
        result = evaluate_metric(3, {"baseline": 1, "regression_limit": 2, "hard_limit": 4})
        self.assertEqual(result["status"], "REGRESSION_LIMIT_EXCEEDED")

    def test_small_variation_within_regression_limit_is_tolerated(self) -> None:
        result = evaluate_metric(2, {"baseline": 1, "regression_limit": 2, "hard_limit": 4})
        self.assertEqual(result["status"], "PASS")

    def test_invalid_budget_order_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_metric(1, {"baseline": 3, "regression_limit": 2, "hard_limit": 4})


if __name__ == "__main__":
    unittest.main()
