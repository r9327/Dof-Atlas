from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import ci_scope_gate


class ScopeGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        for name in (
            "test_ci_scope_gate", "test_ci_dev_tests", "test_ai_context",
            "test_repository_git_hooks", "test_meta_integrity",
            "test_encyclopedia_on_demand_loading",
            "test_encyclopedia_tab_demand_loading",
            "test_guide_prerequisite_lookup",
        ):
            (self.root / "tests" / (name + ".py")).write_text(
                "# synthetic routing-only file\n", encoding="utf-8"
            )

    def classify(self, paths, **extra):
        return ci_scope_gate.classify_diff(
            self.root, paths, before_sha="abcdef1234", head="fff0123",
            **extra
        )

    def test_selector_or_ai_context_changes_require_full(self):
        for changed in (
            "tools/ci_scope_gate.py",
            "tools/ai_context.py",
            "tests/test_ci_scope_gate.py",
        ):
            with self.subTest(path=changed):
                report = self.classify([changed])
                self.assertEqual(report["status"], "FULL_REQUIRED")
                self.assertIn(
                    "SCOPE_ENGINE_OR_GUIDE_BUILDER_CHANGE", report["reasons"]
                )
                self.assertIn(changed, report["full_only_paths"])
                self.assertFalse(report["certified"])

    def test_guide_builder_is_not_covered_by_only_resolver_unit_tests(self):
        path = "app/modules/encyclopedia/services/guide_catalog_builder.py"
        report = self.classify([path])
        self.assertEqual(report["status"], "FULL_REQUIRED")
        self.assertIn(path, report["full_only_paths"])
        self.assertEqual(report["modules"], [])
        self.assertNotIn(
            "tests.test_guide_prerequisite_lookup",
            ci_scope_gate.KNOWN_COUPLED_MODULES.get(path, ()),
        )

    def test_scope_policy_in_mixed_diff_still_requires_full(self):
        report = self.classify(["tools/ci_dev_tests.py", "tools/ci_scope_gate.py"])
        self.assertEqual(report["status"], "FULL_REQUIRED")
        self.assertIn("SCOPE_ENGINE_OR_GUIDE_BUILDER_CHANGE", report["reasons"])

    def test_small_tool_change_runs_only_its_related_tests(self):
        result = self.classify(["tools/ci_dev_tests.py"])
        self.assertEqual(result["status"], "TARGETED")
        self.assertIn("tests.test_ci_dev_tests", result["modules"])
        self.assertNotIn("tests.test_guide_prerequisite_lookup", result["modules"])
        self.assertFalse(result["full_required"])
        self.assertFalse(result["certified"])
        self.assertFalse(result["full_suite_waived"])

    def test_guide_change_includes_coupled_regression_without_full(self):
        result = self.classify([
            "app/modules/encyclopedia/services/guide_path_profiles.py"
        ])
        self.assertEqual(result["status"], "TARGETED")
        self.assertIn("tests.test_guide_prerequisite_lookup", result["modules"])
        self.assertNotIn("tests.test_guides_catalog_fill", result["modules"])
        self.assertEqual(result["risk"], "MEDIUM")

    def test_mixed_diff_rejects_uncovered_file_even_with_other_test_mappings(self):
        # An exact test for ci_dev_tests must not make an unrelated runtime
        # module look covered just because generic runtime smokes exist.
        result = self.classify([
            "tools/ci_dev_tests.py",
            "app/modules/encyclopedia/services/new_unmapped_logic.py",
        ])
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("INSUFFICIENT_PATH_COVERAGE", result["reasons"])
        self.assertIn(
            "app/modules/encyclopedia/services/new_unmapped_logic.py",
            result["uncovered_paths"],
        )
        self.assertNotIn("tools/ci_dev_tests.py", result["uncovered_paths"])
        self.assertEqual(result["modules"], [])

    def test_generated_index_does_not_force_full_for_known_code_change(self):
        result = self.classify([
            "tools/ci_dev_tests.py",
            ".ai/context_index.json",
        ])
        self.assertEqual(result["status"], "TARGETED")
        self.assertEqual(result["uncovered_paths"], [])
        self.assertIn("tests.test_ci_dev_tests", result["modules"])
        self.assertIn("tests.test_ai_context", result["modules"])

    def test_quality_domain_smoke_does_not_claim_direct_source_coverage(self):
        result = self.classify(["tools/new_unmapped_tool.py"])
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("INSUFFICIENT_PATH_COVERAGE", result["reasons"])

    def test_changed_test_file_must_exist_for_targeted_selection(self):
        missing = self.classify(["tests/test_not_present.py"])
        self.assertEqual(missing["status"], "FULL_REQUIRED")
        self.assertIn("tests/test_not_present.py", missing["uncovered_paths"])
        present = self.classify(["tests/test_ci_dev_tests.py"])
        self.assertEqual(present["status"], "TARGETED")
        self.assertEqual(present["uncovered_paths"], [])

    def test_unknown_changed_path_never_returns_targeted(self):
        result = self.classify(["future_area/new_service.py"])
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("UNCLASSIFIED_PATHS", result["reasons"])
        self.assertEqual(result["modules"], [])

    def test_removed_or_renamed_file_escalates(self):
        result = self.classify(
            ["app/modules/encyclopedia/services/guide_path_profiles.py"],
            deletion_paths=["old_services.py"],
        )
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("REMOVED_OR_RENAMED_FILES", result["reasons"])

    def test_security_and_workflow_changes_escalate(self):
        for changed in (
            "tools/atlas_integrity.py",
            ".github/workflows/app-ci.yml",
            "data/encyclopedia/guides/catalog.json",
            "requirements-pyside.txt",
        ):
            with self.subTest(changed=changed):
                result = self.classify([changed])
                self.assertTrue(result["full_required"])
                self.assertIn("RISK_" + result["risk"], result["reasons"])

    def test_broad_change_escalates(self):
        paths = [f"tests/test_{i}.py" for i in range(14)]
        report = self.classify(paths)
        self.assertEqual(report["status"], "FULL_REQUIRED")
        self.assertIn("BROAD_CHANGE", report["reasons"])

    def test_missing_base_does_not_skip_full(self):
        report = ci_scope_gate.classify_diff(
            self.root, ["tools/ci_dev_tests.py"], before_sha="0" * 40
        )
        self.assertEqual(report["status"], "FULL_REQUIRED")
        self.assertIn("NO_COMPARABLE_BASE", report["reasons"])

    def test_empty_and_uncovered_change_escalate(self):
        self.assertTrue(self.classify([])["full_required"])
        self.assertTrue(self.classify(["tests/test_unrecognised.py"])["full_required"])

    def test_main_ci_chooses_scope_before_canonical_full_job(self):
        root = Path(__file__).resolve().parents[1]
        full = (root / ".github/workflows/app-ci.yml").read_text(encoding="utf-8")
        self.assertIn("name: Full Application Suite", full)
        self.assertIn("name: Run full application test suite", full)
        self.assertIn('unittest discover -v -s tests -p "test_*.py"', full)
        self.assertIn("run_guide_ultime_ci.ps1", full)
        self.assertIn("name: Select test scope for routine main pushes", full)
        self.assertIn("tools.ci_scope_gate", full)
        self.assertIn("needs.code-validation.outputs.full_required == 'true'", full)
        self.assertIn("github.event_name == 'workflow_dispatch'", full)
        self.assertIn("steps.full_tests.outcome", full)

    def test_scoped_pr_feedback_does_not_replace_doctor_fast(self):
        root = Path(__file__).resolve().parents[1]
        scoped = (root / ".github/workflows/scoped-pr-ci.yml").read_text(
            encoding="utf-8"
        )
        pr = (root / ".github/workflows/public-pr-ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("pull_request:", scoped)
        self.assertIn("ref: ${{ env.CANDIDATE_SHA }}", scoped)
        self.assertIn("fetch-depth: 0", scoped)
        self.assertIn("python -X faulthandler -m tools.ci_scope_gate", scoped)
        self.assertNotIn("unittest discover", scoped)
        self.assertNotIn("pull_request_target:", scoped)
        self.assertIn("tools.atlas_doctor verify --gate fast", pr)
        self.assertIn("Public PR / Safe Validation", pr)

    def test_git_name_status_uses_null_separated_tokens(self):
        with mock.patch.object(ci_scope_gate.subprocess, "run") as runner:
            runner.side_effect = [
                mock.Mock(returncode=0),
                mock.Mock(returncode=0, stdout=b"M\x00tools/ci_dev_tests.py\x00R100\x00old.py\x00new.py\x00D\x00old_deleted.py\x00"),
            ]
            paths, deleted = ci_scope_gate.changed_paths(self.root, "abc123")
        self.assertEqual(paths, ["new.py", "old_deleted.py", "tools/ci_dev_tests.py"])
        self.assertEqual(deleted, ["old.py", "old_deleted.py"])

    def test_git_fail_closed_on_bad_diff(self):
        with mock.patch.object(ci_scope_gate.subprocess, "run") as runner:
            runner.side_effect = [
                mock.Mock(returncode=0),
                mock.Mock(returncode=0, stdout=b"R100\x00only-old-name\x00"),
            ]
            with self.assertRaises(ci_scope_gate.ScopeError):
                ci_scope_gate.changed_paths(self.root, "abc123")


if __name__ == "__main__":
    unittest.main()
