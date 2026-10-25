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
from app.ui.unity_skin import (
    UNITY_PALETTE, UnityBackdrop, unity_enabled, unity_skin_stylesheet,
    sprite_icon_path, wallpaper_path,
)


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

    def test_clean_wallpaper_has_priority_without_mutating_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_dir = Path(directory)
            original = asset_dir / "background_selection_original.png"
            cleaned = asset_dir / "background_selection_clean.png"
            original.write_bytes(b"unchanged-original")
            with patch.object(unity_skin, "_ASSETS", asset_dir):
                with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
                    self.assertIsNone(wallpaper_path())
                with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
                    self.assertEqual(wallpaper_path(), original)
                    cleaned.write_bytes(b"approved-derived-image")
                    self.assertEqual(wallpaper_path(), cleaned)
                    self.assertEqual(original.read_bytes(), b"unchanged-original")
                    cleaned.unlink()
                    self.assertEqual(wallpaper_path(), original)

    def test_global_widget_families_and_focus_stay_themable(self) -> None:
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            style = unity_skin_stylesheet()
        for selector in (
            "QTreeWidget", "QTabWidget::pane", "QToolTip", "QProgressBar",
            "QTableView", "QPlainTextEdit", "QHeaderView::section",
        ):
            self.assertIn(selector, style)
        self.assertIn("rgba(27, 39, 70, 0.78)", style)
        self.assertIn('QWidget[atlasUnityPage="true"]', style)
        self.assertIn("QPushButton#FeaturedGuideOpen:focus", style)
        for root_name in ("GuidesView", "GuidesHomePage", "GuidesHomeContent", "GuidesDetailPage"):
            self.assertIn(f"QWidget#{root_name}", style)
        self.assertIn("QListView#GuidesHomeDofusGrid", style)
        self.assertIn("border-image: none", style)
        self.assertIn("selection-color: #F1F6FB", style)
        # This final rule must not be masked by the normal/hover sprite rule.
        self.assertEqual(
            style.rfind("QPushButton:focus"),
            style.rfind("QPushButton:focus, QToolButton:focus"),
        )
        with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
            self.assertEqual(unity_skin_stylesheet(), "")

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
