from __future__ import annotations

import unittest
from unittest.mock import patch
from subprocess import CalledProcessError

from tools.ci_domain_certification import (
    plan_domains, owners_for, exact_git_diff,
)

B = "a" * 40
H = "b" * 40


class ModularDomainRoutingTests(unittest.TestCase):
    def route(self, paths, deleted=()):
        return plan_domains(base_sha=B, candidate_sha=H, paths=paths, deleted=list(deleted))

    def test_ci_policy_change_never_fans_out_into_quests_or_guides(self):
        plan = self.route([
            ".github/workflows/phase-certification.yml",
            "tools/atlas_doctor_lib/ci_orchestrator.py",
            "tests/test_ci_runner_guardrails.py",
            ".ai/context_index.json",
        ])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci"])
        self.assertFalse(plan["full_suite_executed"])
        self.assertFalse(plan["phase_certified"])
        self.assertFalse(plan["merge_authorized"])

    def test_craft_and_policy_changes_require_both_and_not_quests(self):
        plan = self.route(["app/pages/craft_page.py", "tools/ci_scope_gate.py",
                           "tests/test_craft_adapter_release.py"])
        self.assertEqual(plan["domains"], ["ci", "craft"])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertFalse(any(x in plan["domains"] for x in ("quests", "guides")))

    def test_real_quest_owner_selects_quests(self):
        self.assertEqual(self.route(["app/quest_catalog.py"])["domains"], ["quests"])
        self.assertEqual(self.route(["app/pages/quest_page.py"])["domains"], ["quests", "ui"])
        self.assertEqual(self.route(["main.py"])["domains"],
                         ["craft", "quests", "guides", "ui", "startup", "identity", "data"])

    def test_shared_manual_guide_view_requires_guide_and_ui_contracts(self):
        path = "app/modules/encyclopedia/views/shared_manual_guide_view.py"
        self.assertEqual(owners_for(path), frozenset({"guides", "ui"}))
        plan = self.route([path, "app/pages/craft_page.py"])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["craft", "guides", "ui"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(owners_for("app/modules/encyclopedia/views/unknown.py"), frozenset())

    def test_classic_and_manual_guide_readers_require_both_domains(self):
        paths = [
            "app/modules/encyclopedia/views/guides_view.py",
            "app/modules/encyclopedia/views/guide_ultime_manual_view.py",
            "app/modules/encyclopedia/views/guide_ultime_universal_view.py",
            "app/modules/encyclopedia/views/shared_manual_guide_view.py",
        ]
        for path in paths:
            self.assertEqual(owners_for(path), frozenset({"guides", "ui"}))
        plan = self.route(paths)
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["guides", "ui"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(
            self.route(["app/modules/encyclopedia/views/another_reader.py"])["status"],
            "BLOCKED",
        )

    def test_guide_catalog_and_local_skin_assets_have_real_domain_owners(self):
        guide_paths = [
            "app/modules/encyclopedia/views/encyclopedia_page.py",
            "app/modules/encyclopedia/views/guide_catalog_view.py",
            "app/modules/encyclopedia/views/guide_featured_home.py",
            "app/modules/encyclopedia/views/guide_library_sources.py",
            "app/modules/encyclopedia/widgets/guide_card.py",
        ]
        asset_paths = [
            "app/assets/themes/dofus_unity/background_selection_original.png",
            "app/assets/themes/dofus_unity/sprites/btn_green_normal.png",
            "app/assets/themes/dofus_unity/fonts/Lexend-Regular.ttf",
            "docs/design/dofus-unity/sources/atlas_unity_background_original.zip",
            "docs/design/dofus-unity/sources_manifest.json",
            "docs/plans/guides-2026-10-24/06b-dofus-unity-asset-manifest.csv",
        ]
        for path in guide_paths:
            self.assertEqual(owners_for(path), frozenset({"guides", "ui"}), path)
        for path in asset_paths:
            self.assertEqual(owners_for(path), frozenset({"ui", "data"}), path)
        self.assertEqual(owners_for("tools/assets/import_dofus_unity_ui.ps1"),
                         frozenset({"ci", "ui"}))
        self.assertEqual(owners_for("tests/test_unity_skin.py"), frozenset({"ui"}))
        self.assertEqual(owners_for("tests/test_distribution_export.py"),
                         frozenset({"ci", "startup"}))
        self.assertEqual(owners_for("app/pages/_quests_page_impl.py"),
                         frozenset({"quests", "ui"}))
        route = self.route(guide_paths + asset_paths + [
            "tools/assets/import_dofus_unity_ui.ps1", "tests/test_unity_skin.py",
            "tests/test_distribution_export.py",
        ])
        self.assertEqual(route["status"], "READY_TO_EXECUTE")
        self.assertEqual(route["unknown_paths"], [])
        for path in (
            "app/assets/themes/dofus_unity/malware.exe",
            "docs/design/dofus-unity/sources/run.sh",
            "app/modules/encyclopedia/views/guide_unknown_new.py",
            "tests/test_unknown_misc_case.py",
        ):
            self.assertEqual(owners_for(path), frozenset(), path)
            self.assertEqual(self.route([path])["status"], "BLOCKED", path)

    def test_lanyel_shared_manual_ui_test_has_both_owners(self):
        path = "tests/test_lanyel_shared_manual_ui.py"
        self.assertEqual(owners_for(path), frozenset({"guides", "ui"}))
        plan = self.route([path, "app/modules/encyclopedia/views/shared_manual_guide_view.py"])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["guides", "ui"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(owners_for("tests/test_unknown_misc_case.py"), frozenset())

    def test_main_phase_evidence_is_critical_ci_domain_owner(self):
        from tools.ci_domain_certification import owners_for
        path = "tests/test_main_phase_evidence.py"
        self.assertEqual(owners_for(path), frozenset({"ci"}))
        self.assertEqual(self.route([path])["status"], "READY_TO_EXECUTE")
        self.assertEqual(self.route([path])["domains"], ["ci"])

    def test_shared_data_api_requires_all_current_consumers(self):
        plan = self.route(["app/local_data_cache.py", "tools/ci_scope_gate.py"])
        self.assertEqual(plan["domains"], ["ci", "craft", "quests", "guides", "data"])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(self.route(["app/pages/guide_page.py"])["domains"], ["guides", "ui"])
        self.assertEqual(self.route(["local_dofus_data/config.py"])["domains"],
                         ["craft", "quests", "guides", "data"])

    def test_smart_host_proof_is_explicit_ci_owner_without_weakening_unknowns(self):
        path = "tools/ci_smart_host_proof.py"
        self.assertEqual(owners_for(path), frozenset({"ci"}))
        plan = self.route([path, "tests/test_ci_smart_host_proof.py"])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(owners_for("tools/unknown_new_policy.py"), frozenset())
        self.assertEqual(self.route(["tools/unknown_new_policy.py"])["status"], "BLOCKED")

    def test_unknown_owner_blocks_instead_of_launching_full(self):
        plan = self.route(["app/new_cross_domain_provider.py"])
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertEqual(plan["unknown_paths"], ["app/new_cross_domain_provider.py"])
        self.assertNotIn("FULL_SUITE", plan["domains"])

    def test_removal_and_type_changes_cannot_downscope(self):
        path = "tools/atlas_doctor_lib/ci_orchestrator.py"
        plan = self.route([path], [path])
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertIn("REMOVAL_OR_RENAME_REQUIRES_REVIEW", plan["reasons"])

    def test_unsafe_duplicate_missing_identity_fails(self):
        for paths in ([], ["docs/a.md", "docs/a.md"], ["../escape.py"], ["a\\b.py"]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.route(paths)
        with self.assertRaises(ValueError):
            plan_domains(base_sha="bad", candidate_sha=H, paths=["tools/ci_scope_gate.py"])
        with self.assertRaises(ValueError):
            self.route(["tools/ci_scope_gate.py"], ["app/missing.py"])

    def test_git_diff_uses_merge_base_and_zero_terminated_status(self):
        from tools import ci_domain_certification as domain
        with patch.object(domain, "_git", return_value="D\0docs/old.md\0A\0docs/new.md\0"):
            changed, deleted = exact_git_diff(B, H)
            self.assertEqual(changed, ["docs/old.md", "docs/new.md"])
            self.assertEqual(deleted, ["docs/old.md"])
        with patch.object(domain, "_git", return_value="R100\0old.py\0new.py\0"):
            with self.assertRaises(ValueError):
                exact_git_diff(B, H)

    def test_pr_workflow_runs_domain_proofs_not_full_suite(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/phase-certification.yml").read_text(encoding="utf-8")
        self.assertIn("name: Phase Certification / Domain or Release Validation", workflow)
        self.assertIn("Run independently required domain certification", workflow)
        self.assertIn("Materialize selected domain fixtures", workflow)
        self.assertIn('if ($needsCatalog)', workflow)
        self.assertIn('if ($needsCraft)', workflow)
        self.assertIn('python -m scripts.windows.quest_assets --download', workflow)
        self.assertIn('python -m scripts.windows.craft_seed --download', workflow)
        self.assertIn("tools.ci_domain_certification", workflow)
        self.assertIn("github.event_name == 'pull_request'", workflow)
        full_step = workflow.split(
            "      - name: Run full Atlas phase certification gate", 1)[1].split(
            "      - name: Verify public dataset inputs", 1)[0]
        self.assertIn("github.event_name != 'pull_request'", full_step)
        enforce = workflow.split(
            "      - name: Enforce phase certification verdict", 1)[1].split(
            "      - name: Record final Phase outcome diagnostics", 1)[0]
        self.assertIn('steps.domains.outcome', enforce)
        self.assertIn('PASS_DOMAIN_TESTS_NOT_PHASE_CERTIFIED', enforce)
        self.assertIn('DOMAIN CERTIFICATION: PASS (NOT FULL/PHASE RELEASE)', enforce)
        self.assertIn('full_suite_executed', enforce)
        self.assertIn('merge_authorized', enforce)

    def test_draft_preflight_blocks_unknown_domain_before_windows(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/scoped-pr-ci.yml").read_text(encoding="utf-8")
        plan = workflow.index("--output artifacts/doctor_ci/plan.json --json")
        closure = workflow.index("PR domain closure BLOCKED:")
        report = workflow.index("python -m tools.ci_pr_audit")
        self.assertLess(plan, closure)
        self.assertLess(closure, report)
        self.assertIn('domain.get("status") != "READY_TO_EXECUTE"', workflow)

    def test_domain_executor_rejects_failed_skipped_and_missing_tests(self):
        import json
        import sys
        import types
        from pathlib import Path
        from tools import ci_domain_certification as domain
        base_policy = json.dumps({
            "schema_version": 1,
            "groups": {
                "CI_INTEGRITY": {"runner": "unittest_modules", "critical": True, "modules": ["tests.test_doctor_ci_orchestrator"]},
                "ASYNC_LIFECYCLE": {"runner": "unittest_modules", "critical": True, "modules": ["tests.test_domain_mock_case"]},
                "RESOURCE_BUDGETS": {"runner": "unittest_modules", "critical": True, "modules": ["tests.test_domain_mock_case"]},
            },
        })
        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return H
            if args == ("show", f"{B}:tools/atlas_integrity_policy.json"):
                return base_policy
            if args == ("show", f"{B}:tools/atlas_doctor_lib/ci_tooling_scope.py"):
                return 'TESTS = ("doctor_ci_orchestrator",)'
            raise AssertionError("Unanticipated Git trust input: " + str(args))
        plan = self.route(["app/pages/craft_page.py"])
        for behavior in ("ok", "skipped", "failure"):
            module = types.ModuleType("tests.test_domain_mock_case")
            def do_test(self, kind=behavior):
                if kind == "skipped":
                    self.skipTest("Mandatory testcase was skipped")
                if kind == "failure":
                    self.fail("Intentional mandatory test failure")
                self.assertTrue(True)
            case = type("Fixture", (unittest.TestCase,), {"test_domain": do_test})
            case.__module__ = module.__name__
            module.Fixture = case
            # The real tests package starts Qt at import time; these stdlib
            # tests execute on Ubuntu without installing PySide6. A synthetic
            # package models only unittest name resolution, not application Qt.
            fake_tests = types.ModuleType("tests")
            fake_tests.__path__ = []
            fake_tests.test_domain_mock_case = module
            with self.subTest(behavior=behavior), \
                 patch.dict(sys.modules, {"tests": fake_tests, module.__name__: module}), \
                 patch.object(domain, "_git", side_effect=git), \
                 patch.object(domain, "_module_sources", return_value=[module.__name__]):
                evidence = domain.execute_domain_tests(plan, root=Path(__file__).resolve().parents[1], base_sha=B)
                self.assertEqual(evidence["tests_run"], 1)
                self.assertFalse(evidence["phase_certified"])
                self.assertFalse(evidence["merge_authorized"])
                self.assertFalse(evidence["full_suite_executed"])
                status = "PASS_DOMAIN_TESTS_NOT_PHASE_CERTIFIED" if behavior == "ok" else "BLOCKED"
                self.assertEqual(evidence["status"], status)

    def test_executor_cannot_remove_existing_baseline_ci_contracts(self):
        import json
        from pathlib import Path
        from tools import ci_domain_certification as domain
        policy = json.dumps({"schema_version": 1, "groups": {
            "CI_INTEGRITY": {"runner": "unittest_modules", "critical": True, "modules": ["tests.test_doctor_ci_orchestrator"]},
            "ARCHITECTURE": {"runner": "unittest_modules", "critical": True, "modules": ["tests.test_project_guardrails"]},
        }})
        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return H
            if args == ("show", f"{B}:tools/atlas_doctor_lib/ci_tooling_scope.py"):
                return 'TESTS = ("legacy_mandatory_dropped",)'
            if args == ("show", f"{B}:tools/atlas_integrity_policy.json"):
                return policy
            raise AssertionError("Unexpected baseline provenance request")
        with patch.object(domain, "_git", side_effect=git), self.assertRaisesRegex(
            ValueError, "Candidate removed mandatory baseline CI contracts"
        ):
            domain.execute_domain_tests(self.route(["tools/ci_scope_gate.py"]),
                                        root=Path(__file__).resolve().parents[1], base_sha=B)

    def test_a_metadata_only_diff_is_not_application_certification(self):
        plan = self.route(["docs/readme.md", ".ai/context_index.json"])
        self.assertEqual(plan["domains"], ["metadata"])
        self.assertFalse(plan["phase_certified"])


if __name__ == "__main__":
    unittest.main()
