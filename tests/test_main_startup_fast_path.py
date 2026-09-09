from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"


class MainStartupFastPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MAIN_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(MAIN_PATH))

    def test_splash_uses_buffer_helper_not_per_pixel_qcolor_loop(self) -> None:
        function = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "splash_logo_pixmap"
        )
        segment = ast.get_source_segment(self.source, function) or ""
        self.assertIn("clear_connected_dark_background(image)", segment)
        self.assertNotIn("pixelColor(", segment)
        self.assertNotIn("setPixelColor(", segment)
        self.assertNotIn("while queue", segment)

    def test_global_theme_is_ready_before_main_window_construction(self) -> None:
        main_function = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        segment = ast.get_source_segment(self.source, main_function) or ""
        theme_index = segment.index("app.setStyleSheet(atlas_stylesheet())")
        window_index = segment.index("window = AtlasWindow(")
        self.assertLess(theme_index, window_index)

    def test_window_style_refresh_is_idempotent(self) -> None:
        window_class = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AtlasWindow"
        )
        method = next(
            node
            for node in window_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "apply_style"
        )
        segment = ast.get_source_segment(self.source, method) or ""
        self.assertIn("app.styleSheet() != style", segment)

    def test_tray_creation_is_deferred_out_of_window_constructor(self) -> None:
        window_class = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AtlasWindow"
        )
        constructor = next(
            node
            for node in window_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        segment = ast.get_source_segment(self.source, constructor) or ""
        self.assertIn("self._schedule_owned_callback(0, self.setup_tray)", segment)
        self.assertNotIn("\n        self.setup_tray()", segment)


if __name__ == "__main__":
    unittest.main()
