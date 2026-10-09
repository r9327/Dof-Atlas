from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.scenario_coverage import summarize_scenarios


class ScenarioCoverageTests(unittest.TestCase):
    SHA = "a" * 40

    def scenario(self, events, *, sha=None, complete=True):
        return {"kind": "doctor_runtime_observation", "candidate_sha": sha or self.SHA,
                "worktree_clean": True, "truncated": not complete, "events": events}

    def test_multiple_scenarios_accumulate_only_positive_exact_sha_coverage(self):
        a = self.scenario([{"type": "python_call_edge",
                            "source": "app/pages/home.py", "target": "app/core/catalog.py"}])
        b = self.scenario([{"type": "qt_callback_invoked",
                            "source": "app/pages/guide.py", "target": "app/core/catalog.py"}])
        report = summarize_scenarios([a, b], expected_sha=self.SHA,
                                     required_files=["app/pages/home.py", "app/pages/guide.py",
                                                     "app/pages/not_tested.py"])
        self.assertEqual(report["traces_invalid"], 0)
        self.assertEqual(report["observed_python_files_count"], 3)
        self.assertEqual(report["unobserved_required_files"], ["app/pages/not_tested.py"])
        self.assertEqual(report["status"], "REVIEW")
        self.assertFalse(report["safe_to_delete_unobserved"])
        self.assertFalse(report["tests_executed"])

    def test_exact_sha_complete_trace_cannot_be_substituted_with_stale_trace(self):
        stale = self.scenario([{"type": "python_call_edge",
                                "source": "app/a.py", "target": "app/b.py"}],
                              sha="b" * 40)
        report = summarize_scenarios([stale], expected_sha=self.SHA,
                                     required_files=["app/a.py"])
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["traces_invalid"], 1)
        self.assertEqual(report["observed_python_files_count"], 0)
        good = self.scenario([{"type": "python_call_edge", "source": "app/a.py",
                               "target": "app/b.py"}])
        self.assertEqual(summarize_scenarios([good], expected_sha=self.SHA,
                                              required_files=["app/a.py"])["status"], "OBSERVED")

    def test_ignores_outside_repo_and_does_not_count_json_path_as_code(self):
        report = summarize_scenarios([self.scenario([
            {"type": "file_open", "source": "app/a.py", "target": "data/items.json"},
            {"type": "python_call_edge", "source": "app/a.py", "target": "../bad.py"},
        ])], expected_sha=self.SHA)
        self.assertEqual(report["observed_python_files_count"], 1)
        with self.assertRaises(ValueError):
            summarize_scenarios([], expected_sha=self.SHA,
                                required_files=["../bad.py"])

    def test_bounds_and_invalid_events_do_not_prove_coverage(self):
        trace = self.scenario([None])
        report = summarize_scenarios([trace], expected_sha=self.SHA)
        self.assertEqual(report["traces_invalid"], 1)
        self.assertEqual(report["observed_python_files_count"], 0)
        with self.assertRaises(ValueError):
            summarize_scenarios([{}] * 13, expected_sha=self.SHA)


if __name__ == "__main__":
    unittest.main()
