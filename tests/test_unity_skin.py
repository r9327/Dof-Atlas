"""Tests for the optional local Unity skin; no packaged or licensed assets implied."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.unity_skin import UNITY_PALETTE, unity_enabled, unity_skin_stylesheet


class UnitySkinTests(unittest.TestCase):
    def test_disabled_unless_explicitly_selected(self) -> None:
        with patch.dict(os.environ, {"ATLAS_THEME": "atlas"}):
            self.assertFalse(unity_enabled())
            self.assertEqual(unity_skin_stylesheet(), "")
        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            self.assertTrue(unity_enabled())

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
