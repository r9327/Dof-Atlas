from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.test_intelligence import test_cost_report


class TestCostEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".ai/runtime").mkdir(parents=True)

    def report(self, name, commands, sha="a"*40):
        path = self.root / ".ai/runtime" / name
        path.write_text(json.dumps({"head": sha, "mode": "FAST", "commands": commands}))
        return path

    def test_real_successful_costs_exclude_reused_full_and_failures(self):
        one = self.report("one.json", [
            {"group": "GUIDE", "duration_seconds": 9, "exit_code": 0},
            {"group": "FAST", "duration_seconds": 0, "exit_code": 0,
             "evidence_reused_from": "FULL_SUITE"},
            {"group": "BROKEN", "duration_seconds": 2, "exit_code": 1},
        ])
        two = self.report("two.json", [
            {"group": "GUIDE", "duration_seconds": 3, "exit_code": 0},
            {"group": "UI", "duration_seconds": 1, "exit_code": 0},
        ])
        data = test_cost_report(self.root, [one, two])
        self.assertEqual(data["status"], "PASS")
        self.assertEqual(data["groups"][0]["group"], "GUIDE")
        self.assertEqual(data["groups"][0]["median_seconds"], 6)
        self.assertEqual(data["groups"][0]["samples"], 2)
        self.assertEqual(data["reused_full_suite_commands_excluded"], 1)
        self.assertEqual(data["failed_commands_excluded"], 1)
        self.assertFalse(data["tests_executed"])
        self.assertFalse(data["benchmarks_executed"])

    def test_missing_or_outside_report_never_returns_pass(self):
        outside = self.root / "outside.json"
        outside.write_text("{}")
        data = test_cost_report(self.root, [outside])
        self.assertEqual(data["status"], "REVIEW")
        self.assertEqual(data["groups"], [])
        self.assertTrue(data["errors"])
        self.assertEqual(test_cost_report(self.root, [Path(".ai/runtime/missing.json")])["status"], "REVIEW")

    def test_nan_and_incomplete_command_never_enter_costs(self):
        path = self.report("bad.json", [
            {"group": "GUIDE", "duration_seconds": float("nan"), "exit_code": 0},
            {"group": "UI", "duration_seconds": 2, "exit_code": 0},
        ])
        payload = test_cost_report(self.root, [path])
        self.assertEqual(payload["status"], "REVIEW")
        self.assertEqual([r["group"] for r in payload["groups"]], ["UI"])
        self.assertEqual(len(payload["errors"]), 1)

    def test_input_report_budget(self):
        with self.assertRaises(ValueError):
            test_cost_report(self.root, [])
        with self.assertRaises(ValueError):
            test_cost_report(self.root, [Path("missing")] * 9)

    def test_advisory_order_keeps_all_required_groups_and_full_suite(self):
        from tools.atlas_doctor_lib.test_intelligence import suggest_targeted_test_order
        evidence = {"status": "PASS", "groups": [
            {"group": "SLOW", "median_seconds": 3600, "samples": 3},
            {"group": "QUICK", "median_seconds": 5, "samples": 2},
        ]}
        result = suggest_targeted_test_order(
            ["FULL_SUITE", "SLOW", "QUICK", "SLOW", "UNKNOWN"], evidence)
        self.assertEqual(result["suggested_order"],
                         ["QUICK", "SLOW", "FULL_SUITE", "UNKNOWN"])
        self.assertEqual(result["unknown_cost_groups"], ["FULL_SUITE", "UNKNOWN"])
        self.assertFalse(result["full_suite_waived"])
        self.assertFalse(result["tests_executed"])
        self.assertEqual(result["historically_measured_groups"], 2)

    def test_missing_cost_data_is_not_misrepresented_as_measured(self):
        from tools.atlas_doctor_lib.test_intelligence import suggest_targeted_test_order
        result = suggest_targeted_test_order(["A", "B"], {"status": "REVIEW", "groups": []})
        self.assertEqual(result["status"], "INSUFFICIENT_COST_EVIDENCE")
        self.assertEqual(result["suggested_order"], ["A", "B"])
        with self.assertRaises(ValueError):
            suggest_targeted_test_order(["X"] * 65, {"groups": []})


if __name__ == "__main__":
    unittest.main()
