from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.storage import ZaapWidget


class OrganizerZaapPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_widget(self, callback) -> ZaapWidget:
        with (
            patch("app.storage.load_zaap_index", return_value=[]),
            patch("app.storage.read_zaap_click_locked", return_value=True),
            patch("app.storage.read_zaap_click_position", return_value=(0, 0)),
        ):
            widget = ZaapWidget(
                status_callback=Mock(),
                start_callback=callback,
                show_position_controls=False,
                show_favorites=False,
            )
        widget.show()
        widget.suggestion_popup.addItem("Zaap test")
        widget.suggestion_popup.show()
        self.app.processEvents()
        self.assertTrue(widget.suggestion_popup.isVisible())
        return widget

    def test_selection_closes_popup_before_runtime_callback(self) -> None:
        observed = []

        def launch(*args):
            observed.append((widget.suggestion_popup.isVisible(), args[0]))

        widget = self.make_widget(launch)
        try:
            widget.launch_zaap({"label": "Zaap test", "posX": 1, "posY": 2})
            self.assertEqual(observed, [(False, "/zaap 1,2")])
            self.assertFalse(widget.suggestion_popup.isVisible())
        finally:
            widget.close()

    def test_invalid_destination_closes_popup_without_dispatch(self) -> None:
        launcher = Mock()
        widget = self.make_widget(launcher)
        try:
            widget.launch_zaap({"label": "Sans coordonnées"})
            self.assertFalse(widget.suggestion_popup.isVisible())
            launcher.assert_not_called()
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
