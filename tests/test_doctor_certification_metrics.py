from __future__ import annotations

import copy
import unittest

from tools.atlas_doctor_lib.certification_metrics import assess_memory_benchmark, STAGE_BUDGETS, RETAINED_BUDGETS


def sample():
    metrics = {
        "stages": [{"label": label, "tree_rss_mb": budget - 1.0}
                   for label, (budget, _strict) in STAGE_BUDGETS.items()],
        "peak_tree_rss_mb": 219.5,
    }
    metrics.update({name: budget - 0.5 for name, budget in RETAINED_BUDGETS.items()})
    return {"schema_version": 1, "environment": {"platform": "win32"}, "metrics": metrics}


class Phase8BudgetEvidenceTests(unittest.TestCase):
    def test_real_phase8_budget_definitions_are_explicit(self):
        o = assess_memory_benchmark(sample())
        self.assertEqual(o["status"], "LOCAL_NUMBERS_IN_BUDGET_UNATTESTED")
        self.assertFalse(o["performance_certified"])
        self.assertFalse(o["github_provenance_verified"])
        self.assertFalse(o["phase_certified"])
        self.assertEqual(o["peak_tree_budget_mb"], 220.0)
        self.assertEqual(len(o["observed_stage_tree_mb"]), 6)

    def test_each_home_stage_at_exact_100_is_failure(self):
        for label, (budget, strict) in STAGE_BUDGETS.items():
            if not strict:
                continue
            with self.subTest(label=label):
                p = sample()
                next(x for x in p["metrics"]["stages"] if x["label"] == label)["tree_rss_mb"] = budget
                self.assertIn("MEMORY_STAGE_OVER_BUDGET:" + label,
                              assess_memory_benchmark(p)["errors"])

    def test_after_preload_allows_exactly_95_but_not_more(self):
        p = sample()
        next(x for x in p["metrics"]["stages"] if x["label"] == "after_preload")["tree_rss_mb"] = 95.0
        self.assertEqual(assess_memory_benchmark(p)["status"], "LOCAL_NUMBERS_IN_BUDGET_UNATTESTED")
        next(x for x in p["metrics"]["stages"] if x["label"] == "after_preload")["tree_rss_mb"] = 95.01
        self.assertIn("MEMORY_STAGE_OVER_BUDGET:after_preload", assess_memory_benchmark(p)["errors"])

    def test_missing_or_duplicate_stage_fails(self):
        p = sample()
        p["metrics"]["stages"].pop()
        self.assertTrue(any(x.startswith("REQUIRED_MEMORY_STAGE_MISSING:")
                            for x in assess_memory_benchmark(p)["errors"]))
        p = sample()
        p["metrics"]["stages"].append(copy.deepcopy(p["metrics"]["stages"][0]))
        self.assertIn("DUPLICATE_MEMORY_STAGE", assess_memory_benchmark(p)["errors"])

    def test_peak_and_retained_budgets_fail(self):
        p = sample()
        p["metrics"]["peak_tree_rss_mb"] = 220.01
        self.assertIn("PROCESS_TREE_PEAK_OVER_BUDGET", assess_memory_benchmark(p)["errors"])
        for name, budget in RETAINED_BUDGETS.items():
            with self.subTest(name=name):
                p = sample()
                p["metrics"][name] = budget + 0.01
                self.assertIn("RETAINED_MEMORY_OVER_BUDGET:" + name,
                              assess_memory_benchmark(p)["errors"])

    def test_malformed_and_nonfinite_numbers_block(self):
        for value in (True, None, "99.5", float("nan"), -1.0):
            p = sample()
            p["metrics"]["stages"][0]["tree_rss_mb"] = value
            self.assertTrue(any(x.startswith("INVALID_MEMORY_STAGE_RSS")
                                for x in assess_memory_benchmark(p)["errors"]))


if __name__ == "__main__":
    unittest.main()
