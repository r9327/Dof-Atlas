"""Direct stdlib-only contract for the standalone Tk launcher UI."""
from __future__ import annotations

import ast
import inspect
import unittest
from unittest.mock import MagicMock

from app.distribution import launcher_ui
from app.ui.unity_palette import UNITY_PALETTE, launcher_colors


class LauncherUiTests(unittest.TestCase):
    def test_launcher_uses_the_same_tokens_without_a_second_palette(self) -> None:
        self.assertEqual(launcher_ui.COLORS, launcher_colors())
        self.assertIs(launcher_ui.COLORS, launcher_ui.UNITY_PALETTE)
        self.assertEqual(launcher_ui.COLORS["background"], UNITY_PALETTE["BG"])
        self.assertEqual(launcher_ui.COLORS["accent"], UNITY_PALETTE["GREEN"])
        self.assertEqual(launcher_ui.COLORS["track"], UNITY_PALETTE["PANEL_2"])
        launcher_tree = ast.parse(inspect.getsource(launcher_ui))
        imports = [n.module or "" for n in ast.walk(launcher_tree) if isinstance(n, ast.ImportFrom)]
        self.assertIn("app.ui.unity_palette", imports)
        self.assertNotIn("app.ui.unity_skin", imports)
        self.assertNotIn("app.ui.theme", imports)
        self.assertFalse(any(name.startswith("PySide6") for name in imports))

    def test_launcher_geometry_is_shared_with_dev_ui_without_qt(self) -> None:
        from pathlib import Path
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX

        size = UNITY_MODULE_GEOMETRY_PX["launcher"]
        self.assertEqual(size["normal_window_size"], (470, 252))
        self.assertEqual(size["install_window_size"], (520, 425))
        self.assertEqual(size["progress_width"], 408)
        self.assertEqual(launcher_ui.button_options()["padx"],
                         size["button_padding_x"])
        self.assertEqual(launcher_ui.button_options()["pady"],
                         size["button_padding_y"])
        source = (Path(__file__).resolve().parents[1] /
                  "app/distribution/launcher.py").read_text(encoding="utf-8")
        self.assertIn('LAUNCHER_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["launcher"]',
                      source)
        self.assertNotIn('(520, 425) if choosing_install else (470, 252)',
                         source)

    def test_tk_controls_still_receive_expected_active_colors(self) -> None:
        self.assertEqual(launcher_ui.button_options()["bg"], UNITY_PALETTE["PANEL_2"])
        self.assertEqual(launcher_ui.button_options()["fg"], UNITY_PALETTE["TEXT_SOFT"])
        self.assertEqual(launcher_ui.button_options()["activebackground"], UNITY_PALETTE["PANEL_HOVER"])
        self.assertEqual(launcher_ui.button_options()["activeforeground"], UNITY_PALETTE["GREEN"])
        self.assertEqual(launcher_ui.button_options()["highlightcolor"], UNITY_PALETTE["GREEN_BORDER"])
        self.assertEqual(launcher_ui.button_options()["highlightthickness"], 1)
        self.assertEqual(launcher_ui.button_options()["font"][0], launcher_ui.FONT_FAMILY)
        style = MagicMock()
        launcher_ui.progress_style(style)
        self.assertEqual(style.configure.call_args.kwargs["troughcolor"], UNITY_PALETTE["PANEL_2"])
        self.assertEqual(style.configure.call_args.kwargs["background"], UNITY_PALETTE["GREEN"])
        style.theme_use.assert_called_once_with("clam")


if __name__ == "__main__":
    unittest.main()
