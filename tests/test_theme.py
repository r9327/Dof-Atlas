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
        secondary = style.split(
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
