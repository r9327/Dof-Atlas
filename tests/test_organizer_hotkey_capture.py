from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QWidget

from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin


class _CaptureWidget(OrganizerHotkeysMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.capture_target = None
        self.click_button = Mock()
        self.double_click_button = Mock()
        self.stop_script_hotkey_button = Mock()
        self.update_global_buttons = Mock()
        self.render_sessions = Mock()
        self.status_callback = Mock()


class OrganizerHotkeyCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_escape_does_not_persist_a_shortcut(self) -> None:
        widget = _CaptureWidget()
        try:
            with patch("app.pages.organizer.organizer_hotkeys.QTimer") as timer_class:
                widget.begin_capture("click")
                self.assertIsNotNone(widget.capture_target)
                event = Mock()
                event.key.return_value = Qt.Key_Escape
                widget.keyPressEvent(event)
                self.assertIsNone(widget.capture_target)
                timer_class.return_value.stop.assert_called()
                event.accept.assert_called_once()
                widget.update_global_buttons.assert_called()
        finally:
            widget.close()
            widget.deleteLater()

    def test_timeout_restores_normal_buttons(self) -> None:
        widget = _CaptureWidget()
        try:
            with patch("app.pages.organizer.organizer_hotkeys.QTimer") as timer_class:
                widget.begin_capture("click")
                timer_class.return_value.start.assert_called_once_with(12_000)
                on_timeout = timer_class.return_value.timeout.connect.call_args.args[0]
                on_timeout()
                self.assertIsNone(widget.capture_target)
                widget.render_sessions.assert_called()
                self.assertIn("délai", widget.status_callback.call_args.args[0])
        finally:
            widget.close()
            widget.deleteLater()

    def test_focus_loss_cancels_pending_capture(self) -> None:
        widget = _CaptureWidget()
        try:
            with patch("app.pages.organizer.organizer_hotkeys.QTimer"):
                widget.begin_capture("click")
                widget.focusOutEvent(QFocusEvent(QEvent.FocusOut))
                self.assertIsNone(widget.capture_target)
                self.assertIn("perdu le focus", widget.status_callback.call_args.args[0])
        finally:
            widget.close()
            widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
