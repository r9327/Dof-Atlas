from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import doctor_dev_lot


HEAD = "a" * 40
LOT_BASE = "b" * 40
PR_BASE = "c" * 40


class DevelopmentLotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = [
            "app/input/mouse_hooks.py", "app/macros/switch_click.py",
            "tests/test_organizer_sendinput.py", "tests/test_organizer_mirror_ui.py",
            "docs/organizer/mirror-feasibility.md", ".ai/context_index.json",
        ]
        for path in (*self.paths, "tests/test_organizer_macro_reliability.py"):
            p = self.root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("pass\n", encoding="utf-8")

    def git(self, root, *args):
        if args == ("rev-parse", "HEAD"):
            return HEAD
        if args == ("status", "--porcelain", "--untracked-files=no"):
            return ""
        if args[:2] == ("rev-parse", "--verify"):
            return args[2].split("^")[0]
        if args[:2] == ("merge-base", "--is-ancestor"):
            return ""
        if args[:2] == ("rev-list", "--count"):
            return "10"
        raise AssertionError(args)

    def changed_paths(self, root, base):
        return (self.paths, []) if base == LOT_BASE else (["app/other.py"] * 52, [])

    def scope(self, *args, **kwargs):
        return {
            "status": "FULL_REQUIRED", "full_required": True,
            "reasons": ["BROAD_CHANGE", "RISK_HIGH"], "modules": [],
        }

    def plan(self):
        with (
            patch.object(doctor_dev_lot, "_git", side_effect=self.git),
            patch.object(doctor_dev_lot.ci_scope_gate, "changed_paths",
                         side_effect=self.changed_paths),
            patch.object(doctor_dev_lot.ci_scope_gate, "classify_diff",
                         side_effect=self.scope),
        ):
            return doctor_dev_lot.plan_lot(
                self.root, lot_base=LOT_BASE, pr_base=PR_BASE, head=HEAD,
            )

    def test_large_pr_remains_full_while_small_lot_has_real_owner_tests(self):
        report = self.plan()
        self.assertEqual(report["status"], "READY")
        self.assertTrue(report["global_full_required"])
        self.assertEqual(report["global_scope_status"], "FULL_REQUIRED")
        self.assertEqual(report["lot_commits"], 10)
        self.assertEqual(report["test_modules"], [
            "tests.test_organizer_macro_reliability",
            "tests.test_organizer_mirror_ui",
            "tests.test_organizer_sendinput",
        ])
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["full_suite_waived"])
        self.assertEqual(report["execution"]["status"], "NOT_RUN")

    def test_unknown_code_has_explicit_review_not_false_pass(self):
        self.paths = ["app/macros/brand_new_engine.py", "tests/test_organizer_sendinput.py"]
        report = self.plan()
        self.assertEqual(report["status"], "REVIEW")
        self.assertIn("app/macros/brand_new_engine.py", report["uncovered_paths"])

    def test_workflow_and_policy_changes_are_blocked(self):
        for path in ("tools/ci_scope_gate.py", ".github/workflows/phase-certification.yml"):
            with self.subTest(path=path):
                self.paths = [path, "tests/test_organizer_sendinput.py"]
                report = self.plan()
                self.assertEqual(report["status"], "BLOCKED")
                self.assertIn(path, report["unsupported_paths"])
                self.assertTrue(report["global_full_required"])

    def test_oversized_or_deleted_lot_is_blocked(self):
        self.paths = [f"app/macros/changed_{i}.py" for i in range(17)]
        with self.assertRaisesRegex(ValueError, "oversized"):
            self.plan()
        self.paths = ["app/input/mouse_hooks.py"]
        with patch.object(doctor_dev_lot.ci_scope_gate, "changed_paths",
                          return_value=(self.paths, ["app/input/deleted.py"])), patch.object(
                          doctor_dev_lot, "_git", side_effect=self.git):
            with self.assertRaisesRegex(ValueError, "deleted"):
                doctor_dev_lot.plan_lot(
                    self.root, lot_base=LOT_BASE, pr_base=PR_BASE, head=HEAD)

    def test_no_ancestor_or_stale_checkout_rejected(self):
        def invalid_ancestor(root, *args):
            if args[0] == "merge-base":
                raise ValueError("Git revision / ancestry validation failed")
            return self.git(root, *args)
        with patch.object(doctor_dev_lot, "_git", side_effect=invalid_ancestor):
            with self.assertRaises(ValueError):
                doctor_dev_lot.plan_lot(
                    self.root, lot_base=LOT_BASE, pr_base=PR_BASE, head=HEAD)
        with self.assertRaisesRegex(ValueError, "exact lowercase"):
            doctor_dev_lot.plan_lot(
                self.root, lot_base="not-a-sha", pr_base=PR_BASE, head=HEAD)

    def test_missing_test_owner_is_not_silently_dropped(self):
        (self.root / "tests/test_organizer_mirror_ui.py").unlink()
        # Direct owner has an explicit second test, so the lot still has
        # diagnostic value; a missing required test is never counted as run.
        report = self.plan()
        self.assertNotIn("tests.test_organizer_mirror_ui", report["test_modules"])
        self.assertTrue(report["global_full_required"])


if __name__ == "__main__":
    unittest.main()
