from __future__ import annotations

import re
import json
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

    def test_ci_uses_registered_windows_self_hosted_runner(self) -> None:
        for name in ("app-ci.yml", "guide-ultime-v5-ui.yml"):
            source = self._workflow(name)
            self.assertIn("runs-on: [self-hosted, Windows, X64]", source, name)
            self.assertNotIn("ubuntu-latest", source, name)
            self.assertNotIn("windows-latest", source, name)
            self.assertNotIn("macos-latest", source, name)
            self.assertNotIn(FEATURE_BRANCH, source, name)

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

    def test_deep_workflow_is_scheduled_manual_and_seeded(self) -> None:
        source = self._workflow("deep-validation.yml")
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("schedule:", source)
        self.assertIn("tools.atlas_integrity deep", source)
        self.assertIn("--base-ref HEAD^", source)
        self.assertIn("pip install -r requirements-pyside.txt", source)
        self.assertIn("git lfs pull --include=", source)
        self.assertIn("doduda.exe", source)
        self.assertIn("QuestCatalog.load()", source)
        self.assertNotIn("pull_request:", source)

    def test_python_313_is_verified_before_fixture_materialization(self) -> None:
        for name in ("app-ci.yml", "guide-ultime-v5-ui.yml"):
            source = self._workflow(name)
            verify_index = source.index("- name: Verify local Python 3.13")
            fixture_index = source.index("git lfs pull --include=")
            inline_python_index = source.index("@'", fixture_index)
            self.assertLess(verify_index, fixture_index, name)
            self.assertLess(verify_index, inline_python_index, name)
            self.assertIn("& py -3.13 --version", source, name)
            self.assertIn("& py -3.13 -m pip --version", source, name)
            self.assertIn("'@ | & py -3.13 -", source, name)
            self.assertNotIn("actions/setup-python", source, name)

    def test_canonical_lock_ci_keeps_full_git_history(self) -> None:
        for name in ("app-ci.yml", "guide-ultime-v5-ui.yml"):
            source = self._workflow(name)
            self.assertIn("fetch-depth: 0", source, name)
            self.assertNotIn("fetch-depth: 1", source, name)

    def test_app_ci_is_the_single_automatic_pr_validator(self) -> None:
        app = self._workflow("app-ci.yml")
        public_pr = self._workflow("public-pr-ci.yml")

        self.assertIn("push:", app)
        self.assertNotIn("pull_request:", app)
        self.assertIn("runs-on: [self-hosted, Windows, X64]", app)

        self.assertIn("pull_request:", public_pr)
        self.assertIn("      - main", public_pr)
        self.assertIn("runs-on: windows-latest", public_pr)
        self.assertNotIn("self-hosted", public_pr)

        self.assertIn("Public PR / Safe Validation", public_pr)
        self.assertIn("tests.test_project_guardrails", public_pr)

        for data_path in (
            '"data/encyclopedia/**"',
            '"data/cartography/**"',
            '"data/images/**"',
            '"data/routes/**"',
            '"data/dofus_atlas_world.db"',
        ):
            self.assertIn(data_path, app)

        self.assertNotIn('"data/local/**"', app)
        self.assertIn('"tools/**"', app)
        self.assertIn('"tests/**"', app)
        self.assertIn('"launch.py"', app)
        self.assertIn('"sitecustomize.py"', app)
        self.assertIn('".github/workflows/**"', app)
        self.assertIn("unittest discover", app)
        self.assertIn("-m tools.atlas_integrity fast", app)
        self.assertIn(GUIDE_RUNNER, app)

    def test_critical_gates_are_independent_and_propagate_red_status(self) -> None:
        source = self._workflow("app-ci.yml")
        for job_name in (
            "Architecture",
            "Identity / Persistence",
            "Startup / Lazy",
            "Qt Lifecycle / Async",
            "Resource Budgets",
            "Golden Flows",
            "Monolithic Lifecycle",
            "Guide / Quests / Success / Data Integrity",
            "Full Application Suite",
        ):
            self.assertIn(f"name: {job_name}", source)
        for step_name in (
            "Run architecture guardrails",
            "Run canonical identity and persistence contracts",
            "Run startup and lazy-loading contracts",
            "Run Qt lifecycle and non-accumulation contracts",
            "Enforce deterministic resource budgets",
            "Run Guide Quests Success Home golden flows",
            "Run representative lifecycle modules in one process",
            "Run canonical Guide and data integrity runner",
        ):
            block = source[source.index(f"- name: {step_name}") :]
            block = block.split("\n      - name:", 1)[0]
            self.assertNotIn("continue-on-error: true", block, step_name)
            self.assertIn("exit $LASTEXITCODE", block, step_name)

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
        for label, source in (("app-ci.yml", app_source), ("run_guide_ultime_ci.ps1", local_source)):
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
        # The public test module now subclasses the large compatibility base.
        # The path assertion remains owned by that base suite.
        source = (ROOT / "tests" / "_pyside_shell_base.py").read_text(encoding="utf-8-sig")
        self.assertIn('path.as_posix().endswith("data/routes/mineur/cristal_liquide_2.png")', source)
        self.assertNotIn(r'data\routes\mineur\cristal_liquide_2.png', source)

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
        self.assertIn('"-m", "tools.validate_guide_ultime_manual_transversals_v16"', local_source)
        self.assertNotIn('"-m", "tools.validate_guide_ultime_manual_transversals_v15"', local_source)

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
