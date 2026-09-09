from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from tests.source_guardrails import read_source


ROOT = Path(__file__).resolve().parents[1]


class ProjectGuardrailsTests(unittest.TestCase):
    def _text(self, relative: str) -> str:
        return read_source(ROOT / relative)

    @staticmethod
    def _call_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = ProjectGuardrailsTests._call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    def test_agents_requires_project_guardrails(self) -> None:
        agents = self._text("AGENTS.md")
        self.assertIn("DEVELOPMENT_GUARDRAILS.md", agents)
        self.assertTrue((ROOT / "DEVELOPMENT_GUARDRAILS.md").exists())

    def test_guide_ultime_manual_progress_uses_stable_stage_identity(self) -> None:
        runtime = self._text("app/modules/encyclopedia/services/guide_ultime_runtime_service.py")
        self.assertIn("manual_stage_id", runtime)
        self.assertIn("return f\"manual:", runtime)
        self.assertIn("_legacy_manual_page_key", runtime)

    def test_manual_runtime_preserves_structured_domain_data(self) -> None:
        runtime = self._text("app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py")
        self.assertIn('"manual_stage_data": copy.deepcopy(stage)', runtime)
        self.assertIn('"manual_chapter_preparation": copy.deepcopy', runtime)
        self.assertIn("_structured_rows_from_fields", runtime)
        self.assertIn("_link_next_cards(cards)", runtime)
        self.assertIn('"manual_stage_id": str(nxt.get("manual_stage_id")', runtime)

    def test_home_uses_manual_guide_runtime_for_primary_progress(self) -> None:
        home = self._text("app/pages/home_page.py")
        self.assertIn("GuideUltimeManualRuntimeService", home)
        self.assertIn("route_sheet_progress", home)
        manual_branch = (
            "if service is not None and service.available:\n"
            "            self._refresh_manual_guide_progress(service)\n"
            "            return"
        )
        fallback = "self.current_guide_id = guide.id\n        self.progress_bar.setValue(percent)"
        self.assertIn(manual_branch, home)
        self.assertIn(fallback, home)
        self.assertLess(
            home.index(manual_branch),
            home.index(fallback),
            "Le runtime manuel doit ??tre prioritaire; le guide legacy ne reste qu'un fallback d'urgence.",
        )

    def test_guide_catalog_uses_manual_sheet_progress(self) -> None:
        guides = self._text("app/modules/encyclopedia/views/guides_view.py")
        self.assertIn("route_sheet_progress", guides)
        self.assertNotIn("import *", guides)
        self.assertNotIn(
            "self.provider.get_by_id(GUIDE_ULTIME_LEGACY_ID)",
            guides,
            "guide_complet ne doit rester qu'un alias de navigation.",
        )

    def test_guide_ultime_styles_live_outside_views(self) -> None:
        manual_view = self._text("app/modules/encyclopedia/views/guide_ultime_manual_view.py")
        universal_view = self._text("app/modules/encyclopedia/views/guide_ultime_universal_view.py")
        generated_view = self._text("app/modules/encyclopedia/views/guide_ultime_generated_view.py")
        self.assertIn("guide_manual_stylesheet", manual_view)
        self.assertIn("guide_universal_stylesheet", universal_view)
        self.assertIn("guide_v5_stylesheet", generated_view)
        self.assertNotIn("background: #", manual_view)
        self.assertNotIn('NPC_COLOR = "#', manual_view)
        self.assertNotIn('RESOURCE_COLOR = "#', manual_view)
        self.assertNotIn("PALETTE", universal_view)
        self.assertNotIn("PALETTE", generated_view)
        self.assertNotIn("setStyleSheet(\n            f\"\"\"", universal_view)
        self.assertNotIn("setStyleSheet(\n            f\"\"\"", generated_view)

    def test_quests_hierarchy_style_is_centralized(self) -> None:
        quests = self._text("app/pages/_quests_page_impl.py")
        style = self._text("app/ui/styles/quests.py")
        self.assertIn("quest_hierarchy_stylesheet", quests)
        self.assertNotIn("QTreeWidget#QuestHierarchyTree {\n                    background: #", quests)
        self.assertIn("@PANEL_HOVER", style)
        self.assertIn("@PANEL_ACTIVE", style)

    def test_shared_quest_item_row_is_not_imported_from_legacy_guide(self) -> None:
        quests = self._text("app/pages/_quests_page_impl.py")
        detail = self._text("app/modules/encyclopedia/widgets/quest_detail_view.py")
        guides = self._text("app/modules/encyclopedia/views/guides_view.py")
        for source in (quests, detail, guides):
            self.assertIn("widgets.quest_item_row import item_row", source)
        self.assertNotIn("views.guides_view_legacy import item_row", quests)
        self.assertNotIn("_guide_ui().item_row(", detail)
        self.assertNotIn("    item_row,\n", guides)

    def test_quest_catalog_cache_never_uses_pickle(self) -> None:
        catalog = self._text("app/quest_catalog.py")
        self.assertNotIn("import pickle", catalog)
        self.assertNotIn("pickle.loads", catalog)
        self.assertNotIn("pickle.dumps", catalog)
        self.assertIn("quest_catalog_v2.json.gz", catalog)

    def test_core_settings_do_not_import_ui_storage(self) -> None:
        settings = self._text("app/core/settings.py")
        self.assertNotIn("from app.storage import", settings)
        self.assertIn("from app.core.profile_settings import", settings)

    def test_app_does_not_bypass_serialized_achievement_progress(self) -> None:
        forbidden = "services.progress_service import AchievementProgressService"
        allowed_implementation_files = {
            "app/modules/encyclopedia/services/progress_service.py",
            "app/modules/encyclopedia/services/serialized_achievement_progress_service.py",
        }
        violations: list[str] = []
        app_root = ROOT / "app"
        for path in app_root.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in allowed_implementation_files:
                continue
            if forbidden in read_source(path):
                violations.append(relative)
        self.assertEqual([], violations, f"Imports legacy AchievementProgressService: {violations}")

        guide_v5 = self._text("app/modules/encyclopedia/services/guide_ultime_generated_service.py")
        self.assertIn("serialized_achievement_progress_service", guide_v5)
        self.assertNotIn("achievement_progress._load()", guide_v5)
        self.assertNotIn("guide_progress._load()", guide_v5)

    def test_progress_services_share_freshness_coordinator(self) -> None:
        coordinator = self._text("app/core/progress_coordinator.py")
        self.assertIn("ProgressFileCoordinator", coordinator)
        self.assertIn("mark_changed", coordinator)
        compatibility = self._text("app/modules/encyclopedia/services/progress_coordinator.py")
        self.assertIn("from app.core.progress_coordinator import", compatibility)
        for relative in (
            "app/modules/encyclopedia/services/quest_progress_service.py",
            "app/modules/encyclopedia/services/guide_progress_service.py",
            "app/modules/encyclopedia/services/serialized_achievement_progress_service.py",
        ):
            source = self._text(relative)
            self.assertIn("coordinator_for", source, relative)
            self.assertIn("_ensure_fresh", source, relative)
            self.assertIn("mark_changed", source, relative)

    def test_ui_does_not_use_legacy_quest_progress_helpers(self) -> None:
        forbidden = ("quest_done", "quest_item_done", "set_quest_done", "set_quest_item_done")
        roots = (
            ROOT / "app/pages",
            ROOT / "app/modules/encyclopedia/views",
            ROOT / "app/modules/encyclopedia/widgets",
        )
        violations: list[str] = []
        for root in roots:
            for path in root.rglob("*.py"):
                text = read_source(path)
                for name in forbidden:
                    if re.search(rf"\b{re.escape(name)}\b", text):
                        violations.append(f"{path.relative_to(ROOT).as_posix()}:{name}")
        self.assertEqual([], sorted(violations), f"Helpers quest progress legacy interdits dans l'UI: {violations}")

    def test_hook_lifecycle_is_safe_in_base_implementations(self) -> None:
        keyboard = self._text("app/input/hotkeys.py")
        mouse = self._text("app/input/mouse_hooks.py")
        lifecycle = self._text("app/input/hook_lifecycle.py")
        managed = self._text("app/input/managed_hooks.py")
        runtime = self._text("app/core/runtime_state.py")

        self.assertIn("stop_message_hook(self)", keyboard)
        self.assertIn("stop_message_hook(self)", mouse)
        self.assertIn("PostThreadMessageW", lifecycle)
        self.assertIn("WM_QUIT", lifecycle)
        self.assertIn("thread.join", lifecycle)
        self.assertNotIn("raccourci vide: Stop urgence", keyboard)
        self.assertNotIn("_ManagedMessageHookMixin", managed)
        self.assertIn("self._running and self._admin_ok", runtime)
        self.assertNotIn("active_callback(report.ok", runtime)

    def test_legacy_callback_compatibility_is_checked_before_invocation(self) -> None:
        storage = self._text("app/storage.py")
        organizer = self._text("app/pages/organizer_page.py")
        self.assertIn("def invoke_compatible_callback", storage)
        self.assertIn("signature.bind(*args)", storage)
        self.assertIn("invoke_compatible_callback(self.reload_runtime_callback, True)", organizer)
        self.assertNotIn("except TypeError:\n            self.reload_runtime_callback()", organizer)

    def test_type_error_handlers_do_not_retry_callbacks(self) -> None:
        """A callback TypeError must propagate; it must never trigger a second call."""

        violations: list[str] = []
        for path in (ROOT / "app").rglob("*.py"):
            source = read_source(path)
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                try_calls = {
                    name
                    for statement in node.body
                    for child in ast.walk(statement)
                    if isinstance(child, ast.Call)
                    if (name := self._call_name(child.func))
                    and ("callback" in name.casefold() or name.casefold().endswith(("_cb", ".cb")))
                }
                if not try_calls:
                    continue
                for handler in node.handlers:
                    handler_type = handler.type
                    catches_type_error = (
                        isinstance(handler_type, ast.Name)
                        and handler_type.id == "TypeError"
                    ) or (
                        isinstance(handler_type, ast.Tuple)
                        and any(isinstance(item, ast.Name) and item.id == "TypeError" for item in handler_type.elts)
                    )
                    if not catches_type_error:
                        continue
                    retry_calls = {
                        name
                        for statement in handler.body
                        for child in ast.walk(statement)
                        if isinstance(child, ast.Call)
                        if (name := self._call_name(child.func))
                    }
                    for name in sorted(try_calls & retry_calls):
                        violations.append(
                            f"{path.relative_to(ROOT).as_posix()}:{getattr(node, 'lineno', '?')}:{name}"
                        )
        self.assertEqual([], violations, f"Callbacks rejoués après TypeError: {violations}")

    def test_equipment_webview_restricts_main_frame_navigation(self) -> None:
        equipment = self._text("app/pages/equipment_page.py")
        self.assertIn("acceptNavigationRequest", equipment)
        self.assertIn("self.allowed_host", equipment)
        self.assertIn("NavigationTypeLinkClicked", equipment)
        self.assertIn("QDesktopServices.openUrl", equipment)
        self.assertIn("self.web.setPage(page_class(self.web))", equipment)

    def test_cartography_recovery_never_uses_command_shell(self) -> None:
        recovery = self._text("app/services/maps/cartography_asset_recovery.py")
        self.assertNotIn("shell=True", recovery)
        self.assertIn("shell=False", recovery)
        sources = self._text("data/cartography/sources.json")
        self.assertNotIn('"command": "doduda && doduda map"', sources)
        self.assertIn('"command_args"', sources)

    def test_normal_launcher_is_offline_and_installer_is_explicit(self) -> None:
        launcher = self._text("Dofus_Atlas.bat").casefold()
        installer = self._text("Install_Dofus_Atlas.bat").casefold()
        bootstrap = self._text("bootstrap_dofus_atlas.ps1")

        self.assertNotIn("pip install", launcher)
        self.assertNotIn("ensurepip", launcher)
        self.assertNotIn("bootstrap_dofus_atlas.ps1", launcher)
        self.assertNotIn(":run_bootstrap", launcher)
        self.assertIn("install_dofus_atlas.bat", launcher)

        self.assertIn("bootstrap_dofus_atlas.ps1", installer)
        self.assertIn("-nolaunch", installer)
        self.assertIn("Get-FileHash", bootstrap)
        self.assertIn("SHA256", bootstrap)
        self.assertIn("$PythonInstallerSha256", bootstrap)

    def test_sqlite_backup_uses_sqlite_backup_api(self) -> None:
        store = self._text("local_dofus_data/data_store.py")
        self.assertIn("source.backup(target)", store)
        self.assertNotIn("shutil.copy2(self.db_path, destination)", store)

    def test_sqlite_schema_versions_require_registered_migrations(self) -> None:
        store = self._text("local_dofus_data/data_store.py")
        migrations = self._text("local_dofus_data/migrations.py")
        self.assertIn("_apply_schema_migrations", store)
        self.assertIn("migration_for(target_version)", store)
        self.assertIn("Migration SQLite manquante", store)
        self.assertIn("MIGRATIONS", migrations)
        self.assertIn("PRAGMA busy_timeout", store)
        self.assertIn("PRAGMA synchronous = NORMAL", store)

    def test_gitignore_contains_real_patterns_not_tracking_literals(self) -> None:
        gitignore = self._text(".gitignore")
        self.assertNotIn('Tracking "', gitignore)
        self.assertIn("logs/*.log", gitignore)
        self.assertIn("__pycache__/", gitignore)

    def test_no_wildcard_imports_in_application_code(self) -> None:
        candidates = [ROOT / "main.py", *(ROOT / "app").rglob("*.py")]
        existing_baseline = {
            "app/pages/quests_page.py:from app.pages._quests_page_impl import *",
        }
        found: set[str] = set()
        diagnostics: list[str] = []
        for path in candidates:
            if not path.exists():
                continue
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(read_source(path), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                    symbol = f"from {node.module} import *"
                    found.add(f"{relative}:{symbol}")
                    diagnostics.append(f"{relative} ligne {node.lineno}: {symbol}")
        self.assertEqual(
            existing_baseline,
            found,
            "Nouvel import wildcard interdit; chaque diagnostic indique fichier, ligne et module. "
            f"Baseline attendue={sorted(existing_baseline)}, trouve={sorted(found)}; "
            f"diagnostics={diagnostics}",
        )

    def test_app_modules_do_not_mutate_sys_path(self) -> None:
        violations: list[str] = []
        for path in (ROOT / "app").rglob("*.py"):
            text = read_source(path)
            if "sys.path.insert" in text or "sys.path.append" in text:
                violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], sorted(violations), f"Mutations sys.path interdites dans app/: {violations}")

    def test_global_ci_exists_alongside_guide_ci(self) -> None:
        self.assertTrue((ROOT / ".github/workflows/app-ci.yml").exists())
        self.assertTrue((ROOT / ".github/workflows/guide-ultime-v5-ui.yml").exists())


if __name__ == "__main__":
    unittest.main()
