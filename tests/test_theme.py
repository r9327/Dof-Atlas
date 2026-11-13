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
