from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.scenario_trends import summarize_scenario_trend


class DoctorScenarioTrendTests(unittest.TestCase):
    @staticmethod
    def trace(sha: str, *, observed: bool, scenario: str = "tests.demo"):
        return {
            "kind": "doctor_runtime_observation", "candidate_sha": sha,
            "scenario_module": scenario, "worktree_clean": True,
            "truncated": False,
            "events": ([{"type": "python_call_edge", "source": "app/a.py",
                         "target": "app/b.py"}] if observed else []),
        }

    def test_repeated_absence_is_review_not_functional_regression(self):
        records = [
            self.trace("a" * 40, observed=True),
            self.trace("b" * 40, observed=True),
            self.trace("c" * 40, observed=False),
            self.trace("d" * 40, observed=False),
        ]
        report = summarize_scenario_trend(records)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["run_count"], 4)
        self.assertEqual(report["repeated_absence_candidates"], 1)
        self.assertEqual(report["candidates"][0]["classification"],
                         "REPEATED_ABSENCE_REVIEW")
        self.assertFalse(report["regression_proven"])
        self.assertFalse(report["tests_executed"])

    def test_symbol_disappearance_is_an_advisory_historical_lead(self):
        records = [
            self.trace("a" * 40, observed=False),
            self.trace("b" * 40, observed=False),
            self.trace("c" * 40, observed=False),
            self.trace("d" * 40, observed=False),
        ]
        observed = {"type": "python_symbol_call", "source": "app/runner.py",
                    "target": "app/modules/guide.py", "callee_symbol": "Guide.advance",
                    "confidence": "OBSERVED_CALL_ENTRY"}
        records[0]["events"] = [observed]
        records[1]["events"] = [observed]
        report = summarize_scenario_trend(records)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["candidates_total"], 0)
        self.assertEqual(report["repeated_symbol_absence_candidates"], 1)
        self.assertEqual(report["symbol_candidates"][0]["symbol"], "Guide.advance")
        self.assertFalse(report["regression_proven"])

    def test_rejects_inconsistent_scenarios(self):
        first = self.trace("a" * 40, observed=True)
        other = self.trace("b" * 40, observed=False, scenario="tests.other")
        self.assertEqual(summarize_scenario_trend([first, other])["status"],
                         "UNAVAILABLE")
        self.assertEqual(summarize_scenario_trend([first])["status"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
