from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.dev_events import _name_status_z, dev_event


class DevEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doctor-events-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Doctor")
        self.git("config", "user.email", "doctor@example.invalid")
        (self.root / "app").mkdir()
        self.old = self.root / "app/old.py"
        self.old.write_text("def run(): return 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root,
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_clean_hook_performs_no_work(self):
        result = dev_event(self.root, "pre-commit")
        self.assertEqual(result["changed_count"], 0)
        self.assertEqual(result["status"], "READY")
        self.assertFalse(result["automatic_tests_executed"])
        self.assertFalse(result["graph_rebuilt"])

    def test_staged_rename_is_structural_review_not_blocker(self):
        self.git("mv", "app/old.py", "app/new.py")
        result = dev_event(self.root, "pre-commit")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["changed_files"], ["app/new.py"])
        self.assertEqual(result["source_structural_total"], 1)
        self.assertTrue(result["source_structural_changes"][0]["status"].startswith("R"))

    def test_unstaged_changes_not_reported_by_staged_hook(self):
        self.old.write_text("def run(): return 2\n")
        self.assertEqual(dev_event(self.root, "pre-commit")["changed_count"], 0)
        self.assertEqual(dev_event(self.root, "save", paths=["app/old.py"])["changed_count"], 1)

    def test_push_diff_uses_committed_changes_only(self):
        self.old.write_text("def run(): return 3\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "update")
        result = dev_event(self.root, "push", base_ref=self.base)
        self.assertEqual(result["changed_files"], ["app/old.py"])
        self.assertEqual(result["status"], "READY")

    def test_invalid_paths_and_no_nested_watch(self):
        with self.assertRaises(ValueError):
            dev_event(self.root, "save", paths=["../../unsafe.py"])
        with self.assertRaises(ValueError):
            dev_event(self.root, "push", base_ref="-danger")
        result = dev_event(self.root, "save", paths=["app/old.py"])
        self.assertNotIn("timers", result)

    def test_nul_status_decoding_handles_renames(self):
        changes = _name_status_z(b"R100\0app/old.py\0app/new.py\0M\0app/other.py\0")
        self.assertEqual(changes[0]["before"], "app/old.py")
        self.assertEqual(changes[0]["path"], "app/new.py")
        self.assertEqual(changes[1]["status"], "M")


class DevelopmentPreflightTests(unittest.TestCase):
    def test_scope_is_bounded_and_never_certified(self):
        from unittest.mock import patch
        from tools.atlas_doctor_lib.development_preflight import development_preflight
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app").mkdir()
            (root / "app/item.py").write_text("value = 1\n", encoding="utf-8")
            with patch("tools.atlas_integrity.resolve_base_ref"), \
                 patch("tools.atlas_integrity.changed_files", return_value=["app/item.py"]), \
                 patch("tools.atlas_integrity.repository_head", return_value="a" * 40), \
                 patch("tools.atlas_integrity.load_policy", return_value={
                     "modes": {"FAST": ["ARCHITECTURE"]},
                     "risk_requirements": {"LOW": [], "MEDIUM": [], "HIGH": [], "CRITICAL": []},
                     "groups": {"ARCHITECTURE": {}}}), \
                 patch("tools.ai_context.recommended_tests", return_value=[]):
                report = development_preflight(root, base_ref="main")
            self.assertEqual(report["status"], "PLANNED")
            self.assertEqual(report["syntax"]["checked"], 1)
            self.assertEqual(report["deferred_integrity_groups"], ["ARCHITECTURE"])
            self.assertFalse(report["integrity_executed"])
            self.assertFalse(report["merge_gate_satisfied"])
            self.assertFalse(report["certified"])
            self.assertFalse(report["tests_executed"])

    def test_bad_ast_fails_without_launching_tests(self):
        from unittest.mock import patch
        from tools.atlas_doctor_lib.development_preflight import development_preflight
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app").mkdir()
            (root / "app/broken.py").write_text("def broken(\n", encoding="utf-8")
            with patch("tools.atlas_integrity.resolve_base_ref"), \
                 patch("tools.atlas_integrity.changed_files", return_value=["app/broken.py"]), \
                 patch("tools.atlas_integrity.repository_head", return_value="a" * 40), \
                 patch("tools.atlas_integrity.load_policy", return_value={
                     "modes": {"FAST": ["ARCHITECTURE"]},
                     "risk_requirements": {"LOW": [], "MEDIUM": [], "HIGH": [], "CRITICAL": []},
                     "groups": {"ARCHITECTURE": {}}}), \
                 patch("tools.ai_context.recommended_tests", return_value=[]):
                report = development_preflight(root, base_ref="main")
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["syntax"]["errors"][0]["reason"], "SyntaxError")
            self.assertFalse(report["tests_executed"])

    def test_optional_tests_are_bounded_and_never_count_as_full_gate(self):
        from unittest.mock import patch
        from tools.atlas_doctor_lib.development_preflight import development_preflight
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            folder_tests = root / "tests"
            folder_tests.mkdir()
            (folder_tests / "test_example.py").write_text(
                "import unittest\nclass Smoke(unittest.TestCase):\n"
                "    def test_ok(self): self.assertEqual(2, 2)\n", encoding="utf-8")
            with patch("tools.atlas_integrity.resolve_base_ref"), \
                 patch("tools.atlas_integrity.changed_files", return_value=["tests/test_example.py"]), \
                 patch("tools.atlas_integrity.repository_head", return_value="a" * 40), \
                 patch("tools.atlas_integrity.load_policy", return_value={
                     "modes": {"FAST": ["ARCHITECTURE"]},
                     "risk_requirements": {"LOW": [], "MEDIUM": [], "HIGH": [], "CRITICAL": []},
                     "groups": {"ARCHITECTURE": {}}}), \
                 patch("tools.ai_context.recommended_tests", return_value=["tests.test_example"]), \
                 patch("tools.atlas_doctor_lib.development_preflight._run_focused_tests",
                       return_value={"status": "PASS", "modules": ["tests.test_example"],
                                     "tests_executed": True, "duration_seconds": 0.1}):
                report = development_preflight(root, base_ref="main", run_tests=True)
            self.assertEqual(report["status"], "FOCUSED_CHECKED")
            self.assertEqual(report["targeted_test_selection"]["selected"], ["tests.test_example"])
            self.assertFalse(report["full_suite_waived"])
            self.assertFalse(report["merge_gate_satisfied"])

    def test_missing_deleted_sources_force_review(self):
        from unittest.mock import patch
        from tools.atlas_doctor_lib.development_preflight import development_preflight
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("tools.atlas_integrity.resolve_base_ref"), \
                 patch("tools.atlas_integrity.changed_files", return_value=["app/deleted.py"]), \
                 patch("tools.atlas_integrity.repository_head", return_value="a" * 40), \
                 patch("tools.atlas_integrity.load_policy", return_value={
                     "modes": {"FAST": ["ARCHITECTURE"]},
                     "risk_requirements": {"LOW": [], "MEDIUM": [], "HIGH": [], "CRITICAL": []},
                     "groups": {"ARCHITECTURE": {}}}), \
                 patch("tools.ai_context.recommended_tests", return_value=[]):
                report = development_preflight(root, base_ref="main")
            self.assertEqual(report["status"], "FAIL")
            self.assertFalse(report["certified"])


if __name__ == "__main__":
    unittest.main()
