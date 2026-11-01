from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QWidget

from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
from app.constants import KEY_CLICK_HOTKEY, KEY_RADIAL_HOTKEY


class _CaptureWidget(OrganizerHotkeysMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.capture_target = None
        self.click_button = Mock()
        self.double_click_button = Mock()
        self.stop_script_hotkey_button = Mock()
        self.radial_hotkey_button = Mock()
        self.profiles = {}
        self.ensure_radial_participants = Mock()
        self.save_profiles = Mock()
        self.export_client_index = Mock()
        self.reload_runtime_callback = Mock()
        self.update_global_buttons = Mock()
        self.render_sessions = Mock()
        self.status_callback = Mock()


class OrganizerHotkeyCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_radial_button_captures_a_real_configurable_shortcut(self) -> None:
        widget = _CaptureWidget()
        try:
            with (
                patch("app.pages.organizer.organizer_hotkeys.QTimer"),
                patch("app.pages.organizer.organizer_hotkeys.key_sequence_to_hotkey",
                      return_value="F6"),
            ):
                widget.begin_capture("radial")
                event = Mock()
                event.key.return_value = Qt.Key_F6
                event.modifiers.return_value = Qt.NoModifier
                widget.keyPressEvent(event)
                self.assertEqual(widget.profiles[KEY_RADIAL_HOTKEY], "F6")
                widget.ensure_radial_participants.assert_called_once_with()
                widget.save_profiles.assert_called_once()
                widget.reload_runtime_callback.assert_called_once()
        finally:
            widget.close()
            widget.deleteLater()

    def test_radial_shortcut_rejects_collision_with_switch_click(self) -> None:
        widget = _CaptureWidget()
        widget.profiles[KEY_CLICK_HOTKEY] = "F6"
        try:
            with (
                patch("app.pages.organizer.organizer_hotkeys.QTimer"),
                patch("app.pages.organizer.organizer_hotkeys.key_sequence_to_hotkey",
                      return_value="F6"),
            ):
                widget.begin_capture("radial")
                event = Mock()
                event.key.return_value = Qt.Key_F6
                event.modifiers.return_value = Qt.NoModifier
                widget.keyPressEvent(event)
                self.assertNotIn(KEY_RADIAL_HOTKEY, widget.profiles)
                widget.save_profiles.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()

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
