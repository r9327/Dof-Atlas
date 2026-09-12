from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8-sig")


def _method_node(relative_path: str, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(_source(relative_path), filename=relative_path)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == method_name:
                return child
    raise AssertionError(f"{class_name}.{method_name} introuvable dans {relative_path}")


def _called_attributes(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute):
            calls.add(func.attr)
        elif isinstance(func, ast.Name):
            calls.add(func.id)
    return calls


class PerformanceGuardrailTests(unittest.TestCase):
    def test_large_quest_catalog_keeps_leaf_widgets_lazy(self) -> None:
        source = _source("app/pages/quests_page.py")
        self.assertIn("_MIN_LAZY_QUESTS = 500", source)
        self.assertIn('placeholder.setData(0, HIERARCHY_KIND_ROLE, "lazy")', source)
        self.assertIn("def _populate_hierarchy_series", source)
        self.assertIn("tree.itemExpanded.connect", source)

    def test_quests_page_does_not_render_last_detail_during_construction(self) -> None:
        restore = _method_node("app/pages/quests_page.py", "QuestsPage", "restore_last_quest")
        calls = _called_attributes(restore)
        self.assertNotIn("select_quest", calls)
        self.assertNotIn("show_quest_detail", calls)
        self.assertNotIn("sync_hierarchy_selection", calls)

        assignments_selected_none = False
        for node in ast.walk(restore):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr == "selected_quest_id"
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is None
                ):
                    assignments_selected_none = True
        self.assertTrue(assignments_selected_none)

    def test_empty_quest_detail_keeps_guide_ui_lazy(self) -> None:
        relative_path = "app/modules/encyclopedia/widgets/quest_detail_view.py"
        constructor = _method_node(relative_path, "QuestDetailView", "__init__")
        clear = _method_node(relative_path, "QuestDetailView", "clear")
        show_quest = _method_node(relative_path, "QuestDetailView", "show_quest")
        render_header = _method_node(relative_path, "QuestDetailView", "_render_header")

        self.assertNotIn("_guide_ui", _called_attributes(constructor))
        self.assertNotIn("_guide_ui", _called_attributes(clear))
        self.assertIn("_render_header", _called_attributes(show_quest))
        self.assertIn("_guide_ui", _called_attributes(render_header))
        source = _source(relative_path)
        self.assertNotIn("_guide_ui_initialized", source)
        self.assertNotIn("apply_local_style", source)

    def test_large_quest_search_is_debounced_and_cached(self) -> None:
        source = _source("app/pages/quests_page.py")
        self.assertIn("_LARGE_CATALOG_SEARCH_DEBOUNCE_MS", source)
        self.assertIn("_search_debounce_timer", source)
        self.assertIn("_quest_search_text_cache", source)
        self.assertIn("def quest_search_text", source)
        self.assertIn("def _on_search_text_changed", source)

    def test_hidden_quest_compatibility_html_is_on_demand(self) -> None:
        source = _source("app/pages/quests_page.py")
        self.assertIn("class _LazyCompatQuestDetailPanel", source)
        self.assertIn("def set_lazy_payload", source)
        self.assertIn("def toHtml", source)
        show_detail = _method_node("app/pages/quests_page.py", "QuestsPage", "show_quest_detail")
        calls = _called_attributes(show_detail)
        self.assertIn("set_lazy_payload", calls)
        self.assertNotIn("quest_detail_html", calls)

    def test_owned_item_file_is_not_reparsed_on_every_quest_click(self) -> None:
        refresh = _method_node("app/pages/quests_page.py", "QuestsPage", "refresh_owned_items")
        calls = _called_attributes(refresh)
        self.assertIn("stat", calls)
        self.assertIn("load_owned_items", calls)
        source = _source("app/pages/quests_page.py")
        self.assertIn("_owned_items_file_signature", source)
        self.assertIn("stat.st_mtime_ns", source)
        self.assertIn("stat.st_size", source)

    def test_page_package_does_not_eager_import_unrelated_pages(self) -> None:
        relative_path = "app/pages/__init__.py"
        tree = ast.parse(_source(relative_path), filename=relative_path)
        eager_page_imports: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("app.pages."):
                eager_page_imports.append(str(node.module))
            elif isinstance(node, ast.Import):
                eager_page_imports.extend(
                    alias.name
                    for alias in node.names
                    if alias.name.startswith("app.pages.")
                )
        self.assertEqual(eager_page_imports, [])
        source = _source(relative_path)
        self.assertIn("_PAGE_EXPORTS", source)
        self.assertIn("import_module(module_name)", source)

    def test_heavy_pages_remain_lazy_at_application_startup(self) -> None:
        source = _source("main.py")
        self.assertIn('self.register_page("Quetes", self.loading_page("Encyclopédie"))', source)
        self.assertIn('self.register_page("Equipement", self.loading_page("Équipement"))', source)
        self.assertIn('self.page_factories["Quetes"] = self.create_encyclopedia_page', source)
        self.assertIn('self.page_factories["Equipement"] = self.create_equipment_page', source)
        self.assertIn(
            "self._schedule_owned_callback(STARTUP_PRELOAD_DELAY_MS, self.start_preload)",
            source,
        )

    def test_qtwebengine_stays_out_of_equipment_module_level_imports(self) -> None:
        source = _source("app/pages/equipment_page.py")
        tree = ast.parse(source, filename="app/pages/equipment_page.py")
        module_level_webengine_imports: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("PySide6.QtWebEngine"):
                module_level_webengine_imports.append(str(node.module))
            elif isinstance(node, ast.Import):
                module_level_webengine_imports.extend(
                    alias.name
                    for alias in node.names
                    if alias.name.startswith("PySide6.QtWebEngine")
                )
        self.assertEqual(module_level_webengine_imports, [])
        self.assertIn("def qwebengine_view_class", source)
        self.assertIn("def schedule_web_start", source)

    def test_guide_home_images_keep_background_file_io_and_ui_thread_decode(self) -> None:
        source = _source("app/modules/encyclopedia/views/guides_view.py")
        self.assertIn("_atlas_async_image_loader = True", source)
        self.assertIn("SOLUTION_IMAGE_EXECUTOR.submit", source)
        self.assertIn("Path(path).read_bytes()", source)
        self.assertIn("QImage.fromData(payload)", source)
        self.assertNotIn("QImage(path)", source)

    def test_perf_baseline_keeps_startup_quests_ram_and_idle_cpu_metrics(self) -> None:
        source = _source("app/modules/encyclopedia/tools/benchmark_guides_performance.py")
        for metric in (
            "startup_stabilized_ms",
            "startup_stabilized_rss_mb",
            "quests_open_ms",
            "rss_after_quests_mb",
            "idle_cpu_percent_one_core",
        ):
            self.assertIn(metric, source)
        self.assertIn('"startup_preload_state": "DEFERRED_ON_DEMAND"', source)
        self.assertNotIn('30.0,\n        "startup preload"', source)

    def test_qimage_decode_emits_non_blocking_debug_measurement(self) -> None:
        source = _source("app/modules/encyclopedia/views/guides_view.py")
        self.assertIn("def _decode_qimage", source)
        self.assertIn("QImage decode kind=%s bytes=%d width=%d height=%d ui_ms=%.3f", source)

    def test_deterministic_resource_budget_failure_is_fatal_to_ci(self) -> None:
        source = _source(".github/workflows/app-ci.yml")
        marker = "- name: Enforce deterministic resource budgets"
        block = source[source.index(marker) :].split("\n      - name:", 1)[0]
        self.assertIn("tests.test_performance_budgets", block)
        self.assertIn("exit $LASTEXITCODE", block)
        self.assertNotIn("continue-on-error", block)


if __name__ == "__main__":
    unittest.main()
