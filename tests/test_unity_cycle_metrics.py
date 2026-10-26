"""Pure Python checks of Guide lifecycle probe metrics, without Qt."""
from __future__ import annotations

import unittest
from tools.assets.unity_local_cycle_probe import cycle_metrics


def samples(n: int, growth: int = 0) -> list[dict]:
    return [{"cycle": i, "widgets": 120 + max(0, i - 5) * growth,
             "working_set_bytes": 10_000 + i * 100} for i in range(n + 1)]


class UnityCycleMetricsTests(unittest.TestCase):
    def test_short_run_cannot_claim_pass(self):
        for count in (1, 5, 9):
            measured = cycle_metrics(samples(count, 2), count)
            self.assertEqual(measured["status"], "SMOKE_NOT_CERTIFIED")
            self.assertEqual(measured["widget_stability"], "NOT_EVALUATED")

    def test_full_run_pass_or_growth(self):
        stable = cycle_metrics(samples(10), 10)
        self.assertEqual(stable["status"], "MEASURED_NOT_CERTIFIED")
        self.assertEqual(stable["working_set_delta_bytes"], 1000)
        leak = cycle_metrics(samples(30, growth=2), 30)
        self.assertEqual(leak["widget_stability"], "FAIL")
        self.assertEqual(leak["status"], "WIDGET_GROWTH")
        self.assertEqual(leak["widget_growth_after_warmup"], 50)

    def test_missing_working_set_never_fabricated(self):
        data = samples(10)
        data[0]["working_set_bytes"] = None
        data[5]["working_set_bytes"] = None
        report = cycle_metrics(data, 10)
        self.assertNotIn("working_set_delta_bytes", report)
        self.assertNotIn("working_set_growth_after_warmup_bytes", report)

    def test_reject_inconsistent_samples(self):
        with self.assertRaises(ValueError):
            cycle_metrics(samples(5), 10)
        with self.assertRaises(ValueError):
            cycle_metrics(samples(0), 0)


if __name__ == "__main__":
    unittest.main()
