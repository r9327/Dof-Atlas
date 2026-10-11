from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.certification_explain import explain_selection


class ExplainCertificationScopeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "tests").mkdir()
        for name in ("test_one", "test_two", "test_three"):
            (self.root / "tests" / f"{name}.py").write_text("import unittest\n")

    def test_all_tests_have_action_and_uncertainty(self):
        a = explain_selection(self.root, {
            "profile": "FAST", "test_modules": ["tests.test_one"],
            "test_selection_explanations": {
                "tests.test_one": {"source": "scenario_contract", "triggered_by": ["app/guide.py"]}
            },
        })
        self.assertEqual(a["inventory_count"], 3)
        self.assertEqual(a["selected_count"], 1)
        rows = {x["test"]: x for x in a["tests"]}
        self.assertEqual(rows["tests.test_one"]["action"], "RUN")
        self.assertEqual(rows["tests.test_one"]["triggered_by"], ["app/guide.py"])
        self.assertEqual(rows["tests.test_two"]["action"], "NOT_IN_SCOPED_SET")
        self.assertFalse(rows["tests.test_two"]["absence_of_dynamic_dependency_proven"])
        self.assertFalse(a["all_exclusions_proven_safe"])
        self.assertFalse(a["full_suite_waived"])

    def test_full_required_explains_why_no_scoped_test(self):
        a = explain_selection(self.root, {
            "profile": "FULL_REQUIRED", "test_modules": [],
            "reasons": ["CRITICAL_POLICY_CHANGE"],
        })
        self.assertEqual(a["selected_count"], 0)
        self.assertEqual(a["tests"][0]["action"], "DEFER_TO_FULL")
        self.assertIn("CRITICAL_POLICY_CHANGE", a["tests"][0]["reason"])

    def test_injected_missing_selected_test_fails_closed(self):
        a = explain_selection(self.root, {
            "profile": "FAST", "test_modules": ["tests.test_nonexistent"]
        })
        self.assertEqual(a["status"], "BLOCKED")
        self.assertEqual(a["reason"], "SELECTED_TEST_NOT_IN_INVENTORY")

    def test_symlink_test_inventory_is_not_trusted(self):
        link = self.root / "tests/test_link.py"
        try:
            link.symlink_to(self.root / "tests/test_one.py")
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not supported here")
        a = explain_selection(self.root, {"profile": "FAST", "test_modules": []})
        self.assertEqual(a["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
