from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EQUIPMENT = ROOT / "app" / "pages" / "equipment_page.py"
ENCYCLOPEDIA_FACADE = ROOT / "app" / "modules" / "encyclopedia" / "views" / "__init__.py"
MEMORY_PAGE = (
    ROOT
    / "app"
    / "modules"
    / "encyclopedia"
    / "views"
    / "memory_bound_encyclopedia_page.py"
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
