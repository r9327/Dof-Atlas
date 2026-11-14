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

    def test_preload_popup_style_is_canonical_and_follows_unity_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "BG": "#102030",
            "PANEL_2": "#203040",
            "BORDER": "#304050",
            "TEXT": "#405060",
            "TEXT_MUTED": "#506070",
            "GREEN": "#607080",
            "FONT_FAMILY": '"Arial"',
            "RADIUS_XL": "15px",
        })
        selectors = (
            ("QDialog#PreloadProgressPopup", ("background: #102030;", "border: 1px solid #304050;", "border-radius: 15px;")),
            ("QLabel#PreloadPopupTitle", ("color: #405060;", 'font-family: "Arial";')),
            ("QLabel#PreloadPopupCurrent", ("color: #506070;", 'font-family: "Arial";')),
            ("QProgressBar#PreloadPopupProgress", ("background: #203040;", "color: #405060;")),
            ("QProgressBar#PreloadPopupProgress::chunk", ("background: #607080;",)),
        )
        for selector, rules in selectors:
            with self.subTest(selector=selector):
                section = style.split(selector + " {", 1)[1].split("}", 1)[0]
                for rule in rules:
                    self.assertIn(rule, section)
        from app.ui.preload_popup import PreloadProgressPopup
        self.assertNotIn("setStyleSheet", PreloadProgressPopup.__init__.__code__.co_names)

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

    def test_preview_overrides_reach_shared_unity_widget_layer(self) -> None:
        overrides = {
            "TEXT": "#142536",
            "BORDER": "#253647",
            "BORDER_CARD": "#364758",
        }
        style = theme.atlas_stylesheet(overrides)
        group = style.rsplit("QGroupBox, QTabWidget::pane {", 1)[1].split("}", 1)[0]
        dialog = style.rsplit("QDialog#AtlasDialog, QMenu {", 1)[1].split("}", 1)[0]
        self.assertIn("color: #142536;", group)
        self.assertIn("border: 1px solid #253647;", group)
        self.assertIn("color: #142536;", dialog)
        self.assertIn("border: 1px solid #364758;", dialog)
        self.assertEqual(theme.PALETTE["TEXT"], "#F1F6FB")

    def test_home_badge_and_almanax_use_shared_semantic_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "TEXT_MUTED": "#223344",
            "TEXT_SOFT": "#445566",
        })
        corner = style.split("#StatusBadge, #ActivityBadge {", 1)[1].split("}", 1)[0]
        blocked = style.split('#StatusBadge[state="blocked"] {', 1)[1].split("}", 1)[0]
        almanax = style.split("#HomeAlmanaxText {", 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent;", corner)
        self.assertIn("border-top: 2px solid #223344;", corner)
        self.assertIn("border-left: 2px solid #223344;", corner)
        self.assertIn("color: #223344;", blocked)
        self.assertIn("border-color: #223344;", blocked)
        self.assertNotIn("#HomePlaceholderBadge {", style)
        self.assertIn("color: #445566;", almanax)

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
            ("QTreeWidget#GuideLibraryCategories::item", "QTreeWidget#GuideLibraryCategories::item:selected", 2),
            ("QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item", "QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item:selected", 3),
            ("QWidget#AchievementsView QListWidget#QuestResultList::item", "QWidget#AchievementsView QListWidget#QuestResultList::item:selected", 3),
        )
        for base_selector, selected_selector, width in selectors:
            with self.subTest(selector=base_selector):
                # Item metrics must not change when the selection accent is
                # painted, even across keyboard and pointer navigation.
                default = style.split(base_selector + " {", 1)[1].split("}", 1)[0]
                selected = style.split(selected_selector + " {", 1)[1].split("}", 1)[0]
                self.assertIn(f"border-left: {width}px solid transparent;", default)
                self.assertIn(f"border-left: {width}px solid #ABC123;", selected)

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
