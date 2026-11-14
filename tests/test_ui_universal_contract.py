"""Regression gate: Dev UI is the single contract for all Atlas modules.

Checks actual compiled Qt QSS, all 22 indexed families and 12 module owners.
Only validated widget states are treated as shared; prototypes are excluded.
"""
from __future__ import annotations

import inspect
import re
import unittest
from pathlib import Path

from app.ui.theme import atlas_stylesheet
from app.ui.ui_registry import (
    UI_CONSUMER_INDEX, UI_FAMILY_QSS_SELECTORS,
    UI_INTERACTION_QSS_SELECTORS, validate_ui_index,
)
from app.ui.unity_palette import (
    UNITY_UI_FAMILY_INDEX, UNITY_UI_CONSUMERS,
    UNITY_GLASS_INTENSITY, unity_glass_gradient,
)
from app.ui.organizer_style import ORGANIZER_STYLE_TEMPLATE


REPO_ROOT = Path(__file__).resolve().parents[1]


class UiUniversalContractTests(unittest.TestCase):
    def test_every_gallery_family_and_consumer_is_registered(self):
        validate_ui_index()
        self.assertEqual(len(UI_FAMILY_QSS_SELECTORS), 22)
        self.assertEqual(len(UI_CONSUMER_INDEX), 12)
        self.assertEqual(tuple(UI_FAMILY_QSS_SELECTORS), tuple(UNITY_UI_FAMILY_INDEX))
        self.assertEqual(tuple(UI_CONSUMER_INDEX), UNITY_UI_CONSUMERS)
        for module, entry in UI_CONSUMER_INDEX.items():
            with self.subTest(module=module):
                for path in entry["paths"]:
                    self.assertTrue((REPO_ROOT / path).is_file(), path)
        self.assertEqual(UI_CONSUMER_INDEX["Launcher"]["adapter"], "tk")
        self.assertEqual(UI_CONSUMER_INDEX["Organizer"]["adapter"], "qt_scoped")
        self.assertEqual(
            set(UI_CONSUMER_INDEX) -
            {"Launcher", "Organizer"},
            {name for name, data in UI_CONSUMER_INDEX.items()
             if data["adapter"] == "qt"},
        )

    def test_all_unity_design_tokens_have_one_qt_free_owner(self):
        from app.ui import theme
        from app.ui.unity_palette import (
            UNITY_SPACING_PX, UNITY_TYPOGRAPHY, UNITY_SIZES_PX,
            resolve_unity_colors,
        )
        self.assertEqual(theme.PALETTE, resolve_unity_colors())
        self.assertEqual(theme.TYPOGRAPHY, UNITY_TYPOGRAPHY)
        self.assertEqual(theme.SPACING, {
            f"SPACE_{role.upper()}": f"{px}px"
            for role, px in UNITY_SPACING_PX.items()
        })
        self.assertEqual(
            theme.SIZES["TOP_NAV_HEIGHT"],
            f'{UNITY_SIZES_PX["top_nav_height"]}px',
        )
        self.assertEqual(theme.PALETTE["RED"], "#D71920")
        self.assertEqual(theme.PALETTE["YELLOW"], "#D6B22D")

    def test_one_compiled_qss_covers_every_real_visual_family(self):
        qss = atlas_stylesheet()
        self.assertNotIn("@GLASS_BUTTON", qss)
        self.assertNotIn("@GLASS_HOVER", qss)
        self.assertNotIn("@GLASS_GREEN", qss)
        for family, selectors in UI_FAMILY_QSS_SELECTORS.items():
            with self.subTest(family=family):
                if family in {"metrics", "motion", "coverage", "palette"}:
                    self.assertFalse(selectors)
                    continue
                self.assertTrue(selectors)
                for selector in selectors:
                    self.assertIn(selector, qss)
        for family, selectors in UI_INTERACTION_QSS_SELECTORS.items():
            with self.subTest(states=family):
                for selector in selectors:
                    self.assertIn(selector, qss)

    def test_organizer_reuses_same_css_instead_of_widget_stylesheet(self):
        from app.pages.organizer.organizer_ui import OrganizerUiMixin
        source = inspect.getsource(OrganizerUiMixin.build_organizer_ui)
        self.assertNotIn("setStyleSheet(", source)
        self.assertIn('action.setProperty("atlasShortcutInset", True)', source)
        self.assertIn("#organizerPage QFrame#card", ORGANIZER_STYLE_TEMPLATE)
        self.assertIn(
            '#organizerPage QPushButton[atlasShortcutInset="true"]',
            ORGANIZER_STYLE_TEMPLATE,
        )
        self.assertFalse(
            re.search(r"#[0-9a-fA-F]{6}\\b", ORGANIZER_STYLE_TEMPLATE),
            "Organizer is only allowed to use the canonical Unity color tokens",
        )
        self.assertIn("#organizerPage QFrame#card", atlas_stylesheet())

    def test_all_qt_consumers_inherit_global_qss_without_local_stylesheets(self):
        import ast
        for module, entry in UI_CONSUMER_INDEX.items():
            if entry["adapter"] == "tk":
                continue
            for filename in entry["paths"]:
                with self.subTest(module=module, filename=filename):
                    tree = ast.parse((REPO_ROOT / filename).read_text(encoding="utf-8"))
                    local_styles = [
                        node for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "setStyleSheet"
                    ]
                    self.assertFalse(local_styles, f"{filename}: local QSS bypasses UI Dev")
        self.assertNotIn("background: @GLASS_GREEN;", ORGANIZER_STYLE_TEMPLATE)
        self.assertNotIn("background: @ACTIVE_GRADIENT;", ORGANIZER_STYLE_TEMPLATE)
        self.assertNotIn("background: @RED_DARK;", ORGANIZER_STYLE_TEMPLATE)
        self.assertNotIn("#organizerPage QPushButton#primaryButton:hover",
                         ORGANIZER_STYLE_TEMPLATE)

    def test_tk_launcher_keeps_unity_color_and_font_adapter(self):
        from app.distribution.launcher_ui import COLORS, FONT_FAMILY, button_options
        from app.ui.unity_palette import UNITY_PALETTE, UNITY_TYPOGRAPHY
        self.assertEqual(FONT_FAMILY, "Lexend")
        self.assertIn(FONT_FAMILY, UNITY_TYPOGRAPHY["FONT_FAMILY"])
        opts = button_options()
        self.assertEqual(opts["bg"], UNITY_PALETTE["PANEL_2"])
        self.assertEqual(opts["activebackground"], UNITY_PALETTE["PANEL_HOVER"])
        self.assertEqual(opts["activeforeground"], UNITY_PALETTE["GREEN"])
        self.assertEqual(COLORS["button_focus"], UNITY_PALETTE["GREEN_BORDER"])

    def test_glass_gradient_is_shared_and_override_aware(self):
        from app.pages.organizer.glass_material import (
            GLASS_INTENSITY, unity_glass_gradient as organizer_gradient,
        )

        self.assertEqual(GLASS_INTENSITY, UNITY_GLASS_INTENSITY)
        self.assertEqual(organizer_gradient(), unity_glass_gradient())
        style = atlas_stylesheet({
            "PANEL_ACTIVE": "#112233",
            "PANEL_2": "#223344",
            "PANEL_HOVER": "#334455",
        })
        self.assertIn("stop:0 rgba(17, 34, 51, 243)", style)
        self.assertIn("stop:1 rgba(34, 51, 68, 246)", style)
        self.assertIn("stop:0 rgba(51, 68, 85, 246)", style)
        self.assertIn("#primaryButton:hover", style)
        self.assertNotIn("#organizerPage QPushButton#primaryButton:hover", style)


if __name__ == "__main__":
    unittest.main()
