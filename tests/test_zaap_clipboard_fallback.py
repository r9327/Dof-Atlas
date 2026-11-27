"""Qt regression: a locally valid Zaap remains usable without the runtime."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.storage import ZaapWidget


class ZaapClipboardFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _panel(start_callback):
        messages = []
        panel = SimpleNamespace(
            launching_zaap=False,
            suggestion_label=lambda row: row["label"],
            status_callback=messages.append,
            hide_suggestions=Mock(),
            search_input=Mock(),
            config_update_callback=None,
            start_callback=start_callback,
            _schedule_owned_callback=lambda _delay, callback: callback(),
        )
        panel.reset_launch_guard = lambda: setattr(panel, "launching_zaap", False)
        return panel, messages

    def test_explicit_runtime_refusal_copies_local_zaap_command(self) -> None:
        callback = Mock(return_value=False)
        panel, messages = self._panel(callback)
        QApplication.clipboard().setText("previous")
        with patch("app.storage.row_coordinate_pair", return_value=(1, -2)):
            ZaapWidget.launch_zaap(panel, {"label": "Astrub"})
        callback.assert_called_once()
        self.assertEqual(QApplication.clipboard().text(), "/zaap 1,-2")
        self.assertIn("commande copiée", messages[-1])
        self.assertFalse(panel.launching_zaap)

    def test_missing_runtime_copies_valid_zaap_without_fake_launch(self) -> None:
        panel, messages = self._panel(None)
        with patch("app.storage.row_coordinate_pair", return_value=(1, -2)):
            ZaapWidget.launch_zaap(panel, {"label": "Astrub"})
        self.assertEqual(QApplication.clipboard().text(), "/zaap 1,-2")
        self.assertIn("commande copiée", messages[-1])

    def test_successful_launch_does_not_change_clipboard(self) -> None:
        panel, messages = self._panel(Mock(return_value=True))
        QApplication.clipboard().setText("saved user text")
        with patch("app.storage.row_coordinate_pair", return_value=(1, -2)):
            ZaapWidget.launch_zaap(panel, {"label": "Astrub"})
        self.assertEqual(QApplication.clipboard().text(), "saved user text")
        self.assertIn("en cours", messages[-1])

    def test_failed_popup_cleanup_does_not_keep_launch_guard_locked(self) -> None:
        callback = Mock(return_value=True)
        panel, _messages = self._panel(callback)
        panel.hide_suggestions.side_effect = RuntimeError("popup deleted")
        with self.assertRaises(RuntimeError):
            ZaapWidget.launch_zaap(panel, {"label": "Astrub [1,-2]"})
        self.assertFalse(panel.launching_zaap)
        callback.assert_not_called()

    def test_real_invalid_source_rows_never_launch_or_copy(self) -> None:
        callback = Mock(return_value=True)
        panel, messages = self._panel(callback)
        QApplication.clipboard().setText("keep")
        for row in (
            {"label": "Zone 1 niveau 50"},
            {"label": "[1,2]", "posX": -2147483648, "posY": 0},
            {"label": "[1,2]", "posX": 3, "posY": 4},
        ):
            ZaapWidget.launch_zaap(panel, row)
        callback.assert_not_called()
        self.assertEqual(QApplication.clipboard().text(), "keep")
        self.assertFalse(panel.launching_zaap)

    def test_unverified_coordinates_never_change_clipboard(self) -> None:
        callback = Mock(return_value=True)
        panel, messages = self._panel(callback)
        QApplication.clipboard().setText("keep")
        with patch("app.storage.row_coordinate_pair", return_value=None):
            ZaapWidget.launch_zaap(panel, {"label": "Inconnu"})
        callback.assert_not_called()
        self.assertEqual(QApplication.clipboard().text(), "keep")
        self.assertIn("coordonnees absentes", messages[-1])


if __name__ == "__main__":
    unittest.main()
