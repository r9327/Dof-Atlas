from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "app/modules/encyclopedia/views/encyclopedia_page.py"
DEFERRED_GUIDE_PATH = ROOT / "app/modules/encyclopedia/views/deferred_achievement_guides_view.py"
PUBLIC_VIEWS_PATH = ROOT / "app/modules/encyclopedia/views/__init__.py"
PLACEHOLDER_PATH = ROOT / "app/modules/encyclopedia/views/placeholder_view.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class EncyclopediaGuideSuccessDelegacyTests(unittest.TestCase):
    def test_obsolete_placeholder_architecture_is_gone(self) -> None:
        page = _source(PAGE_PATH)
        public_views = _source(PUBLIC_VIEWS_PATH)

        self.assertFalse(PLACEHOLDER_PATH.exists())
        self.assertNotIn("EncyclopediaPlaceholderView", page)
        self.assertNotIn("EncyclopediaPlaceholderView", public_views)
        self.assertNotIn("_lazy_placeholders", page)
        self.assertIn('setObjectName("EncyclopediaDeferredSlot")', page)

    def test_encyclopedia_has_one_modern_guide_runtime_path(self) -> None:
        page = _source(PAGE_PATH)

        self.assertIn("DeferredAchievementGuidesView(", page)
        for obsolete in (
            "_ensure_guides_view_base",
            "_ensure_guides_view_progressive",
            "_promote_guides_runtime_context",
            "_on_tab_changed_progressive",
        ):
            self.assertNotIn(obsolete, page)

    def test_guide_success_card_is_bound_by_business_id_not_historical_text(self) -> None:
        source = _source(DEFERRED_GUIDE_PATH)

        self.assertIn('GUIDE_SUCCESS_TITLE = "Guide Succès"', source)
        self.assertIn("== GUIDE_ULTIME_LEGACY_ID", source)
        self.assertIn("title.setText(GUIDE_SUCCESS_TITLE)", source)
        lowered = source.casefold()
        self.assertNotIn("aventure de zéro", lowered)
        self.assertNotIn("aventure de zero", lowered)

    def test_guide_success_home_progress_comes_from_canonical_route_in_worker(self) -> None:
        source = _source(PAGE_PATH)

        self.assertIn('GUIDE_SUCCESS_CATALOG_ID = "guide_complet"', source)
        self.assertIn("guide_success_service.route_sheet_progress(", source)
        self.assertIn("progress[GUIDE_SUCCESS_CATALOG_ID]", source)

        tree = ast.parse(source)
        top_level_imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module
                == "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service"
                for node in top_level_imports
            )
        )

        helper = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_build_guide_success_runtime"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module
                == "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service"
                for node in ast.walk(helper)
            )
        )


if __name__ == "__main__":
    unittest.main()
