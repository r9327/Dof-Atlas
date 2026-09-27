from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "app/modules/encyclopedia/views/encyclopedia_page.py"
DEFERRED_GUIDE_PATH = ROOT / "app/modules/encyclopedia/views/deferred_achievement_guides_view.py"
PUBLIC_VIEWS_PATH = ROOT / "app/modules/encyclopedia/views/__init__.py"
PLACEHOLDER_PATH = ROOT / "app/modules/encyclopedia/views/placeholder_view.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_obsolete_placeholder_architecture_is_gone() -> None:
    page = _source(PAGE_PATH)
    public_views = _source(PUBLIC_VIEWS_PATH)

    assert not PLACEHOLDER_PATH.exists()
    assert "EncyclopediaPlaceholderView" not in page
    assert "EncyclopediaPlaceholderView" not in public_views
    assert "_lazy_placeholders" not in page
    assert 'setObjectName("EncyclopediaDeferredSlot")' in page


def test_encyclopedia_has_one_modern_guide_runtime_path() -> None:
    page = _source(PAGE_PATH)

    assert "DeferredAchievementGuidesView(" in page
    for obsolete in (
        "_ensure_guides_view_base",
        "_ensure_guides_view_progressive",
        "_promote_guides_runtime_context",
        "_on_tab_changed_progressive",
    ):
        assert obsolete not in page


def test_guide_success_card_is_bound_by_business_id_not_historical_text() -> None:
    source = _source(DEFERRED_GUIDE_PATH)

    assert 'GUIDE_SUCCESS_TITLE = "Guide Succès"' in source
    assert "== GUIDE_ULTIME_LEGACY_ID" in source
    assert "title.setText(GUIDE_SUCCESS_TITLE)" in source
    lowered = source.casefold()
    assert "aventure de zéro" not in lowered
    assert "aventure de zero" not in lowered


def test_guide_success_home_progress_comes_from_canonical_route_in_worker() -> None:
    source = _source(PAGE_PATH)

    assert 'GUIDE_SUCCESS_CATALOG_ID = "guide_complet"' in source
    assert "guide_success_service.route_sheet_progress(" in source
    assert "progress[GUIDE_SUCCESS_CATALOG_ID]" in source

    tree = ast.parse(source)
    top_level_imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service"
        for node in top_level_imports
    )

    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_guide_success_runtime"
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service"
        for node in ast.walk(helper)
    )
