from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_MAIN = ROOT / "main.py"
EQUIPMENT = ROOT / "app" / "pages" / "equipment_page.py"
ENCYCLOPEDIA_FACADE = ROOT / "app" / "modules" / "encyclopedia" / "views" / "__init__.py"
ENCYCLOPEDIA_SERVICE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "services"
    / "encyclopedia_service.py"
)
PROVIDER_FACADE = ROOT / "app" / "modules" / "encyclopedia" / "providers" / "__init__.py"
DOFUS_ITEM_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "dofus_item_provider.py"
)
MEMORY_PAGE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "views"
    / "memory_bound_encyclopedia_page.py"
)
MEMORY_GUIDE_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "memory_bound_guide_provider.py"
)
MEMORY_ACHIEVEMENT_PROVIDER = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "providers"
    / "memory_bound_achievement_provider.py"
)
RELATED_DATA = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "services"
    / "related_data_service.py"
)


def test_equipment_runtime_does_not_embed_qt_webengine() -> None:
    source = EQUIPMENT.read_text(encoding="utf-8")
    assert "QtWebEngine" not in source
    assert "QWebEngine" not in source
    assert "QDesktopServices.openUrl" in source
    assert "HUZOUNET_URL" in source


def test_encyclopedia_public_facade_routes_to_memory_bound_page() -> None:
    source = ENCYCLOPEDIA_FACADE.read_text(encoding="utf-8")
    assert "memory_bound_encyclopedia_page" in source
    assert "MemoryBoundEncyclopediaPage as RealEncyclopediaPage" in source


def test_encyclopedia_runtime_constructs_provider_through_memory_facade() -> None:
    source = ENCYCLOPEDIA_SERVICE.read_text(encoding="utf-8")
    assert "from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider" in source
    assert "providers.achievement_provider import AchievementProvider" not in source


def test_memory_bound_page_hibernates_widgets_and_reconstructible_runtime() -> None:
    source = MEMORY_PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        "hibernate_heavy_views",
        "_hibernate_achievements",
        "_hibernate_guides",
        "_release_runtime_providers",
        "prepare_external_tab_navigation",
        "_collect_achievement_runtime",
        "collect_related_preload",
        "ensure_achievements_view",
        "ensure_guides_view",
        "hideEvent",
        "showEvent",
        "on_tab_changed",
    } <= method_names
    assert "release_catalogue" in source
    assert "RelatedPreloadGate()" in source
    assert "_achievement_ready = False" in source
    assert "_guide_runtime_ready = False" in source
    assert "pending_encyclopedia_tab" in source
    assert "_memory_release_runtime_when_idle = False" in source
    assert "deleteLater()" in source


def test_achievement_provider_releases_reconstructible_source_maps() -> None:
    facade = PROVIDER_FACADE.read_text(encoding="utf-8")
    source = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "memory_bound_achievement_provider" in facade
    assert "MemoryBoundAchievementProvider as RealAchievementProvider" in facade
    assert {
        "_reset_sources",
        "release_catalogue",
        "_trim_catalogue_payload",
        "_load",
        "prepare_detail_sources",
        "get_detail_by_id",
    } <= method_names
    assert "QuestSources(" in source
    assert "self._entries = None" in source
    assert "self._image_indexes.clear()" in source
    assert "_compact_achievement_dict" in source
    assert "_compact_objective_dict" in source
    assert "_DUMP_DETAIL_FLAG" in source
    assert "_dump_default_detail" in source
    assert '"raw"' in source


def test_related_index_warmup_runs_outside_long_lived_atlas_process() -> None:
    source = RELATED_DATA.read_text(encoding="utf-8")
    assert "subprocess.run" in source
    assert "achievement_index_warmup" in source
    assert "sys.executable" in source
    assert "QuestSources(" not in source


def test_dofus_item_extraction_does_not_parse_monolithic_sources_in_parent() -> None:
    source = DOFUS_ITEM_PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert {"_load", "_load_in_process", "_dump_compact_default_items"} <= method_names
    assert "subprocess.run" in source
    assert "--dump-compact" in source
    assert "sys.executable" in source


def test_guide_provider_releases_reconstructible_catalogue() -> None:
    source = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert {"release_catalogue", "release_detail_cache", "_load"} <= method_names
    assert "self._loaded = False" in source
    assert "self._detail_entries = {}" in source


def test_shell_announces_explicit_encyclopedia_tab_before_showing_page() -> None:
    source = SHELL_MAIN.read_text(encoding="utf-8")
    method = source[source.index("def open_encyclopedia_tab"):source.index("def finish_pending_encyclopedia_tab")]
    prepare = method.index("prepare_external_tab_navigation")
    show = method.index('self.show_page("Quetes")')
    assert prepare < show
    assert "prepare_navigation(label)" in method


def test_memory_page_prefers_explicit_tab_over_hidden_current_tab() -> None:
    source = MEMORY_PAGE.read_text(encoding="utf-8")
    assert 'label = self._memory_pending_tab_label or self.tabs.tabText(index)' in source
    assert 'if label and label == self._memory_pending_tab_label:' in source


def test_success_catalogue_keeps_rich_objectives_out_of_resident_rows() -> None:
    source = MEMORY_ACHIEVEMENT_PROVIDER.read_text(encoding="utf-8")
    assert '"objectives": []' in source
    assert '"progress_objectives": [' in source
    assert "def progress_objectives_for" in source
    assert "_DUMP_DETAIL_FLAG" in source


def test_guide_compact_worker_never_loads_dofus_item_corpus() -> None:
    source = MEMORY_GUIDE_PROVIDER.read_text(encoding="utf-8")
    assert "class _CompactGuideNoopItemProvider" in source
    assert "dofus_item_provider=_CompactGuideNoopItemProvider()" in source
    dump = source[source.index("def _dump_compact_default_guides"):]
    assert "DofusItemProvider(" not in dump


def test_dofus_item_worker_streams_monolithic_doduda_sources() -> None:
    source = DOFUS_ITEM_PROVIDER.read_text(encoding="utf-8")
    assert "def _iter_doduda_refs" in source
    assert '_iter_doduda_refs(items_path)' in source
    assert 'self._read_json(self.data_dir / "items.json"' not in source
    assert 'doduda_rows(self.data_dir / "item_types.json")' not in source
    assert 'doduda_rows(self.data_dir / "effects.json")' not in source
