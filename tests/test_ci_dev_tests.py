from __future__ import annotations

import subprocess
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

    def test_git_discovery_includes_committed_staged_and_untracked(self):
        def git(*args):
            proc = subprocess.run(
                ["git", *args], cwd=self.root, capture_output=True,
                text=True, check=True,
            )
            return proc.stdout.strip()

        git("init")
        git("config", "user.name", "Atlas CI tests")
        git("config", "user.email", "atlas-ci@example.invalid")
        git("add", "-A")
        git("commit", "-m", "initial")
        base = git("rev-parse", "HEAD")

        committed = self.root / "tests/test_achievements_phase2.py"
        committed.write_text("# committed update\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-m", "changed test")
        staged = self.root / "tests/test_meta_integrity.py"
        staged.write_text("# staged update\n", encoding="utf-8")
        git("add", "--", "tests/test_meta_integrity.py")
        new = self.root / "tests/test_untracked.py"
        new.write_text("# untracked\n", encoding="utf-8")

        paths = ci_dev_tests.changed_paths(self.root, base)
        self.assertIn("tests/test_achievements_phase2.py", paths)
        self.assertIn("tests/test_meta_integrity.py", paths)
        self.assertIn("tests/test_untracked.py", paths)

    def test_failing_test_stays_failure_with_timing(self):
        class Broken(unittest.TestCase):
            def test_failure(self):
                self.fail("must stay red")

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Broken)
        with patch.object(unittest.defaultTestLoader, "loadTestsFromNames", return_value=suite):
            code, payload = ci_dev_tests.run_targeted(["tests.broken"], head="a" * 40)
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "FAIL")
        self.assertEqual(payload["failures"], 1)
        self.assertEqual(payload["test_count"], 1)
        self.assertEqual(len(payload["top_slowest_tests"]), 1)

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


class DeveloperParallelTests(unittest.TestCase):
    def test_parallel_refuses_qt_and_unknown(self):
        with self.assertRaises(ci_dev_tests.SelectionError):
            ci_dev_tests.run_parallel_safe(Path.cwd(), ["tests.test_ci_dev_tests", "tests.test_achievements_phase2"], head="a"*40, jobs=2)
        with self.assertRaises(ci_dev_tests.SelectionError):
            ci_dev_tests.run_parallel_safe(Path.cwd(), ["tests.test_ci_dev_tests"], head="a"*40, jobs=2)
        with self.assertRaises(ci_dev_tests.SelectionError):
            ci_dev_tests.run_parallel_safe(Path.cwd(), ["tests.test_ci_history", "tests.test_ci_dev_tests"], head="a"*40, jobs=8)

    def test_parallel_all_safe_modules_run_in_separate_subprocesses(self):
        from subprocess import CompletedProcess
        seen = []

        def completed(args, **kwargs):
            seen.append((args, kwargs))
            return CompletedProcess(args, 0, "", "Ran 2 tests in 0.002s\n\nOK\n")

        modules = ["tests.test_ci_history", "tests.test_ci_dev_tests"]
        with patch.object(ci_dev_tests.subprocess, "run", side_effect=completed):
            code, result = ci_dev_tests.run_parallel_safe(Path.cwd(), modules, head="a"*40, jobs=2)
        self.assertEqual(code, 0)
        self.assertEqual(result["test_count"], 4)
        self.assertFalse(result["per_test_timings_available"])
        self.assertEqual({args[-1] for args, _ in seen}, set(modules))
        self.assertTrue(all(kwargs.get("timeout") == 600 for _, kwargs in seen))
        self.assertFalse(result["full_suite_waived"])

    def test_parallel_failure_is_not_hidden(self):
        from subprocess import CompletedProcess

        def result(args, **kwargs):
            return CompletedProcess(args, 1 if args[-1] == "tests.test_ci_history" else 0,
                                    "", "Ran 1 test in 0.001s\nFAILED\n")
        with patch.object(ci_dev_tests.subprocess, "run", side_effect=result):
            code, payload = ci_dev_tests.run_parallel_safe(
                Path.cwd(), ["tests.test_ci_dev_tests", "tests.test_ci_history"],
                head="b"*40, jobs=2)
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "FAIL")
