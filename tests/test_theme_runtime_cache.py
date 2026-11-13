from __future__ import annotations

import unittest
from unittest.mock import patch

import app.ui.theme as theme


class ThemeRuntimeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        theme.clear_theme_cache()

    def tearDown(self) -> None:
        theme.clear_theme_cache()

    def test_renderer_is_canonical_in_theme_module(self) -> None:
        self.assertEqual(theme.render_theme_template.__module__, "app.ui.theme")

    def test_static_template_is_rendered_only_once(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_renderer(template: str, overrides=None) -> str:
            calls.append((template, overrides))
            return f"rendered:{template}"

        with patch.object(theme, "_render_theme_template", side_effect=fake_renderer):
            first = theme.render_theme_template("color:@TEXT;")
            second = theme.render_theme_template("color:@TEXT;")

        self.assertEqual(first, "rendered:color:@TEXT;")
        self.assertEqual(second, first)
        self.assertEqual(calls, [("color:@TEXT;", None)])

    def test_dynamic_overrides_bypass_static_cache(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_renderer(template: str, overrides=None) -> str:
            calls.append((template, overrides))
            return "dynamic"

        overrides = {"TEXT": "#ffffff"}

        with patch.object(theme, "_render_theme_template", side_effect=fake_renderer):
            self.assertEqual(theme.render_theme_template("color:@TEXT;", overrides), "dynamic")
            self.assertEqual(theme.render_theme_template("color:@TEXT;", overrides), "dynamic")
        self.assertEqual(len(calls), 2)
        self.assertIs(calls[0][1], overrides)
        self.assertIs(calls[1][1], overrides)

    def test_dropdown_popup_and_disabled_states_share_unity_tokens(self) -> None:
        overrides = {
            "PANEL_ACTIVE": "#123ABC",
            "TEXT_DISABLED": "#ABC123",
            "BORDER_STRONG": "#234BCD",
        }
        style = theme.atlas_stylesheet(overrides)
        popup = style.split("QComboBox QAbstractItemView {", 1)[1].split("}", 1)[0]
        disabled = style.split("QComboBox:disabled {", 1)[1].split("}", 1)[0]
        hover = style.split("QComboBox:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("selection-background-color: #123ABC;", popup)
        self.assertIn("selection-color: " + theme.PALETTE["TEXT"] + ";", popup)
        self.assertIn("color: #ABC123;", disabled)
        self.assertIn("border-color: #234BCD;", hover)
        self.assertIn("QComboBox::drop-down {", style)

    def test_module_navigation_states_use_shared_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "GREEN_BORDER": "#123ABC",
            "TEXT_DISABLED": "#ABC123",
            "PANEL_HOVER": "#345BCD",
        })
        pressed = style.split(
            "#TopNavButton:pressed, #TopNavButtonActive:pressed {", 1
        )[1].split("}", 1)[0]
        disabled = style.split(
            "#TopNavButton:disabled, #TopNavButtonActive:disabled {", 1
        )[1].split("}", 1)[0]
        focused = style.split(
            "#TopNavButton:focus, #TopNavButtonActive:focus {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background: #345BCD;", pressed)
        self.assertIn("color: #ABC123;", disabled)
        self.assertIn("border: 1px solid #123ABC;", focused)
        self.assertIn("border-bottom: 2px solid " + theme.PALETTE["GREEN"] + ";", focused)

    def test_guide_category_tree_follows_shared_unity_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "PANEL_ACTIVE": "#123ABC",
            "PANEL_HOVER": "#345BCD",
            "TEXT": "#ABC123",
        })
        self.assertIn("QTreeWidget#GuideLibraryCategories {", style)
        selected = style.split(
            "QTreeWidget#GuideLibraryCategories::item:selected {", 1,
        )[1].split("}", 1)[0]
        hovered = style.split(
            "QTreeWidget#GuideLibraryCategories::item:hover {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: #123ABC;", selected)
        self.assertIn("color: #ABC123;", selected)
        self.assertIn("background: #345BCD;", hovered)
        self.assertIn("QTreeWidget#GuideLibraryCategories::item {", style)

    def test_guide_and_success_selection_borders_do_not_shift_rows(self) -> None:
        style = theme.atlas_stylesheet({"GREEN": "#ABC123"})
        selectors = (
            ("QTreeWidget#GuideLibraryCategories::item", "QTreeWidget#GuideLibraryCategories::item:selected"),
            ("QTreeWidget#AchievementCategoryTree::item", "QTreeWidget#AchievementCategoryTree::item:selected"),
            ("#AchievementsView QListWidget#QuestResultList::item", "#AchievementsView QListWidget#QuestResultList::item:selected"),
        )
        for base_selector, selected_selector in selectors:
            with self.subTest(selector=base_selector):
                # Item metrics must not change when the selection accent is
                # painted, even across keyboard and pointer navigation.
                default = style.split(base_selector + " {", 1)[1].split("}", 1)[0]
                selected = style.split(selected_selector + " {", 1)[1].split("}", 1)[0]
                self.assertIn("border-left: 2px solid transparent;", default)
                self.assertIn("border-left: 2px solid #ABC123;", selected)

    def test_guide_section_title_is_global_without_local_palette(self) -> None:
        style = theme.atlas_stylesheet({"TEXT": "#ABC123"})
        heading = style.split("QLabel#GuideLibrarySectionTitle {", 1)[1].split("}", 1)[0]
        self.assertIn("color: #ABC123;", heading)
        self.assertIn("font-size: 13px;", heading)
        self.assertIn("font-weight: 800;", heading)

    def test_focus_border_has_same_geometry_as_idle_navigation(self) -> None:
        style = theme.atlas_stylesheet()
        idle = style.split("#TopNavButton, #TopNavButtonActive {", 1)[1].split("}", 1)[0]
        focused = style.split(
            "#TopNavButton:focus, #TopNavButtonActive:focus {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border: 1px solid transparent;", idle)
        self.assertIn("border-bottom: 2px solid transparent;", idle)
        self.assertIn("border: 1px solid ", focused)
        self.assertIn("border-bottom: 2px solid ", focused)

    def test_atlas_stylesheet_reuses_cached_static_template(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_renderer(template: str, overrides=None) -> str:
            calls.append((template, overrides))
            return "atlas-style"

        with (
            patch.object(theme, "_render_theme_template", side_effect=fake_renderer),
            patch.object(theme, "unity_skin_stylesheet", return_value="unity-style"),
        ):
            self.assertEqual(theme.atlas_stylesheet(), "atlas-style\nunity-style")
            self.assertEqual(theme.atlas_stylesheet(), "atlas-style\nunity-style")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0][1])


if __name__ == "__main__":
    unittest.main()
