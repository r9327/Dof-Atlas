from __future__ import annotations

import unittest
from pathlib import Path

from app.ui.styles import (
    guide_manual_stylesheet,
    guide_universal_stylesheet,
    guide_v5_stylesheet,
)
from app.ui.styles.guide import (
    guide_manual_stylesheet as canonical_manual_stylesheet,
    guide_universal_stylesheet as canonical_universal_stylesheet,
    guide_v5_stylesheet as canonical_v5_stylesheet,
)
from app.ui.styles.guide_manual import guide_manual_stylesheet as legacy_manual_stylesheet
from app.ui.styles.guide_universal import (
    guide_universal_stylesheet as legacy_universal_stylesheet,
)
from app.ui.styles.guide_v5 import guide_v5_stylesheet as legacy_v5_stylesheet


class GuideStyleSingleSourceTests(unittest.TestCase):
    def test_public_and_legacy_imports_share_one_canonical_implementation(self) -> None:
        self.assertIs(guide_manual_stylesheet, canonical_manual_stylesheet)
        self.assertIs(guide_universal_stylesheet, canonical_universal_stylesheet)
        self.assertIs(guide_v5_stylesheet, canonical_v5_stylesheet)
        self.assertIs(legacy_manual_stylesheet, canonical_manual_stylesheet)
        self.assertIs(legacy_universal_stylesheet, canonical_universal_stylesheet)
        self.assertIs(legacy_v5_stylesheet, canonical_v5_stylesheet)

    def test_guide_styles_render_global_theme_tokens(self) -> None:
        for renderer in (
            guide_manual_stylesheet,
            guide_universal_stylesheet,
            guide_v5_stylesheet,
        ):
            with self.subTest(renderer=renderer.__name__):
                stylesheet = renderer()
                self.assertTrue(stylesheet.strip())
                self.assertNotIn("@PANEL", stylesheet)
                self.assertNotIn("@TEXT", stylesheet)
                self.assertNotIn("@GREEN", stylesheet)

    def test_phase2_views_do_not_install_page_level_stylesheets(self) -> None:
        guarded_views = (
            "app/modules/encyclopedia/views/achievements_view.py",
            "app/modules/encyclopedia/views/guides_view.py",
            "app/modules/encyclopedia/views/guide_ultime_generated_view.py",
            "app/modules/encyclopedia/views/guide_ultime_manual_view.py",
            "app/modules/encyclopedia/views/guide_ultime_universal_view.py",
            "app/modules/encyclopedia/widgets/quest_item_row.py",
            "app/pages/_quests_page_impl.py",
        )
        for path in guarded_views:
            with self.subTest(path=path):
                source = Path(path).read_text(encoding="utf-8")
                self.assertNotIn("setStyleSheet(", source)
                self.assertNotIn("apply_local_style", source)

        self.assertFalse(Path("app/ui/styles/quests.py").exists())

    def test_global_theme_owns_phase2_view_selectors(self) -> None:
        source = Path("app/ui/theme.py").read_text(encoding="utf-8")
        for selector in (
            "QWidget#AchievementsView QLineEdit#EncyclopediaSearch",
            "QTreeWidget#QuestHierarchyTree",
            'QFrame#GuideQuestLine[state="done"]',
            "#GuideManualProgress",
            "#GuideUltimeProgressHeader",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, source)


if __name__ == "__main__":
    unittest.main()
