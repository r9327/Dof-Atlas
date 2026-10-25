"""Tests for the optional local Unity skin; no packaged or licensed assets implied."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.ui import unity_skin
from app.ui.unity_skin import UNITY_PALETTE, unity_enabled, unity_skin_stylesheet, sprite_icon_path, UnityBackdrop


class UnitySkinTests(unittest.TestCase):
    def test_disabled_unless_explicitly_selected(self) -> None:
        with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
            self.assertFalse(unity_enabled())
            self.assertEqual(unity_skin_stylesheet(), "")
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            self.assertTrue(unity_enabled())

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_local_icon_is_not_used_in_default_app(self) -> None:
        with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
            self.assertIsNone(sprite_icon_path("guide"))
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            self.assertIsNone(sprite_icon_path("not-an-allowlisted-icon"))

    def test_real_local_sprites_have_all_states_and_single_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = Path(directory)
            sprites = asset_dir / "sprites"
            sprites.mkdir()
            source = QImage(48, 24, QImage.Format_ARGB32)
            source.fill(0xff5262a1)
            self.assertTrue(source.save(str(asset_dir / "background_selection_original.png")))
            for state in ("normal", "over", "pressed", "disabled"):
                self.assertTrue(source.save(str(sprites / f"btn_green_{state}.png")))
            self.assertTrue(source.save(str(sprites / "Assets_UI_Themes_Figma_menuIcons_1x_guide-png.png")))
            with patch.object(unity_skin, "_ASSETS", asset_dir), patch.dict(
                os.environ, {"ATLAS_THEME": "dofus_unity"},
            ):
                style = unity_skin_stylesheet()
                for state in ("normal", "over", "pressed", "disabled"):
                    self.assertIn(f"btn_green_{state}.png", style)
                self.assertIn("border-image:", style)
                self.assertIn("rgba(27, 39, 70, 0.88)", style)
                self.assertIn("QWidget#EncyclopediaPage", style)
                self.assertIn("QWidget#organizerPage", style)
                self.assertIn("QPushButton:focus", style)
                self.assertTrue(sprite_icon_path("guide").is_file())
                backdrop = UnityBackdrop()
                backdrop.resize(130, 90)
                self.assertFalse(backdrop._pixmap.isNull())
                backdrop.show()
                self.app.processEvents()
                # Widget paints from one parent pixmap, not one per child/page.
                self.assertEqual(backdrop._pixmap.size().width(), 48)
                backdrop.close()
                backdrop.deleteLater()
                self.app.processEvents()

    def test_palette_contrast_roles_and_sprite_state_contract(self) -> None:
        self.assertNotEqual(UNITY_PALETTE["BG"], UNITY_PALETTE["TEXT"])
        self.assertIn("SHELL_GRADIENT", UNITY_PALETTE)
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            style = unity_skin_stylesheet()
            self.assertIn("AtlasUnityBackdrop", style)
            self.assertIn("QPushButton:focus", style)
            if "btn_green_normal.png" in style:
                for required in ("btn_green_over.png", "btn_green_pressed.png", "btn_green_disabled.png"):
                    self.assertIn(required, style)
                self.assertIn("border-image", style)


if __name__ == "__main__":
    unittest.main()
