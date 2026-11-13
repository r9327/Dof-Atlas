"""Pure-Python contracts for the only Unity palette: runnable without PySide6."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.ui.unity_palette import UNITY_PALETTE, launcher_colors


class UnityPaletteTests(unittest.TestCase):
    def test_all_tk_roles_follow_canonical_unity_values(self) -> None:
        self.assertEqual(launcher_colors(), {
            "background": UNITY_PALETTE["BG"],
            "panel": UNITY_PALETTE["PANEL"],
            "border": UNITY_PALETTE["BORDER"],
            "track": UNITY_PALETTE["PANEL_2"],
            "text": UNITY_PALETTE["TEXT"],
            "muted": UNITY_PALETTE["TEXT_MUTED"],
            "accent": UNITY_PALETTE["GREEN"],
            "accent_hover": UNITY_PALETTE["GREEN_HOVER"],
        })

    def test_override_changes_tk_colors_without_mutating_unity_palette(self) -> None:
        saved = dict(UNITY_PALETTE)
        preview = {**UNITY_PALETTE, "GREEN": "#123456", "PANEL_2": "#654321"}
        colors = launcher_colors(preview)
        self.assertEqual(colors["accent"], "#123456")
        self.assertEqual(colors["track"], "#654321")
        self.assertEqual(UNITY_PALETTE, saved)

    def test_color_module_does_not_import_qt_or_game_runtime(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/ui/unity_palette.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name.startswith(("PySide6", "app.")) for name in imports))


if __name__ == "__main__":
    unittest.main()
