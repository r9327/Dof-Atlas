"""Pure-Python contracts for the only Unity palette: runnable without PySide6."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.ui.unity_palette import (
    UNITY_COLOR_ALIAS_ROLES, UNITY_ICON_NAMES, UNITY_MAIN_ROLES,
    UNITY_PALETTE, UNITY_SIZES_PX, UNITY_UI_USAGE,
    launcher_colors, resolve_unity_colors,
)


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

    def test_guide_roles_follow_the_same_ui_colors(self) -> None:
        colors = resolve_unity_colors()
        self.assertEqual(
            {name: colors[name] for name in UNITY_COLOR_ALIAS_ROLES},
            {name: colors[parent] for name, parent in UNITY_COLOR_ALIAS_ROLES.items()},
        )
        self.assertLess(len(set(colors.values())), len(colors))
        preview = resolve_unity_colors({
            "PANEL": "#112233",
            "BORDER": "#334455",
        })
        self.assertEqual(preview["GUIDE_COMPACT_SURFACE"], "#112233")
        self.assertEqual(preview["GUIDE_NAV_BORDER"], "#334455")
        self.assertEqual(
            preview["GUIDE_PREPARATION_ROW"], colors["PANEL_2"]
        )
        explicit = resolve_unity_colors({
            "PANEL": "#112233", "GUIDE_COMPACT_SURFACE": "#ABCDEF"
        })
        self.assertEqual(explicit["GUIDE_COMPACT_SURFACE"], "#ABCDEF")
        self.assertEqual(UNITY_PALETTE["PANEL"], "#1B2746")

    def test_ui_places_and_sizes_use_single_source(self) -> None:
        self.assertEqual(len(UNITY_MAIN_ROLES), 10)
        self.assertTrue(set(UNITY_MAIN_ROLES).issubset(UNITY_PALETTE))
        self.assertEqual(len(UNITY_UI_USAGE), 10)
        self.assertTrue(all(
            a in UNITY_PALETTE and b in UNITY_PALETTE
            for _caption, a, b in UNITY_UI_USAGE
        ))
        self.assertEqual(UNITY_SIZES_PX["control_compact"], 24)
        self.assertEqual(UNITY_SIZES_PX["control_normal"], 32)
        self.assertEqual(UNITY_SIZES_PX["icon_large"], 24)
        self.assertEqual(len(UNITY_ICON_NAMES), 8)

    def test_color_module_does_not_import_qt_or_game_runtime(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/ui/unity_palette.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name.startswith(("PySide6", "app.")) for name in imports))


if __name__ == "__main__":
    unittest.main()
