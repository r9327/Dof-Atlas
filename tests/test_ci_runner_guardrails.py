from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE_BRANCH = "feature/guide-ultime-v5-ui"
CANONICAL_LOCK_MODULE = "tools.audit_guide_ultime_canonical_lock"
CANONICAL_DEPENDENCY_MODULE = "tools.audit_guide_ultime_canonical_dependencies"
FINAL_TRANSVERSAL_MODULE = "tools.validate_guide_ultime_manual_transversals_v16"
GUIDE_RUNNER = ".\\tools\\run_guide_ultime_ci.ps1"


class CiRunnerGuardrailsTests(unittest.TestCase):
    def _workflow(self, name: str) -> str:
        return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")

    def _local_runner(self) -> str:
        return (ROOT / "tools" / "run_guide_ultime_ci.ps1").read_text(encoding="utf-8")

    @staticmethod
    def _test_modules(source: str) -> set[str]:
        return set(re.findall(r"\btests\.test_[A-Za-z0-9_]+\b", source))

    @staticmethod
    def _tool_scripts(source: str) -> set[str]:
        return {
            match.replace("\\", "/")
            for match in re.findall(r"\btools[\\/][A-Za-z0-9_.-]+\.py\b", source)
        }

    def test_public_automatic_workflows_use_github_hosted_windows(self) -> None:
        app = self._workflow("app-ci.yml")
        public_pr = self._workflow("public-pr-ci.yml")

        for label, source in (("app-ci.yml", app), ("public-pr-ci.yml", public_pr)):
            self.assertIn("runs-on: windows-latest", source, label)
            self.assertNotIn("runs-on: [self-hosted, Windows, X64]", source, label)
            self.assertNotIn(FEATURE_BRANCH, source, label)

        self.assertIn("push:", app)
        self.assertNotIn("pull_request:", app)
        self.assertIn("pull_request:", public_pr)
        self.assertNotIn("pull_request_target:", public_pr)

    def test_internal_self_hosted_workflows_are_manual_only(self) -> None:
        owner_main_guard = "github.actor == github.repository_owner && github.ref == 'refs/heads/main'"
        for name in ("guide-ultime-v5-ui.yml", "deep-validation.yml"):
            source = self._workflow(name)
            self.assertIn("workflow_dispatch:", source, name)
            self.assertIn("runs-on: [self-hosted, Windows, X64]", source, name)
            self.assertIn(owner_main_guard, source, name)
            self.assertNotIn("pull_request:", source, name)
            self.assertNotIn("push:", source, name)
            self.assertNotIn("schedule:", source, name)

    def test_ruleset_template_uses_real_blocking_job_names(self) -> None:
        payload = json.loads(
            (ROOT / ".github/rulesets/integration-branch.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["enforcement"], "active")
        self.assertIn("refs/heads/main", payload["conditions"]["ref_name"]["include"])

        rules = {rule["type"]: rule for rule in payload["rules"]}
        self.assertIn("deletion", rules)
        self.assertIn("non_fast_forward", rules)
        self.assertNotIn("required_signatures", rules)

        contexts = {
            item["context"]
            for item in rules["required_status_checks"]["parameters"]["required_status_checks"]
        }
        self.assertIn("Public PR / Safe Validation", contexts)

    def test_deep_workflow_is_manual_seeded_and_full_strength(self) -> None:
        source = self._workflow("deep-validation.yml")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("schedule:", source)
        self.assertIn("runs-on: [self-hosted, Windows, X64]", source)
        self.assertIn("tools.atlas_integrity deep", source)
        self.assertIn("--base-ref HEAD^", source)
        self.assertIn("pip install --require-hashes --no-deps -r requirements-pyside.txt", source)
        self.assertIn("git lfs pull --include=", source)
        self.assertIn("doduda.exe", source)
        self.assertIn("QuestCatalog.load()", source)

    def test_python_313_setup_matches_runner_type(self) -> None:
        app = self._workflow("app-ci.yml")
        self.assertRegex(app, r"uses: actions/setup-python@[0-9a-f]{40}")
        self.assertIn('python-version: "3.13"', app)
        self.assertIn("python --version", app)
        self.assertNotIn("& py -3.13 --version", app)

        for name in ("guide-ultime-v5-ui.yml", "deep-validation.yml"):
            source = self._workflow(name)
            self.assertIn("& py -3.13 --version", source, name)
            self.assertNotIn("actions/setup-python", source, name)

    def test_canonical_lock_ci_keeps_full_git_history(self) -> None:
        for name in (
            "app-ci.yml",
            "public-pr-ci.yml",
            "guide-ultime-v5-ui.yml",
            "deep-validation.yml",
        ):
            source = self._workflow(name)
            self.assertIn("fetch-depth: 0", source, name)
            self.assertNotIn("fetch-depth: 1", source, name)

    def test_app_ci_keeps_public_safe_fast_gate_separate_from_catalog_tests(self) -> None:
        source = self._workflow("app-ci.yml")
        self.assertIn("name: Integrity Policy / Fast Code Validation", source)
        self.assertIn("name: Full Application Suite", source)
        self.assertIn("needs: code-validation", source)
        self.assertIn("Run public-safe integrity checks", source)
        self.assertIn("Run catalog-independent regression suite", source)
        self.assertIn("tools.atlas_meta_integrity", source)
        self.assertIn("tools.check_generated_files", source)
        self.assertIn("tests.test_ci_runner_guardrails", source)
        self.assertIn("tests.test_qt_async_non_accumulation", source)
        self.assertIn("tests.test_security_hardening_guardrails", source)

        fast_block = source[
            source.index("code-validation:") : source.index("  full-validation:")
        ]
        self.assertNotIn("tests.test_quest_visuals_lot6", fast_block)
        self.assertNotIn("tools.atlas_integrity fast", fast_block)
        self.assertNotIn("git lfs pull", fast_block)
        self.assertNotIn("doduda.exe", fast_block)

    def test_app_ci_full_gate_materializes_catalog_before_full_discovery(self) -> None:
        source = self._workflow("app-ci.yml")
        full = source[source.index("  full-validation:") :]

        self.assertIn("runs-on: windows-latest", full)
        self.assertIn("git lfs pull --include=", full)
        self.assertIn("tools/doduda/doduda.exe", full)
        self.assertIn("Materialize local Dofus catalog", full)
        self.assertIn("QuestCatalog.load()", full)
        self.assertIn("count < 1900", full)
        self.assertIn('unittest discover -v -s tests -p "test_*.py"', full)
        self.assertIn(GUIDE_RUNNER, full)

        lfs_index = full.index("git lfs pull --include=")
        catalog_index = full.index("Materialize local Dofus catalog")
        discovery_index = full.index('unittest discover -v -s tests -p "test_*.py"')
        guide_index = full.index(GUIDE_RUNNER)
        self.assertLess(lfs_index, catalog_index)
        self.assertLess(catalog_index, discovery_index)
        self.assertLess(catalog_index, guide_index)

    def test_app_ci_materializes_only_required_visual_lfs_fixtures(self) -> None:
        source = self._workflow("app-ci.yml")
        self.assertIn("lfs: false", source)
        self.assertNotIn("lfs: true", source)
        self.assertIn("git lfs pull --include=", source)
        self.assertIn("unmaterialized LFS pointer", source)
        self.assertIn("git-lfs.github.com/spec/v1", source)
        for quest_id in (26, 29, 55, 72, 260, 691, 1653, 1760, 1851, 2464):
            self.assertIn(
                f"data/encyclopedia/images/quests/{quest_id}/**",
                source,
                str(quest_id),
            )

    def test_app_ci_full_verdict_propagates_every_heavy_failure(self) -> None:
        source = self._workflow("app-ci.yml")
        final = source[source.index("- name: Fail full validation when a full check failed") :]
        for token in (
            "steps.lfs.outcome",
            "steps.catalog.outcome",
            "steps.full_tests.outcome",
            "steps.guide_data.outcome",
        ):
            self.assertIn(token, final)
        self.assertIn("throw", final)

    def test_app_ci_trigger_scope_covers_public_sources_without_local_state(self) -> None:
        source = self._workflow("app-ci.yml")
        for data_path in (
            '"data/encyclopedia/**"',
            '"data/cartography/**"',
            '"data/images/**"',
            '"data/routes/**"',
            '"data/dofus_atlas_world.db"',
        ):
            self.assertIn(data_path, source)

        self.assertNotIn('"data/local/**"', source)
        self.assertIn('"tools/**"', source)
        self.assertIn('"tests/**"', source)
        self.assertIn('"launch.py"', source)
        self.assertIn('"sitecustomize.py"', source)
        self.assertIn('".github/workflows/**"', source)
        self.assertIn('".github/dependabot.yml"', source)

    def test_public_pr_workflow_stays_read_only_and_public_safe(self) -> None:
        source = self._workflow("public-pr-ci.yml")
        self.assertIn("pull_request:", source)
        self.assertIn("      - main", source)
        self.assertIn("runs-on: windows-latest", source)
        self.assertNotIn("self-hosted", source)
        self.assertIn("contents: read", source)
        self.assertIn("Public PR / Safe Validation", source)
        self.assertIn("actions/dependency-review-action@", source)
        self.assertIn("tests.test_project_guardrails", source)
        self.assertIn("tests.test_ci_runner_guardrails", source)
        self.assertIn("tests.test_security_hardening_guardrails", source)

    def test_detailed_guide_ci_materializes_only_its_visual_fixture(self) -> None:
        source = self._workflow("guide-ultime-v5-ui.yml")
        self.assertIn("lfs: false", source)
        self.assertNotIn("lfs: true", source)
        self.assertIn(
            'git lfs pull --include="data/encyclopedia/images/quests/1653/**"',
            source,
        )
        self.assertIn("unmaterialized LFS pointer", source)

    def test_detailed_guide_ci_is_manual_only_and_delegates_to_local_runner(self) -> None:
        source = self._workflow("guide-ultime-v5-ui.yml")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("push:", source)
        self.assertIn(GUIDE_RUNNER, source)
        self.assertNotIn("tests.test_guide_ultime_ocre_registry_runtime", source)
        self.assertNotIn("tools.audit_guide_ultime_canonical_lock", source)
        self.assertNotIn("tools.validate_guide_ultime_manual_bundle", source)

    def test_canonical_dependency_audit_uses_module_invocation_without_path_hack(self) -> None:
        relative = Path(*CANONICAL_DEPENDENCY_MODULE.split(".")).with_suffix(".py")
        source = (ROOT / relative).read_text(encoding="utf-8")
        self.assertTrue((ROOT / relative).is_file())
        self.assertNotIn("sys.path.insert", source)
        self.assertNotIn("import sys", source)

        app_source = self._workflow("app-ci.yml")
        local_source = self._local_runner()
        guide_source = self._workflow("guide-ultime-v5-ui.yml")
        self.assertIn(GUIDE_RUNNER, app_source)
        self.assertIn('"-m", "tools.audit_guide_ultime_canonical_dependencies"', local_source)
        self.assertIn(GUIDE_RUNNER, guide_source)

    def test_route_hook_checks_reference_existing_modules(self) -> None:
        audit_name = "audit_guide_ultime_manual_route_hooks.py"
        old_audit_name = "audit_guide_ultime_manual_transversal_hooks.py"
        test_module = "tests.test_guide_ultime_manual_route_hooks"
        old_test_module = "tests.test_guide_ultime_manual_transversal_hooks"

        self.assertTrue((ROOT / "tools" / audit_name).is_file())
        self.assertTrue((ROOT / "tests" / "test_guide_ultime_manual_route_hooks.py").is_file())

        app_source = self._workflow("app-ci.yml")
        guide_source = self._workflow("guide-ultime-v5-ui.yml")
        local_source = self._local_runner()

        self.assertIn(GUIDE_RUNNER, app_source)
        self.assertIn("tools.audit_guide_ultime_manual_route_hooks", local_source)
        self.assertIn(test_module, local_source)
        self.assertIn(GUIDE_RUNNER, guide_source)
        for label, source in (
            ("app-ci.yml", app_source),
            ("run_guide_ultime_ci.ps1", local_source),
        ):
            self.assertNotIn(old_audit_name, source, label)
            self.assertNotIn(old_test_module, source, label)

    def test_module_safe_final_audits_have_no_path_hack(self) -> None:
        for module in (
            CANONICAL_LOCK_MODULE,
            "tools.validate_guide_ultime_manual_transversals_v15",
            FINAL_TRANSVERSAL_MODULE,
        ):
            relative = Path(*module.split(".")).with_suffix(".py")
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertTrue((ROOT / relative).is_file(), module)
            self.assertNotIn("sys.path.insert", source, module)
            self.assertNotIn("import sys", source, module)
            if module != FINAL_TRANSVERSAL_MODULE:
                self.assertIn("Path(__file__).resolve().parents[1]", source, module)

    def test_remaining_direct_audits_bootstrap_repository_root(self) -> None:
        for relative in (
            "tools/audit_guide_ultime_manual_route_hooks.py",
            "tools/audit_guide_ultime_manual_prerequisites.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("import sys", source, relative)
            self.assertIn("Path(__file__).resolve().parents[1]", source, relative)
            self.assertIn("sys.path.insert(0, str(ROOT))", source, relative)

    def test_shell_route_path_contract_is_platform_neutral(self) -> None:
        source = (ROOT / "tests" / "_pyside_shell_base.py").read_text(encoding="utf-8-sig")
        self.assertIn(
            'path.as_posix().endswith("data/routes/mineur/cristal_liquide_2.png")',
            source,
        )
        self.assertNotIn(r"data\routes\mineur\cristal_liquide_2.png", source)

    def test_local_guide_runner_covers_current_source_progress_and_ui_contracts(self) -> None:
        critical_modules = {
            "tests.test_guide_ultime_manual_structured_domain",
            "tests.test_guide_ultime_stable_progress_keys",
            "tests.test_guide_progress_persistence",
            "tests.test_home_guide_ultime_source",
            "tests.test_quest_detail_guide_ui_contract",
        }
        local_source = self._local_runner()
        self.assertTrue(critical_modules.issubset(self._test_modules(local_source)))
        self.assertIn(
            '"-m", "tools.validate_guide_ultime_manual_transversals_v16"',
            local_source,
        )
        self.assertNotIn(
            '"-m", "tools.validate_guide_ultime_manual_transversals_v15"',
            local_source,
        )

    def test_manual_workflow_and_local_runner_share_one_guide_entrypoint(self) -> None:
        guide_source = self._workflow("guide-ultime-v5-ui.yml")
        local_source = self._local_runner()
        self.assertIn(GUIDE_RUNNER, guide_source)
        self.assertGreaterEqual(len(self._test_modules(local_source)), 20)
        self.assertIn("tools.audit_guide_ultime_canonical_lock", local_source)
        self.assertIn("tools.audit_guide_ultime_canonical_dependencies", local_source)
        self.assertIn("tools.validate_guide_ultime_manual_transversals_v16", local_source)

    def test_runtime_audit_rejects_unsupported_canonical_fields(self) -> None:
        app_source = self._workflow("app-ci.yml")
        local_source = self._local_runner()
        guide_source = self._workflow("guide-ultime-v5-ui.yml")
        self.assertIn(GUIDE_RUNNER, app_source)
        self.assertIn("audit_guide_ultime_manual_runtime", local_source)
        self.assertIn("--strict-fields", local_source)
        self.assertIn(GUIDE_RUNNER, guide_source)

    def test_every_explicit_ci_reference_exists(self) -> None:
        sources = {
            "app-ci.yml": self._workflow("app-ci.yml"),
            "guide-ultime-v5-ui.yml": self._workflow("guide-ultime-v5-ui.yml"),
            "deep-validation.yml": self._workflow("deep-validation.yml"),
            "run_guide_ultime_ci.ps1": self._local_runner(),
        }
        for label, source in sources.items():
            for relative in sorted(self._tool_scripts(source)):
                self.assertTrue((ROOT / relative).is_file(), f"{label}: missing {relative}")
            for module in sorted(self._test_modules(source)):
                relative = Path(*module.split(".")).with_suffix(".py")
                self.assertTrue((ROOT / relative).is_file(), f"{label}: missing {relative}")


if __name__ == "__main__":
    unittest.main()
