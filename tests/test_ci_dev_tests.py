from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import ci_dev_tests


class DeveloperTestPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        for name in ("test_achievements_phase2.py", "test_ai_context.py", "test_repository_git_hooks.py", "test_meta_integrity.py", "test_ci_dev_tests.py"):
            (self.root / "tests" / name).write_text("# placeholder\n", encoding="utf-8")

    def test_single_changed_test_selects_it_without_full_suite(self):
        p = ci_dev_tests.plan(self.root, ["tests/test_achievements_phase2.py"], head="a" * 40)
        self.assertEqual(p["status"], "TARGETED_ADVISORY")
        self.assertEqual(p["modules"], ["tests.test_achievements_phase2"])
        self.assertFalse(p["tests_executed"])
        self.assertFalse(p["full_suite_waived"])
        self.assertFalse(p["certified"])

    def test_quality_tool_reuses_canonical_context_mapping(self):
        p = ci_dev_tests.plan(self.root, ["tools/ci_dev_tests.py"])
        self.assertEqual(p["status"], "TARGETED_ADVISORY")
        self.assertEqual(p["modules"][0], "tests.test_ci_dev_tests")
        self.assertIn("tests.test_ai_context", p["modules"])

    def test_unknown_path_blocks_execution_even_with_known_test(self):
        p = ci_dev_tests.plan(self.root, ["tests/test_ci_dev_tests.py", "mystery/problem.bin"])
        self.assertEqual(p["status"], "REVIEW_REQUIRED")
        self.assertEqual(p["unmapped_paths"], ["mystery/problem.bin"])
        with patch.object(ci_dev_tests, "ROOT", self.root):
            with patch.object(ci_dev_tests, "_git", return_value="b" * 40):
                self.assertEqual(ci_dev_tests.main(["--path", "mystery/problem.bin", "--run"]), 2)

    def test_empty_and_traversal_paths_rejected(self):
        for names in ([], ["../elsewhere.py"], ["/etc/passwd"], ["./../other"]):
            with self.subTest(names=names), self.assertRaises(ci_dev_tests.SelectionError):
                ci_dev_tests.plan(self.root, names)

    def test_test_runner_records_real_timings_and_exit_code(self):
        class Sample(unittest.TestCase):
            def test_passes(self):
                self.assertTrue(True)

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Sample)
        with patch.object(unittest.defaultTestLoader, "loadTestsFromNames", return_value=suite):
            code, payload = ci_dev_tests.run_targeted(["tests.sample"], head="a" * 40)
        self.assertEqual(code, 0)
        self.assertEqual(payload["test_count"], 1)
        self.assertEqual(len(payload["top_slowest_tests"]), 1)
        self.assertGreaterEqual(payload["top_slowest_tests"][0]["seconds"], 0)
        self.assertFalse(payload["certified"])
        self.assertFalse(payload["full_suite_waived"])

    def test_report_is_sandboxed_to_artifacts(self):
        data = {"status": "PASS"}
        with self.assertRaises(ci_dev_tests.SelectionError):
            ci_dev_tests._write_report(self.root, "data/persistent.json", data)
        with self.assertRaises(ci_dev_tests.SelectionError):
            ci_dev_tests._write_report(self.root, "../elsewhere.json", data)
        ci_dev_tests._write_report(self.root, "artifacts/dev-tests/report.json", data)
        self.assertTrue((self.root / "artifacts/dev-tests/report.json").is_file())


if __name__ == "__main__":
    unittest.main()
