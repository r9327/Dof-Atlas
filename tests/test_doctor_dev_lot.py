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

    def test_shared_text_owner_requires_existing_tests_and_preserves_full(self):
        source = self.root / "app/core/text.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("pass\n", encoding="utf-8")
        owner = self.root / "tests/test_core_text.py"
        owner.write_text("pass\n", encoding="utf-8")
        self.paths = ["app/core/text.py", ".ai/context_index.json"]
        report = self.plan()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["test_modules"], ["tests.test_core_text"])
        self.assertEqual(report["uncovered_paths"], [])
        self.assertTrue(report["global_full_required"])
        self.assertFalse(report["full_suite_waived"])
        self.assertFalse(report["phase_certified"])
        owner.unlink()
        missing = self.plan()
        self.assertEqual(missing["status"], "REVIEW")
        self.assertEqual(missing["uncovered_paths"], ["app/core/text.py"])

    def test_macro_lock_has_existing_generation_owner_without_weaking_full(self):
        # Preserve exact source ownership for native Stop and pointer leases:
        # no generic Organizer smoke or blanket module allowance.
        source = self.root / "app/core/macro_lock.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("pass\\n", encoding="utf-8")
        owned = self.root / "tests/test_organizer_macro_generation.py"
        owned.parent.mkdir(parents=True, exist_ok=True)
        owned.write_text("pass\\n", encoding="utf-8")
        self.paths = [
            "app/core/macro_lock.py",
            "tests/test_organizer_macro_generation.py",
            ".ai/context_index.json",
        ]
        report = self.plan()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["uncovered_paths"], [])
        self.assertEqual(
            report["test_modules"], ["tests.test_organizer_macro_generation"],
        )
        self.assertTrue(report["global_full_required"])
        self.assertFalse(report["phase_certified"])
        owned.unlink()
        # An absent test must not itself be treated as a changed test file.
        # The source-only lot still requires a concrete owner and REVIEWs.
        self.paths = ["app/core/macro_lock.py", ".ai/context_index.json"]
        missing = self.plan()
        self.assertEqual(missing["status"], "REVIEW")
        self.assertEqual(missing["uncovered_paths"], ["app/core/macro_lock.py"])

    def test_pointer_state_and_mirror_worker_have_real_test_owners(self):
        # These are production senders; a broad organizer-domain smoke
        # cannot substitute for an explicit, executable owner.
        for source in ("app/input/input_state.py", "app/macros/mirror_input.py"):
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n", encoding="utf-8")
        self.paths = [
            "app/input/input_state.py", "app/macros/mirror_input.py",
            "tests/test_organizer_sendinput.py", "tests/test_organizer_mirror_ui.py",
        ]
        report = self.plan()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["uncovered_paths"], [])
        self.assertEqual(report["unsupported_paths"], [])
        self.assertEqual(report["test_modules"], [
            "tests.test_organizer_mirror_ui",
            "tests.test_organizer_sendinput",
        ])
        # Targeted tests may run, but the whole PR still requires FULL.
        self.assertTrue(report["global_full_required"])
        self.assertFalse(report["phase_certified"])

    def test_pointer_owner_absence_remains_review_not_false_ready(self):
        self.paths = ["app/input/input_state.py", "app/macros/mirror_input.py"]
        for name in ("test_organizer_mirror_ui.py", "test_organizer_sendinput.py"):
            (self.root / "tests" / name).unlink()
        report = self.plan()
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(
            sorted(report["uncovered_paths"]),
            sorted(self.paths),
        )
        self.assertEqual(report["test_modules"], [])
        self.assertTrue(report["global_full_required"])

    def test_unknown_code_has_explicit_review_not_false_pass(self):
        self.paths = ["app/macros/brand_new_engine.py", "tests/test_organizer_sendinput.py"]
        report = self.plan()
        self.assertEqual(report["status"], "REVIEW")
        self.assertIn("app/macros/brand_new_engine.py", report["uncovered_paths"])

    def test_mirror_report_tool_has_exact_direct_test_owner(self):
        self.paths = [
            "app/macros/switch_click.py",
            "tools/organizer_mirror_log_report.py",
            "tests/test_organizer_mirror_log_report.py",
            "tests/test_organizer_mirror_ui.py",
            ".ai/context_index.json",
        ]
        for name in (
            "tools/organizer_mirror_log_report.py",
            "tests/test_organizer_mirror_log_report.py",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n", encoding="utf-8")
        report = self.plan()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["uncovered_paths"], [])
        self.assertEqual(report["unsupported_paths"], [])
        self.assertEqual(report["test_modules"], [
            "tests.test_organizer_macro_reliability",
            "tests.test_organizer_mirror_log_report",
            "tests.test_organizer_mirror_ui",
        ])
        self.assertTrue(report["global_full_required"])
        self.assertEqual(report["execution"]["status"], "NOT_RUN")
        self.assertFalse(report["phase_certified"])

    def test_unmapped_tool_remains_blocked_even_with_matching_test(self):
        self.paths = [
            "tools/unreviewed_mirror_sender.py",
            "tests/test_unreviewed_mirror_sender.py",
        ]
        name = self.root / "tests/test_unreviewed_mirror_sender.py"
        name.parent.mkdir(parents=True, exist_ok=True)
        name.write_text("pass\\n", encoding="utf-8")
        report = self.plan()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("tools/unreviewed_mirror_sender.py",
                      report["unsupported_paths"])
        self.assertTrue(report["global_full_required"])

    def test_missing_mirror_report_owner_is_review_never_ready(self):
        self.paths = ["tools/organizer_mirror_log_report.py"]
        report = self.plan()
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["uncovered_paths"],
                         ["tools/organizer_mirror_log_report.py"])
        self.assertEqual(report["test_modules"], [])
        self.assertFalse(report["phase_certified"])

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

    def test_cli_uses_explicit_candidate_checkout_not_trusted_tool_directory(self):
        candidate = self.root
        output = candidate / "lot-report.json"
        fake_plan = {
            "status": "READY", "test_modules": ["tests.test_organizer_sendinput"],
            "global_scope_status": "FULL_REQUIRED", "global_full_required": True,
            "phase_certified": False, "full_suite_waived": False,
            "execution": {"status": "NOT_RUN", "exit_code": None},
        }
        with (
            patch.object(doctor_dev_lot, "plan_lot", return_value=fake_plan) as planner,
            patch.object(doctor_dev_lot.ci_scope_gate, "_run_scoped_modules",
                         return_value=0) as runner,
        ):
            code = doctor_dev_lot.main([
                "--repo-root", str(candidate), "--lot-base", LOT_BASE,
                "--pr-base", PR_BASE, "--expected-sha", HEAD,
                "--run", "--output", str(output),
            ])
        self.assertEqual(code, 0)
        planner.assert_called_once_with(
            candidate, lot_base=LOT_BASE, pr_base=PR_BASE, head=HEAD,
        )
        runner.assert_called_once_with(
            candidate.resolve(), ["tests.test_organizer_sendinput"],
        )
        data = __import__("json").loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["execution"]["status"], "PASS")
        self.assertTrue(data["global_full_required"])
        self.assertFalse(data["phase_certified"])

    def test_missing_test_owner_is_not_silently_dropped(self):
        (self.root / "tests/test_organizer_mirror_ui.py").unlink()
        # Direct owner has an explicit second test, so the lot still has
        # diagnostic value; a missing required test is never counted as run.
        report = self.plan()
        self.assertNotIn("tests.test_organizer_mirror_ui", report["test_modules"])
        self.assertTrue(report["global_full_required"])


if __name__ == "__main__":
    unittest.main()
