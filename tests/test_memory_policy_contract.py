from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


def test_memory_bound_page_hibernates_only_widget_layer() -> None:
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
        "ensure_achievements_view",
        "ensure_guides_view",
        "hideEvent",
        "on_tab_changed",
    } <= method_names
    assert "service.achievement_provider" not in source
    assert "service.guide_provider = None" not in source
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
        "_trim_catalogue_payload",
        "_load",
        "prepare_detail_sources",
        "get_detail_by_id",
    } <= method_names
    assert "QuestSources(" in source
    assert "self._entries = None" in source
    assert "self._image_indexes.clear()" in source
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
