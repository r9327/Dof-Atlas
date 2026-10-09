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

    def test_opened_python_and_registered_qt_receiver_are_not_executed_files(self):
        trace = self.scenario([
            {"type": "file_open", "source": "app/loader.py", "target": "app/unexecuted.py"},
            {"type": "qt_signal_connect_returned",
             "source": "app/loader.py", "target": "app/never_called.py"},
        ])
        report = summarize_scenarios([trace], expected_sha=self.SHA,
                                     required_files=["app/unexecuted.py", "app/never_called.py"])
        self.assertEqual(report["observed_python_files_count"], 1)
        self.assertEqual(report["observed_python_files_examples"], ["app/loader.py"])
        self.assertEqual(report["status"], "REVIEW")
        self.assertFalse(report["safe_to_delete_unobserved"])

    def test_returned_cached_import_never_counts_target_as_executed(self):
        report = summarize_scenarios([self.scenario([
            {"type": "module_import_returned", "source": "app/consumer.py",
             "target": "app/not_executed.py",
             "confidence": "IMPORTLIB_RETURNED_REPOSITORY_MODULE"},
        ])], expected_sha=self.SHA, required_files=["app/not_executed.py"])
        self.assertEqual(report["observed_python_files_examples"], ["app/consumer.py"])
        self.assertEqual(report["unobserved_required_files"], ["app/not_executed.py"])
        self.assertFalse(report["safe_to_delete_unobserved"])

    def test_exact_sha_symbol_entries_and_qt_callbacks_are_distinguished(self):
        events = [
            {"type": "python_symbol_call", "source": "app/start.py",
             "target": "app/services/search.py", "callee_symbol": "Finder.run",
             "confidence": "OBSERVED_CALL_ENTRY"},
            {"type": "qt_callback_invoked", "source": "app/pages/guide.py",
             "target": "app/pages/guide.py", "callee_symbol": "GuidesView.refresh",
             "confidence": "WRAPPED_PYTHON_CALLBACK_ENTERED"},
            {"type": "qt_signal_connect_returned", "source": "app/pages/guide.py",
             "target": "app/pages/guide.py", "callee_symbol": "GuidesView.never_entered"},
            {"type": "module_import_returned", "source": "app/start.py",
             "target": "app/services/search.py", "callee_symbol": "Finder.not_entered",
             "confidence": "IMPORTLIB_RETURNED_REPOSITORY_MODULE"},
        ]
        required = ["app/services/search.py::Finder.run",
                    "app/pages/guide.py::GuidesView.refresh",
                    "app/services/search.py::Finder.not_entered"]
        report = summarize_scenarios([self.scenario(events)], expected_sha=self.SHA,
                                     required_symbols=required)
        self.assertEqual(report["entered_symbols_count"], 2)
        self.assertEqual(report["unobserved_required_symbols"],
                         ["app/services/search.py::Finder.not_entered"])
        self.assertEqual(report["status"], "REVIEW")
        self.assertFalse(report["safe_to_delete_unobserved"])

    def test_symbol_coverage_does_not_trust_stale_traces(self):
        event = {"type": "python_symbol_call", "source": "app/runner.py",
                 "target": "app/core/catalog.py", "callee_symbol": "read",
                 "confidence": "OBSERVED_CALL_ENTRY"}
        stale = self.scenario([event], sha="b" * 40)
        report = summarize_scenarios([stale], expected_sha=self.SHA,
             required_symbols=["app/core/catalog.py::read"])
        self.assertEqual(report["entered_symbols_count"], 0)
        with self.assertRaises(ValueError):
            summarize_scenarios([self.scenario([])], expected_sha=self.SHA,
                 required_symbols=["../../outside.py::run"])

    def test_bounds_and_invalid_events_do_not_prove_coverage(self):
        trace = self.scenario([None])
        report = summarize_scenarios([trace], expected_sha=self.SHA)
        self.assertEqual(report["traces_invalid"], 1)
        self.assertEqual(report["observed_python_files_count"], 0)
        with self.assertRaises(ValueError):
            summarize_scenarios([{}] * 13, expected_sha=self.SHA)


if __name__ == "__main__":
    unittest.main()
