from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tools.atlas_doctor_lib import certification_runtime


class RuntimeCertificationTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "candidate_sha": "b" * 40,
            "changed_paths": ["app/modules/encyclopedia/views/guide_view.py"],
            "source_impact": {"consumers": [
                "app/modules/encyclopedia/widgets/progression.py"
            ]},
        }

    def test_real_observation_is_not_functional_certification(self):
        actual = {
            "status": "OBSERVED", "candidate_sha": self.plan["candidate_sha"],
            "observed_required_files": sorted(
                self.plan["changed_paths"] + self.plan["source_impact"]["consumers"]
            ),
            "unobserved_required_files": [], "traces_checked": 1,
            "traces_invalid": 0,
        }
        with mock.patch.object(certification_runtime, "load_scenario_coverage",
                               return_value=actual) as loaded:
            r = certification_runtime.attach_runtime_trace(
                Path("/tmp"), self.plan, [Path("runtime.json")]
            )
        self.assertEqual(r["status"], "OBSERVED_NOT_CERTIFIED")
        self.assertFalse(r["functional_tests_passed"])
        self.assertFalse(r["performance_budgets_passed"])
        self.assertFalse(r["qt_lifecycle_certified"])
        self.assertFalse(r["full_suite_waived"])
        self.assertEqual(loaded.call_args.kwargs["required_files"],
                         sorted(self.plan["changed_paths"] + self.plan["source_impact"]["consumers"]))

    def test_stale_or_wrong_sha_never_counts_as_observation(self):
        with mock.patch.object(certification_runtime, "load_scenario_coverage",
                               return_value={
                                   "status": "OBSERVED", "candidate_sha": "a" * 40,
                               }):
            result = certification_runtime.attach_runtime_trace(
                Path("/tmp"), self.plan, [Path("runtime.json")]
            )
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["reason"], "OVER_BUDGET_OR_WRONG_SHA")

    def test_incomplete_trace_remains_review(self):
        with mock.patch.object(certification_runtime, "load_scenario_coverage",
                               return_value={
                                   "status": "REVIEW",
                                   "candidate_sha": self.plan["candidate_sha"],
                                   "unobserved_required_files": self.plan["changed_paths"],
                                   "traces_invalid": 1
                               }):
            result = certification_runtime.attach_runtime_trace(
                Path("/tmp"), self.plan, [Path("runtime.json")]
            )
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["unobserved_app_files"], self.plan["changed_paths"])

    def test_missing_trace_fails_closed(self):
        with mock.patch.object(certification_runtime, "load_scenario_coverage",
                               side_effect=ValueError("not a trace")):
            result = certification_runtime.attach_runtime_trace(
                Path("/tmp"), self.plan, [Path("absent.json")]
            )
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["reason"], "ValueError")

    def test_budget_enforced(self):
        with self.assertRaises(ValueError):
            certification_runtime.attach_runtime_trace(Path("."), self.plan, [])
        with self.assertRaises(ValueError):
            certification_runtime.attach_runtime_trace(
                Path("."), self.plan, [Path("trace.json")] * 13
            )

    def test_source_coverage_uses_real_doctor_scenario_module(self):
        from tools.atlas_doctor_lib import scenario_coverage
        self.assertTrue(callable(scenario_coverage.load_scenario_coverage))


if __name__ == "__main__":
    unittest.main()
