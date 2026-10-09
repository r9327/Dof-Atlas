from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.development_preflight import (
    _review_python_sources,
    _select_modules,
    _run_focused_tests,
    development_preflight,
)


class DevelopmentPreflightContracts(unittest.TestCase):
    def test_source_budget_makes_partial_not_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app").mkdir()
            paths = []
            for i in range(18):
                relative = f"app/module_{i}.py"
                (root / relative).write_text(f"x_{i} = 1\n")
                paths.append(relative)
            result = _review_python_sources(root, paths)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["checked"], 16)
            self.assertTrue(result["truncated"])

    def test_syntax_error_and_symlink_do_not_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "broken.py").write_text("def bad(\n")
            result = _review_python_sources(root, ["broken.py"])
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["errors"][0]["reason"], "SyntaxError")

    def test_filtered_modules_never_run_outside_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "tests").mkdir()
            (root / "tests/test_a.py").write_text("pass\n")
            with patch("tools.ai_context.recommended_tests",
                       return_value=["tests.test_a", "app.main", "tests.test_missing"]):
                report = _select_modules(root, [], 8)
            self.assertEqual(report["selected"], ["tests.test_a"])
            self.assertEqual(report["status"], "REVIEW")

    def test_actual_test_runner_success_and_failure_propagate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            folder_tests = root / "tests"
            folder_tests.mkdir()
            (folder_tests / "__init__.py").write_text("")
            (folder_tests / "test_ok.py").write_text(
                "import unittest\nclass Smoke(unittest.TestCase):\n"
                " def test_ok(self): self.assertTrue(True)\n")
            (folder_tests / "test_fail.py").write_text(
                "import unittest\nclass Smoke(unittest.TestCase):\n"
                " def test_fail(self): self.fail('expected')\n")
            good = _run_focused_tests(root, ["tests.test_ok"], 30)
            bad = _run_focused_tests(root, ["tests.test_fail"], 30)
            self.assertEqual(good["status"], "PASS")
            self.assertEqual(bad["status"], "FAIL")
            self.assertTrue(good["tests_executed"])

    def test_rejects_unsafe_budgets_and_refs(self):
        root = Path("/tmp")
        for kw in ({"base_ref": "-bad"}, {"base_ref": "main", "max_tests": 9},
                   {"base_ref": "main", "timeout_seconds": 9}):
            with self.assertRaises(ValueError):
                development_preflight(root, **kw)


if __name__ == "__main__":
    unittest.main()
