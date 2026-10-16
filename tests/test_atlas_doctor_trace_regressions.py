from __future__ import annotations

import unittest
from tools.atlas_doctor_lib.trace_regressions import compare_scenario_traces


class HistoricalTraceComparisonTests(unittest.TestCase):
    def make(self, sha, events, *, scenario="tools.example_scenario"):
        return {"kind": "doctor_runtime_observation", "candidate_sha": sha,
                "worktree_clean": True, "truncated": False,
                "scenario_module": scenario, "events": events}

    def test_real_observation_drops_are_review_not_confirmed_regressions(self):
        before = self.make("a" * 40, [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"},
            {"type": "qt_callback_invoked", "source": "app/b.py",
             "target": "app/c.py", "confidence": "WRAPPED_PYTHON_CALLBACK_ENTERED"},
        ])
        after = self.make("b" * 40, [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"},
        ])
        result = compare_scenario_traces(before, after)
        self.assertEqual(result["lost_total"], 1)
        self.assertEqual(result["lost_observed_edges"][0]["kind"], "qt_callback_invoked")
        self.assertEqual(result["status"], "REVIEW")
        self.assertFalse(result["regression_proven"])

    def test_incomplete_or_different_scenarios_never_get_compared(self):
        before = self.make("a" * 40, [])
        after = self.make("b" * 40, [], scenario="tests.other")
        self.assertEqual(compare_scenario_traces(before, after)["status"], "UNAVAILABLE")
        after["scenario_module"] = before["scenario_module"]
        after["truncated"] = True
        self.assertEqual(compare_scenario_traces(before, after)["status"], "UNAVAILABLE")
        after["truncated"] = False
        self.assertEqual(compare_scenario_traces(before, after)["status"], "NO_OBSERVATION_DROP")

    def test_outside_paths_and_untrusted_qt_events_cannot_fake_edges(self):
        before = self.make("a" * 40, [
            {"type": "python_call_edge", "source": "../bad.py", "target": "app/b.py"},
            {"type": "qt_callback_invoked", "source": "app/a.py", "target": "app/b.py",
             "confidence": "CALL_SITE_ONLY"},
        ])
        after = self.make("b" * 40, [])
        self.assertEqual(compare_scenario_traces(before, after)["lost_total"], 0)


if __name__ == "__main__":
    unittest.main()
