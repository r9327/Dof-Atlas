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

    def test_reviewed_organizer_files_get_strict_cross_domain_ownership(self):
        # Neither an unrelated macro nor a future native hook gets a free pass.
        cases = {
            "app/macros/zaap.py": {"organizer", "ui", "identity"},
            "app/macros/direction.py": {"organizer", "ui", "identity"},
            "app/macros/mirror_plan.py": {"organizer", "ui", "identity"},
            "app/pages/organizer/radial_selection.py": {"organizer", "ui", "identity"},
            "app/pages/organizer/radial_overlay.py": {"organizer", "ui", "identity"},
            "app/core/runtime_state.py": {"organizer", "ui", "startup", "identity"},
            "app/pages/organizer_page.py": {"organizer", "ui", "startup", "identity"},
            "app/pages/organizer/character_sessions.py": {"organizer", "ui", "identity", "data"},
            "app/windows/clicks.py": {"organizer", "ui", "startup", "identity"},
            "tests/test_organizer_sendinput.py": {"organizer", "ui", "identity"},
            "tests/test_organizer_macro_reliability.py": {"organizer", "ui", "identity"},
            "tests/test_organizer_mirror_plan.py": {"organizer", "ui", "identity"},
            "tests/test_organizer_radial_overlay.py": {"organizer", "ui", "identity"},
            "tests/test_organizer_hotkey_capture.py": {"organizer", "ui", "identity"},
            "docs/organizer/radial-selector.md": {"organizer", "ui", "identity"},
            "docs/organizer/mirror-feasibility.md": {"organizer", "ui", "identity"},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset(expected))
                planned = self.route([path])
                self.assertEqual(planned["status"], "READY_TO_EXECUTE")
                self.assertEqual(planned["unknown_paths"], [])
                self.assertIn("organizer", planned["domains"])
                self.assertFalse(planned["phase_certified"])
        for unknown in ("app/macros/unreviewed.py",
                        "app/core/unreviewed_runtime.py",
                        "tests/test_organizer_unreviewed_backend.py"):
            with self.subTest(unknown=unknown):
                self.assertFalse(owners_for(unknown))
                self.assertEqual(self.route([unknown])["status"], "BLOCKED")
        # Generic Markdown is classified as advisory metadata by the existing
        # planner, not an executable unknown owner. Preserve that contract:
        # it must not silently acquire the Organizer domain.
        generic_doc = "docs/organizer/unreviewed-contract.md"
        self.assertFalse(owners_for(generic_doc))
        self.assertNotIn("organizer", self.route([generic_doc])["domains"])

    def test_delivery_contract_and_guard_are_ci_owned(self):
        for path in ("tools/ci_delivery_guard.py",
                     ".github/pull_request_template.md", "AGENTS.md",
                     ".github/workflows/delivery-guard.yml",
                     "tests/test_ci_delivery_guard.py"):
            self.assertEqual(owners_for(path), frozenset({"ci"}), path)

    def test_pr303_bundled_preloads_and_qt_ram_contracts_have_exact_owners(self):
        exact = {
            "scripts/windows/build_guide_rewards.py": {"ci", "startup", "guides", "data"},
            "scripts/windows/build_guide_routes.py": {"ci", "startup", "guides", "data"},
            "scripts/windows/build_quest_index.py": {"ci", "startup", "quests", "data"},
            "docs/performance/atlas-ram-inventory-v1.json": {"ci"},
            "docs/performance/pr303-audit-candidats-20261031.json": {"ci"},
            "docs/performance/pr303-audit-commits-20261031.json": {"ci"},
            "tests/test_organizer_layout.py": {"ui", "identity"},
            "tests/test_world_scan_async_loading.py": {"ui"},
            "tests/test_startup_preload_window_visibility.py": {"startup", "ui"},
        }
        for path, owners in exact.items():
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset(owners))
        plan = self.route(list(exact))
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertFalse(plan["full_suite_executed"])
        for path in (
            "scripts/windows/build_unreviewed_cache.py",
            "docs/performance/new-ram-registry.json",
            "docs/performance/pr303-audit-unreviewed.json",
            "tests/test_unknown_layout.py",
        ):
            self.assertFalse(owners_for(path), path)
            self.assertEqual(self.route([path])["status"], "BLOCKED")

    def test_pr303_release_fallback_and_final_audit_paths_have_exact_owners(self):
        release_owners = {"ci", "craft", "quests", "guides", "ui", "startup", "data"}
        exact = {
            "app/cartography/map_asset_loader.py": {"ui", "data"},
            "tests/test_cartography_asset_readonly_fallback.py": {"ui", "data"},
            "scripts/windows/release_lfs_assets.py": release_owners,
            "scripts/windows/release_lfs_assets_lock.json": release_owners,
            "scripts/windows/runtime_visual_assets.py": release_owners,
            "scripts/windows/runtime_visual_assets_lock.json": release_owners,
            "tests/test_distribution_runtime_assets.py": release_owners,
            "tests/test_ganymede_live_cutover_inventory.py": {"guides", "data"},
            "tests/test_pr303_commit_audit.py": {"ci"},
            "tools/audit_pr303_commits.py": {"ci"},
            "tools/doctor_candidate_worklist.py": {"ci"},
        }
        for path, expected in exact.items():
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset(expected))
        plan = self.route(list(exact))
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        for path in (
            "scripts/windows/unreviewed_release_assets.py",
            "app/cartography/unreviewed_loader.py",
            "tools/doctor_unreviewed_worklist.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(owners_for(path))
                self.assertEqual(self.route([path])["status"], "BLOCKED")

    def test_expensive_windows_specialists_wait_for_ready_not_draft(self):
        from pathlib import Path
        workflows = Path(__file__).resolve().parents[1] / ".github/workflows"
        for name in (
            "atlas-short-full-app.yml",
            "atlas-exhaustive-benchmark.yml",
        ):
            with self.subTest(workflow=name):
                content = (workflows / name).read_text(encoding="utf-8")
                self.assertIn("ready_for_review", content)
                self.assertIn("workflow_call:", content)
                self.assertIn("workflow_dispatch:", content)
                self.assertIn(
                    "if: ${{ github.event_name != 'pull_request' || "
                    "github.event.pull_request.draft == false }}",
                    content,
                )
        focused = (workflows / "guides-focused-proof.yml").read_text(encoding="utf-8")
        self.assertIn("types: [synchronize, ready_for_review]", focused)
        self.assertIn("if: ${{ github.event.pull_request.draft == false }}", focused)

    def test_pr303_late_preload_and_doctor_paths_have_reviewed_owners(self):
        # The exact seven unknown paths surfaced by the SHA-specific Draft
        # domain closure are cross-domain; a filename heuristic must not
        # silently convert a Success/Qt test into Craft-only coverage.
        expected = {
            "app/modules/encyclopedia/views/memory_bound_encyclopedia_page.py":
                {"quests", "guides", "ui", "startup"},
            "app/startup_cache_domain_worker.py":
                {"startup", "quests", "guides", "data"},
            "tests/test_encyclopedia_success_detail_prewarm.py":
                {"startup", "quests", "guides", "ui"},
            "tests/test_success_async_detail_runtime.py":
                {"quests", "guides", "ui"},
            "tools/benchmark_phase8_preload.py":
                {"ci", "startup", "quests", "guides", "ui"},
            "tools/doctor_scenario_runner.py": {"ci"},
            "tools/tool_catalog.py": {"ci"},
        }
        for path, owners in expected.items():
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset(owners))
                self.assertEqual(self.route([path])["status"], "READY_TO_EXECUTE")
        plan = self.route(list(expected))
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(plan["domains"],
                         ["ci", "quests", "guides", "ui", "startup", "data"])
        self.assertFalse(plan["full_suite_executed"])
        self.assertFalse(plan["merge_authorized"])
        for unknown in (
            "app/startup_cache_unreviewed_worker.py",
            "app/modules/encyclopedia/views/memory_bound_unreviewed_page.py",
            "tests/test_success_unreviewed_runtime.py",
            "tools/benchmark_phase8_unreviewed.py",
            "tools/doctor_unknown_runner.py",
        ):
            with self.subTest(unknown=unknown):
                self.assertFalse(owners_for(unknown))
                self.assertEqual(self.route([unknown])["status"], "BLOCKED")

    def test_batch_quest_evidence_has_guide_and_startup_consumers(self):
        for path in (
            "app/quest_catalog_details.py",
            "app/modules/encyclopedia/providers/quest_provider.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset({"quests", "guides", "startup"}))
                self.assertEqual(self.route([path])["status"], "READY_TO_EXECUTE")
        self.assertFalse(owners_for("app/unreviewed_backend_details.py"))
        self.assertEqual(self.route(["app/unreviewed_backend_details.py"])["status"], "BLOCKED")

    def test_achievement_qt_view_has_cross_domain_ownership_without_wildcards(self):
        path = "app/modules/encyclopedia/views/achievements_view.py"
        self.assertEqual(owners_for(path), frozenset({"quests", "guides", "ui"}))
        result = self.route([path])
        self.assertEqual(result["status"], "READY_TO_EXECUTE")
        self.assertEqual(result["domains"], ["quests", "guides", "ui"])
        self.assertEqual(result["unknown_paths"], [])
        for unknown in (
            "app/modules/encyclopedia/views/achievements_unreviewed_view.py",
            "app/modules/encyclopedia/views/unknown_success_detail.py",
        ):
            self.assertFalse(owners_for(unknown))
            self.assertEqual(self.route([unknown])["status"], "BLOCKED")

    def test_doctor_performance_lab_has_exact_ci_ownership_only(self):
        paths = [
            "tools/atlas_doctor.py",
            "tools/atlas_perf_attribution.py",
            "tools/benchmark_atlas_exhaustive.py",
            "tests/test_atlas_exhaustive_benchmark.py",
            "tests/test_atlas_doctor_full_scope.py",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset({"ci"}))
        plan = self.route(paths + [
            "tools/atlas_doctor_lib/exhaustive_performance.py",
            "tests/test_doctor_exhaustive_performance.py",
            ".github/workflows/atlas-exhaustive-benchmark.yml",
        ])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci"])
        self.assertEqual(plan["unknown_paths"], [])
        for unrelated in (
            "tools/benchmark_unreviewed.py", "tools/atlas_perf_unreviewed.py",
            "tests/test_atlas_exhaustive_unreviewed.py",
        ):
            self.assertFalse(owners_for(unrelated))
            self.assertEqual(self.route([unrelated])["status"], "BLOCKED")

    def test_doctor_agent_protocol_test_is_explicit_ci_owned(self):
        known = "tests/test_atlas_doctor_agent_protocol.py"
        unknown = "tests/test_atlas_doctor_unreviewed.py"
        self.assertEqual(owners_for(known), frozenset({"ci"}))
        self.assertEqual(self.route([known])["status"], "READY_TO_EXECUTE")
        self.assertEqual(self.route([known])["unknown_paths"], [])
        self.assertFalse(owners_for(unknown))
        self.assertEqual(self.route([unknown])["status"], "BLOCKED")

    def test_reviewed_ai_skills_are_ci_owned_without_opening_unknown_paths(self):
        from tools.ci_domain_certification import REVIEWED_CI_INSTRUCTION_PATHS

        # All 11 new paths reuse the existing, canonical reviewed-path set.
        new_paths = (
            ".ai/context-map.yaml",
            ".ai/scopes/quality_ci.yaml",
            "tests/test_ai_workflow_skills.py",
            ".agents/skills/codebase-navigation/SKILL.md",
            ".agents/skills/dofus-data-provenance/SKILL.md",
            ".agents/skills/evidence-driven-validation/SKILL.md",
            ".agents/skills/performance-triage/SKILL.md",
            ".agents/skills/persistence-safety/SKILL.md",
            ".agents/skills/pyside6-qtwebengine/SKILL.md",
            ".agents/skills/root-cause-debugging/SKILL.md",
            ".agents/skills/safe-architecture-cleanup/SKILL.md",
        )
        self.assertEqual(len(set(new_paths)), len(new_paths))
        self.assertTrue(set(new_paths).issubset(REVIEWED_CI_INSTRUCTION_PATHS))
        for path in new_paths:
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset({"ci"}))
        plan = self.route(list(new_paths) + [
            ".github/workflows/ai-context-ci.yml", ".ai/context_index.json",
        ])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(plan["domains"], ["ci"])
        for path in (
            ".agents/skills/unreviewed/SKILL.md",
            ".agents/skills/unreviewed/execute.py",
            ".ai/scopes/unreviewed.yaml",
            "tests/test_unknown_ai_workflow.py",
        ):
            self.assertFalse(owners_for(path), path)
            self.assertEqual(self.route([path])["status"], "BLOCKED", path)

    def test_ci_router_ui_exclusion_requires_independent_import_evidence(self):
        # Real UI classifier, not a caller-supplied UI_NONE stub. This regression
        # covers the Draft diagnostic that previously reported UNMAPPED_DEPENDENCY.
        from tools.atlas_doctor_lib.ci_orchestrator import select_workflows
        from tools.atlas_doctor_lib.doctor_ui_ci import classify_ui, ROOT

        paths = ["tools/ci_domain_certification.py", "tests/test_ci_domain_certification.py"]
        domain = self.route(paths)
        self.assertEqual(domain["domains"], ["ci"])
        ui = classify_ui(ROOT, paths, candidate_sha=H, base_sha=B)
        self.assertEqual(ui["status"], "NOT_APPLICABLE", ui["uncertainty"])
        self.assertEqual(ui["selected_scenarios"], [])
        selection = select_workflows(
            paths, event="pull_request", phase_route={"route": "FULL"},
            ui_plan=ui, domain_plan=domain, tooling_scope=False,
        )
        self.assertTrue(selection["full"])  # Risk marker, never evidence of FULL.
        self.assertFalse(selection["specialist_fallback"])
        self.assertFalse(selection["workflows"]["doctor-ui"]["selected"])
        self.assertTrue(selection["workflows"]["ai-context-ci"]["selected"])
        self.assertTrue(selection["workflows"]["signature-report"]["selected"])
        self.assertTrue(selection["workflows"]["graphify-targeted-ci"]["selected"])

    def test_ci_router_ui_exclusion_fails_closed_if_runtime_boundary_changes(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from tools.atlas_doctor_lib.doctor_ui_ci import classify_ui

        for source in (
            "from app import ui\n",
            "from app.ui import theme\n",
            "from PySide6 import QtWidgets\n",
            "__import__('app.ui.theme')\n",
            "import importlib\nimportlib.import_module('app.ui.theme')\n",
            "from importlib import import_module as load\nload('app.ui.theme')\n",
            "from builtins import __import__ as loader\nloader('app.ui.theme')\n",
        ):
            with self.subTest(source=source), TemporaryDirectory() as folder:
                root = Path(folder)
                target = root / "tools/ci_domain_certification.py"
                target.parent.mkdir(parents=True)
                target.write_text(source, encoding="utf-8")
                report = classify_ui(root, ["tools/ci_domain_certification.py"],
                                     candidate_sha=H, base_sha=B)
                self.assertEqual(report["status"], "REVIEW_REQUIRED")
                self.assertTrue(report["uncertainty"])

    def test_reviewed_ai_and_certification_instructions_are_ci_owned(self):
        from tools.phase_adaptive_gate import critical_changed
        paths = [
            "AGENTS.md", "AI_ENTRYPOINT.md", "CLAUDE.md",
            ".github/copilot-instructions.md", ".cursor/rules/atlas-doctor.mdc",
            "app/AGENTS.md", "data/AGENTS.md", "tests/AGENTS.md",
            "tools/AGENTS.md", "tools/skills/dofus-atlas-tools/SKILL.md",
            "PHASE_CERTIFICATION.md", "DOCTOR_ADAPTIVE_CERTIFICATION.md",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset({"ci"}))
                self.assertEqual(self.route([path])["domains"], ["ci"])
        plan = self.route(paths)
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertFalse(plan["full_suite_executed"])
        self.assertFalse(plan["phase_certified"])
        # Domain ownership never relaxes the independent root-of-trust check.
        self.assertIn("PHASE_CERTIFICATION.md", critical_changed(paths))

    def test_unreviewed_agent_policies_still_fail_closed(self):
        for path in (
            ".cursor/rules/unreviewed.mdc",
            "tools/skills/unreviewed/SKILL.md",
            "app/modules/encyclopedia/AGENTS.md",
            "NEW_AGENT_POLICY.md",
            "DEVELOPMENT_GUARDRAILS.md",
        ):
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset())
                self.assertEqual(self.route([path])["status"], "BLOCKED")
        self.assertEqual(
            self.route(["AGENTS.md", "app/modules/encyclopedia/AGENTS.md"])["status"],
            "BLOCKED",
        )
        deleted = self.route(["AI_ENTRYPOINT.md"], deleted=["AI_ENTRYPOINT.md"])
        self.assertEqual(deleted["status"], "BLOCKED")
        self.assertIn("REMOVAL_OR_RENAME_REQUIRES_REVIEW", deleted["reasons"])

    def test_mixed_policy_and_application_domains_remain_separate(self):
        plan = self.route([
            "PHASE_CERTIFICATION.md", "AGENTS.md",
            "app/pages/guide_page.py",
        ])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci", "guides", "ui"])
        self.assertNotIn("metadata", plan["domains"])

    def test_mixed_release_regression_test_has_explicit_reviewed_owners(self):
        path = "tests/test_release_certification_fixes.py"
        self.assertEqual(owners_for(path), frozenset({"ci", "craft", "guides"}))
        plan = self.route([path])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci", "craft", "guides"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(owners_for("tests/test_unknown_release_contract.py"), frozenset())

    def test_extended_memory_workflow_regression_is_ci_and_craft_owned(self):
        path = "tests/test_phase8_lifecycle_extended_contract.py"
        self.assertEqual(owners_for(path), frozenset({"ci", "craft"}))
        plan = self.route([path])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci", "craft"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertFalse(owners_for("tests/test_phase8_unreviewed_contract.py"))

    def test_manual_rtk_bootstrap_has_narrow_ci_ownership(self):
        paths = ["tools/install_rtk.ps1", "tests/test_install_rtk.py"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset({"ci"}))
        plan = self.route(paths)
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["domains"], ["ci"])
        self.assertEqual(plan["unknown_paths"], [])
        self.assertFalse(owners_for("tools/install_unreviewed.ps1"))
        self.assertFalse(owners_for("tests/test_install_unreviewed.py"))

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
        self.assertEqual(owners_for("tests/test_theme_runtime_cache.py"),
                         frozenset({"ui"}))
        self.assertEqual(owners_for("tests/test_distribution_export.py"),
                         frozenset({"ci", "startup"}))
        self.assertEqual(owners_for("app/pages/_quests_page_impl.py"),
                         frozenset({"quests", "ui"}))
        route = self.route(guide_paths + asset_paths + [
            "tools/assets/import_dofus_unity_ui.ps1", "tests/test_unity_skin.py",
            "tests/test_theme_runtime_cache.py", "tests/test_distribution_export.py",
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

    def test_smart_installer_paths_have_explicit_shared_owners(self):
        reviewed = (
            "app/distribution/install.py",
            "app/distribution/release_client.py",
            "app/distribution/disk_space.py",
            "app/distribution/file_clone.py",
            "app/distribution/cleanup.py",
            "app/distribution/install_location.py",
            "tests/test_distribution_disk_space.py",
            "tests/test_distribution_smart_update.py",
            "tests/test_distribution_packaging.py",
        )
        for path in reviewed:
            with self.subTest(path=path):
                self.assertEqual(
                    owners_for(path), frozenset({"ci", "startup", "data"})
                )
        plan = self.route(list(reviewed))
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        # Deliberately refuse not-yet-reviewed updater modules and tests.
        self.assertFalse(owners_for("app/distribution/unchecked_helper.py"))
        self.assertFalse(owners_for("tests/test_distribution_new_unchecked.py"))
        self.assertEqual(
            self.route(["app/distribution/unchecked_helper.py"])["status"],
            "BLOCKED",
        )

    def test_launcher_ui_and_qt_preload_have_exact_shared_owners(self):
        paths = [
            "app/distribution/launcher.py",
            "app/distribution/launcher_ui.py",
            "app/ui/preload_popup.py",
            "tests/test_distribution_launcher_branding.py",
        ]
        for path in paths[:3]:
            self.assertEqual(owners_for(path), frozenset({"startup", "ui"}), path)
        plan = self.route(paths)
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(plan["domains"], ["ui", "startup"])
        # Never approve arbitrary updater, helper or executable paths.
        for path in (
            "app/distribution/unreviewed_updater.py",
            "app/distribution/new_helper.exe",
        ):
            self.assertEqual(owners_for(path), frozenset(), path)
            self.assertEqual(self.route([path])["status"], "BLOCKED")

    def test_pr254_local_proofs_and_packaging_close_domains_without_wildcards(self):
        # Exact 10 paths independently identified by the Draft CI failure.
        expected = {
            "scripts/windows/package_release.py": {"ci", "ui", "startup", "data"},
            "tests/test_distribution_package.py": {"ci", "startup"},
            "tests/test_unity_assets_inventory.py": {"ui", "data"},
            "tests/test_unity_cycle_metrics.py": {"guides", "ui"},
            "tests/test_unity_pre_ci_runner.py": {"ci", "startup"},
            "tests/test_unity_wallpaper_cleaner.py": {"ui", "data"},
            "tools/assets/clean_unity_wallpaper.py": {"ci", "ui", "data"},
            "tools/assets/inspect_unity_assets.py": {"ci", "ui", "data"},
            "tools/assets/unity_local_cycle_probe.py": {"ci", "guides", "ui"},
            "tools/assets/unity_pre_ci.py": {"ci", "guides", "ui", "startup", "data"},
        }
        for path, owners in expected.items():
            self.assertEqual(owners_for(path), frozenset(owners), path)
        route = self.route(sorted(expected))
        self.assertEqual(route["status"], "READY_TO_EXECUTE")
        self.assertEqual(route["unknown_paths"], [])
        self.assertEqual(
            route["domains"], ["ci", "guides", "ui", "startup", "data"]
        )
        for path in (
            "tools/assets/unknown_installer.py",
            "scripts/windows/unreviewed_export.py",
            "tests/test_unity_unknown_example.py",
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

    def test_existing_corrective_suites_have_exact_cross_domain_owners(self):
        expected = {
            "tests/test_truthful_module_availability.py": {"craft", "ui", "startup"},
            "tests/test_encyclopedia_corrective.py": {"quests", "guides", "ui", "data"},
        }
        for path, owners in expected.items():
            self.assertEqual(owners_for(path), frozenset(owners), path)
        plan = self.route(sorted(expected))
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(
            plan["domains"],
            ["craft", "quests", "guides", "ui", "startup", "data"],
        )
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(owners_for("tests/test_availability_unreviewed.py"), frozenset())

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

    def test_eight_atlas_shared_cache_files_have_reviewed_cross_domain_owners(self):
        affected = {
            "app/startup_cache_warmup.py": {"startup", "quests", "guides", "data"},
            "app/core/cache_write_lock.py": {"startup", "quests", "guides", "data"},
            "app/modules/encyclopedia/services/achievement_index_warmup.py":
                {"startup", "quests", "guides"},
        }
        for path, domains in affected.items():
            with self.subTest(path=path):
                self.assertEqual(owners_for(path), frozenset(domains))
        plan = self.route(list(affected) + [
            "tools/ci_domain_certification.py",
            ".github/workflows/atlas-doctor-complete-benchmark.yml",
        ])
        self.assertEqual(plan["status"], "READY_TO_EXECUTE")
        self.assertEqual(plan["unknown_paths"], [])
        self.assertEqual(set(plan["domains"]),
                         {"ci", "quests", "guides", "startup", "data"})
        # Do not create a loophole for a new cache worker or unrelated module.
        self.assertEqual(owners_for("app/startup_cache_unreviewed.py"), frozenset())
        self.assertEqual(owners_for("app/core/cache_write_lock_unreviewed.py"), frozenset())
        self.assertEqual(self.route(["app/core/cache_write_lock_unreviewed.py"])["status"], "BLOCKED")
        self.assertEqual(
            owners_for("app/modules/encyclopedia/services/achievement_unreviewed.py"),
            frozenset(),
        )

    def test_unknown_owner_blocks_instead_of_launching_full(self):
        plan = self.route(["app/new_cross_domain_provider.py"])
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertEqual(plan["unknown_paths"], ["app/new_cross_domain_provider.py"])
        self.assertNotIn("FULL_SUITE", plan["domains"])

    def test_craft_seed_builder_has_exact_shared_owners(self):
        self.assertEqual(
            owners_for("scripts/windows/craft_seed.py"),
            frozenset({"ci", "craft", "data", "startup"}),
        )
        self.assertEqual(owners_for("scripts/windows/new_seed_helper.py"), frozenset())

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
