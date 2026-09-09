from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLabel

import app.storage as storage
from app.constants import APP_ICON_PATH, LOGO_PATH
from app.pages.craft_page import quantity_spinbox
from app.ui.components import AtlasButton, AtlasDialogHeader, atlas_application_icon
from app.ui.theme import PALETTE, atlas_stylesheet, render_theme_template
from main import AtlasWindow, CloseActionDialog


class UiFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(atlas_stylesheet())

    def test_global_theme_renders_every_token_and_supports_overrides(self):
        style = atlas_stylesheet()
        self.assertNotIn("@", style)
        self.assertIn(f"background: {PALETTE['BG']};", style)
        self.assertIn("QDialog#CloseActionDialog", style)
        rendered_colors = {
            color.upper()
            for color in re.findall(r"#[0-9a-fA-F]{6}", style)
        }
        palette_colors = {
            color.upper()
            for value in PALETTE.values()
            for color in re.findall(r"#[0-9a-fA-F]{6}", value)
        }
        self.assertLessEqual(rendered_colors, palette_colors)

        preview = atlas_stylesheet({"BG": "#010203"})
        self.assertIn("QMainWindow, QWidget {\n    background: #010203;", preview)
        with self.assertRaises(KeyError):
            atlas_stylesheet({"NOT_A_THEME_TOKEN": "value"})

    def test_legacy_module_qss_is_rendered_with_home_palette(self):
        rendered = render_theme_template(
            "background:#080b12;color:#f1f4fb;border:#6f4bb6;"
        )
        self.assertEqual(
            rendered,
            (
                f"background:{PALETTE['BG']};"
                f"color:{PALETTE['TEXT']};"
                f"border:{PALETTE['GREEN']};"
            ),
        )

    def test_shared_button_variants_remain_storage_compatible(self):
        self.assertIs(storage.AtlasButton, AtlasButton)
        expected = {
            "primary": "PrimaryActionButton",
            "secondary": "SecondaryButton",
            "danger": "DangerButton",
        }
        for variant, object_name in expected.items():
            button = AtlasButton("Action", variant=variant)
            self.assertEqual(button.objectName(), object_name)
            button.deleteLater()
        with self.assertRaises(ValueError):
            AtlasButton("Action", variant="unknown")

    def test_one_canonical_logo_asset_builds_the_application_icon(self):
        self.assertEqual(APP_ICON_PATH, LOGO_PATH)
        self.assertTrue(APP_ICON_PATH.exists())
        self.assertFalse(atlas_application_icon().isNull())

    def test_shell_window_and_brand_reuse_the_same_icon(self):
        with (
            patch.object(AtlasWindow, "start_runtime", return_value=None),
            patch.object(AtlasWindow, "setup_tray", return_value=None),
        ):
            window = AtlasWindow()
            try:
                self.assertEqual(
                    window.shell_icon.cacheKey(),
                    window.windowIcon().cacheKey(),
                )
                self.assertEqual(
                    window.shell_icon.cacheKey(),
                    window.brand_button.icon().cacheKey(),
                )
                self.assertIsNotNone(window.brand_icon_label.pixmap())
                self.assertFalse(window.brand_icon_label.pixmap().isNull())
            finally:
                window.quit_requested = True
                window.close()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)

    def test_close_dialog_uses_global_components_and_action_variants(self):
        dialog = CloseActionDialog()
        try:
            self.assertFalse(dialog.windowIcon().isNull())
            self.assertIsNotNone(dialog.findChild(AtlasDialogHeader))
            body = dialog.findChild(QLabel, "DialogBody")
            self.assertIsNotNone(body)
            buttons = {
                button.text(): button.objectName()
                for button in dialog.findChildren(AtlasButton)
            }
            self.assertEqual(
                buttons,
                {
                    "Annuler": "SecondaryButton",
                    "Quitter": "DangerButton",
                    "Réduire": "PrimaryActionButton",
                },
            )
        finally:
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(dialog, QEvent.DeferredDelete)

    def test_quantity_spinbox_uses_global_qss_instead_of_local_style(self):
        spinbox = quantity_spinbox(3)
        try:
            self.assertEqual(spinbox.objectName(), "QuantitySpinBox")
            self.assertEqual(spinbox.styleSheet(), "")
            self.assertIn("QSpinBox#QuantitySpinBox", atlas_stylesheet())
        finally:
            spinbox.deleteLater()


if __name__ == "__main__":
    unittest.main()
