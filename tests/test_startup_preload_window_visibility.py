"""Qt regression: preload has its own window until real tasks are terminal."""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from app.ui.preload_popup import PreloadProgressPopup


class StartupPreloadVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_standalone_preload_is_visible_while_main_stays_hidden(self) -> None:
        main_window = QWidget()
        popup = PreloadProgressPopup(main_window)
        revealed: list[bool] = []
        popup.readyForMainWindow.connect(lambda: (revealed.append(True), main_window.show()))
        try:
            popup.begin({"quests": "IDLE", "encyclopedia": "IDLE", "craft": "IDLE"})
            self.app.processEvents()
            self.assertTrue(popup.isVisible())
            self.assertFalse(main_window.isVisible())

            popup.update_states({"quests": "READY", "encyclopedia": "LOADING", "craft": "IDLE"})
            popup._hide_if_current(popup._hide_generation)
            self.assertFalse(revealed)
            self.assertTrue(popup.isVisible())
            self.assertFalse(main_window.isVisible())

            popup.update_states({"quests": "READY", "encyclopedia": "READY", "craft": "FAILED"})
            popup._hide_if_current(popup._hide_generation)
            self.app.processEvents()
            self.assertEqual(revealed, [True])
            self.assertFalse(popup.isVisible())
            self.assertTrue(main_window.isVisible())
        finally:
            main_window.close()
            popup.deleteLater()
            self.app.processEvents()

    def test_bootstrap_never_shows_main_before_preload(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        entry = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        body = ast.get_source_segment(source, entry) or ""
        self.assertIn("window.preload_popup.begin(dict(window.preload_states))", body)
        self.assertNotIn("window.show()", body)
        self.assertNotIn("splash.finish(window)", body)
        self.assertIn("window.preload_popup.readyForMainWindow.connect(self._reveal_after_preload)", source)


if __name__ == "__main__":
    unittest.main()
