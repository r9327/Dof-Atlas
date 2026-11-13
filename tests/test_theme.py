"""Direct UI-theme owner: Guide Ultime follows shared Successes widgets.

The legacy designer must not reintroduce per-view dropdown overrides.
"""
from __future__ import annotations

import unittest

import app.ui.theme as theme


class SharedThemeTests(unittest.TestCase):
    def test_guide_ultime_dropdown_inherits_successes_global_rules(self) -> None:
        overrides = {
            "PANEL_2": "#123ABC",
            "PANEL_ACTIVE": "#234BCD",
            "BORDER": "#345CDE",
            "BORDER_STRONG": "#456DEF",
        }
        style = theme.atlas_stylesheet(overrides)
        # A Guide-specific QComboBox rule used to override the common
        # popup/focus/hover rules twice with incompatible padding/colors.
        self.assertNotIn("#GuideUltimeGeneratedView QComboBox", style)
        common = style.split(
            "QLineEdit, QComboBox, QSpinBox, #inputField, #comboField {", 1
        )[0]
        self.assertIn("QComboBox", common)
        dropdown = style.split("QComboBox QAbstractItemView {", 1)[1].split("}", 1)[0]
        self.assertIn("background: #123ABC;", dropdown)
        self.assertIn("selection-background-color: #234BCD;", dropdown)
        self.assertIn("border: 1px solid #345CDE;", dropdown)
        hover = style.split("QComboBox:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("border-color: #456DEF;", hover)
        # Do not disturb Guide-only buttons and other interactive controls.
        self.assertIn(
            "#GuideUltimeGeneratedView QPushButton,\n"
            "#GuideUltimeGeneratedView QToolButton {",
            style,
        )
        self.assertIn("#GuideUltimeGeneratedView QCheckBox {", style)

    def test_shared_buttons_use_one_typography_spacing_and_radius_contract(self) -> None:
        from app.ui.components import BUTTON_OBJECT_NAMES

        self.assertEqual(BUTTON_OBJECT_NAMES["navigation"], "TopNavButton")
        self.assertEqual(BUTTON_OBJECT_NAMES["navigation_active"], "TopNavButtonActive")
        self.assertEqual(BUTTON_OBJECT_NAMES["primary"], "PrimaryActionButton")
        self.assertEqual(BUTTON_OBJECT_NAMES["secondary"], "SecondaryButton")

        style = theme.atlas_stylesheet({
            "FONT_SMALL": "15px",
            "FONT_BODY": "16px",
            "RADIUS_SM": "9px",
            "SPACE_LG": "17px",
            "SPACE_MD": "13px",
        })
        common = style.split(
            "#primaryButton, #ActiveButton, #PrimaryActionButton,\n"
            "#secondaryButton, #SecondaryButton {", 1,
        )[1].split("}", 1)[0]
        for rule in (
            "font-size: 15px;",
            "padding-left: 17px;",
            "padding-right: 13px;",
        ):
            self.assertIn(rule, common)

        primary = style.split(
            "#primaryButton, #ActiveButton, #PrimaryActionButton {", 1
        )[1].split("}", 1)[0]
        # The first occurrence belongs to the shared primary/secondary
        # typography block; inspect the final variant-specific color rule.
        secondary = style.rsplit(
            "#secondaryButton, #SecondaryButton {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background: ", primary)
        self.assertIn("background: ", secondary)
        self.assertNotIn("padding-left", primary)
        self.assertNotIn("padding-left", secondary)
        self.assertIn("font-size: 16px;", style)
        self.assertIn("border-radius: 9px;", style)

        normal = theme.atlas_stylesheet()
        self.assertIn("font-size: 11px;", normal)
        self.assertIn("font-size: 12px;", normal)
        self.assertIn("border-radius: 6px;", normal)

    def test_stateful_toggles_share_unity_roles_without_losing_layout(self) -> None:
        """Guide and segmented controls share states, not their text layout."""
        style = theme.atlas_stylesheet({
            "PANEL_2": "#123456",
            "BORDER": "#345678",
            "TEXT_SOFT": "#789ABC",
            "PANEL_HOVER": "#234567",
            "BORDER_STRONG": "#456789",
            "GREEN_DARK": "#345634",
            "GREEN": "#456745",
        })
        shared = style.split(
            "#GuideHideCompletedToggle,\n"
            "#segmentedButton, #segmentedButtonActive {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: #123456;", shared)
        self.assertIn("border-color: #345678;", shared)
        self.assertIn("color: #789ABC;", shared)
        hover = style.split(
            "#GuideHideCompletedToggle:hover, #segmentedButton:hover {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: #234567;", hover)
        self.assertIn("border-color: #456789;", hover)
        active = style.split(
            "#GuideHideCompletedToggle:checked, #segmentedButtonActive {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: #345634;", active)
        self.assertIn("border-color: #456745;", active)
        guide_layout = style.split(
            "#GuideHideCompletedToggle {", 1,
        )[1].split("}", 1)[0]
        segment_layout = style.split("#GuideHideCompletedToggle {", 1)[1].split(
            "#segmentedButton, #segmentedButtonActive {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("text-align: left;", guide_layout)
        self.assertIn("text-align: center;", segment_layout)
        self.assertIn("border: 1px solid #345678;", segment_layout)
        self.assertIn("#GuideHideCompletedToggle:checked:hover {", style)

    def test_breadcrumb_has_one_global_owner_and_live_unity_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "TEXT_MUTED": "#102030",
            "PANEL_HOVER": "#203040",
            "GREEN_BORDER": "#304050",
        })
        self.assertNotIn("QPushButton#GuideBreadcrumbButton,\n", style)
        self.assertNotIn("QPushButton#GuideBreadcrumbButton:hover,\n", style)
        self.assertEqual(style.count("QPushButton#GuideBreadcrumbButton {"), 1)
        self.assertEqual(style.count("QPushButton#GuideBreadcrumbButton:hover {"), 1)
        normal = style.split("QPushButton#GuideBreadcrumbButton {", 1)[1].split("}", 1)[0]
        hover = style.split("QPushButton#GuideBreadcrumbButton:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("color: #102030;", normal)
        self.assertIn("background: #203040;", hover)
        self.assertIn("border-color: #304050;", hover)
        self.assertIn("QPushButton#GuideInlineQuestButton,", style)

    def test_shared_guide_row_glass_tracks_live_unity_tokens(self) -> None:
        style = theme.atlas_stylesheet({
            "PANEL_HOVER": "#123456",
            "BORDER_SOFT": "#ABCDEF",
            "RADIUS_XS": "11px",
            "RADIUS_SM": "13px",
            "SPACE_XXS": "3px",
        })
        rules = style.split(
            "QFrame#GuideManualCombatSection,\n"
            "QFrame#GuideManualCombatLineRow,\n"
            "QFrame#GuideManualCombatInlineRow {", 1,
        )[1].split("}", 1)[0]
        self.assertIn("background: rgba(18, 52, 86, 0.05);", rules)
        self.assertIn("border: 1px solid rgba(171, 205, 239, 0.18);", rules)
        self.assertIn("border-radius: 11px;", rules)
        section_rule = style.split(
            "QFrame#GuideManualCombatSection {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 13px;", section_rule)
        warning_line = style.split(
            "QFrame#GuideManualWarningSection QLabel#GuideManualLine {", 1
        )[1].split("}", 1)[0]
        self.assertIn("padding: 3px 0;", warning_line)
        self.assertIn("QFrame#GuideManualLineRow", style)
        # This rule intentionally uses an object-name selector, independent
        # of the concrete Qt class (the live widget remains a QCheckBox).
        self.assertIn("#GuideManualCombatCheck {", style)

    def test_unity_skin_radii_follow_theme_overrides_without_local_duplicates(self) -> None:
        from app.ui.unity_palette import UNITY_RADII

        self.assertEqual(
            {key: theme.SIZES[key] for key in UNITY_RADII}, UNITY_RADII,
        )
        style = theme.atlas_stylesheet({
            "RADIUS_XS": "14px",
            "RADIUS_SM": "16px",
            "RADIUS_MD": "18px",
        })
        group = style.split("QGroupBox, QTabWidget::pane {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: 16px;", group)
        featured = style.split(
            "QFrame#GuideFeaturedCard { background: qlineargradient(", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 18px;", featured)
        progress = style.split(
            "QFrame#GuideFeaturedCard QProgressBar#GuideFeaturedProgress {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 14px;", progress)
        copy_hover = style.split(
            "QPushButton#GuidePreparationItemCopy:hover {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-radius: 14px;", copy_hover)
        self.assertEqual(theme.SIZES["RADIUS_SM"], "6px")
        self.assertEqual(theme.SIZES["RADIUS_MD"], "8px")

    def test_guide_color_aliases_follow_common_unity_overrides(self) -> None:
        from app.ui.unity_palette import UNITY_SIZES_PX

        style = theme.atlas_stylesheet({
            "PANEL": "#112233",
            "PANEL_2": "#223344",
            "PANEL_ACTIVE": "#334455",
            "BORDER_CARD": "#445566",
        })
        # The Guide is not allowed to maintain a parallel surface palette.
        self.assertIn("rgba(17, 34, 51, 0.93)", style)
        self.assertIn("rgba(34, 51, 68, 0.92)", style)
        self.assertIn("rgba(51, 68, 85, 0.97)", style)
        self.assertIn("rgba(68, 85, 102, 0.65)", style)
        self.assertEqual(
            theme.SIZES["CONTROL_HEIGHT_COMPACT"],
            f'{UNITY_SIZES_PX["control_compact"]}px',
        )
        self.assertEqual(
            theme.SIZES["ICON_SIZE_LARGE"],
            f'{UNITY_SIZES_PX["icon_large"]}px',
        )

    def test_guide_buttons_remain_themed_after_dropdown_unification(self) -> None:
        style = theme.atlas_stylesheet({"GREEN_BORDER": "#135790"})
        button_hover = style.split(
            "#GuideUltimeGeneratedView QPushButton:hover,\n"
            "#GuideUltimeGeneratedView QToolButton:hover {", 1
        )[1].split("}", 1)[0]
        self.assertIn("border-color: #135790;", button_hover)
        self.assertNotIn("#GuideUltimeGeneratedView QComboBox", style)


if __name__ == "__main__":
    unittest.main()
