from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QWidget

from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
from app.constants import (
    KEY_CLICK_HOTKEY, KEY_RADIAL_HOTKEY, KEY_RADIAL_ENABLED,
    KEY_STOP_SCRIPT_HOTKEY,
)
from app.pages.organizer.common import client_slot_hotkey_key
from app.input.hotkeys import build_hotkey_actions


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

    def test_client_capture_rejects_invalid_slot_without_rebinding_another_character(self) -> None:
        for bad_slot in (None, True, False, -1, 8, 1.9, "1", object()):
            with self.subTest(slot=repr(bad_slot)):
                widget = _CaptureWidget()
                try:
                    with (
                        patch("app.pages.organizer.organizer_hotkeys.QTimer"),
                        patch("app.pages.organizer.organizer_hotkeys.key_sequence_to_hotkey",
                              return_value="F6"),
                    ):
                        widget.begin_capture("client", slot=bad_slot)
                        event = Mock()
                        event.key.return_value = Qt.Key_F6
                        event.modifiers.return_value = Qt.NoModifier
                        widget.keyPressEvent(event)
                    self.assertEqual(widget.profiles, {})
                    widget.save_profiles.assert_not_called()
                    widget.reload_runtime_callback.assert_not_called()
                    self.assertIn("slot personnage invalide",
                                  widget.status_callback.call_args.args[0])
                finally:
                    widget.close()
                    widget.deleteLater()

    def test_client_capture_accepts_eighth_slot_without_rebinding_first(self) -> None:
        widget = _CaptureWidget()
        try:
            with (
                patch("app.pages.organizer.organizer_hotkeys.QTimer"),
                patch("app.pages.organizer.organizer_hotkeys.key_sequence_to_hotkey",
                      return_value="F6"),
            ):
                widget.begin_capture("client", slot=7)
                event = Mock()
                event.key.return_value = Qt.Key_F6
                event.modifiers.return_value = Qt.NoModifier
                widget.keyPressEvent(event)
            self.assertEqual(widget.profiles.get(client_slot_hotkey_key(7)), "F6")
            self.assertNotIn(client_slot_hotkey_key(0), widget.profiles)
            widget.save_profiles.assert_called_once()
        finally:
            widget.close()
            widget.deleteLater()

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

    def test_radial_hotkey_remains_disabled_when_configured_while_off(self):
        widget = _CaptureWidget()
        widget.profiles[KEY_RADIAL_ENABLED] = False
        widget._radial_controller = Mock()
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
            self.assertFalse(widget.profiles[KEY_RADIAL_ENABLED])
            widget._radial_controller.set_shortcut.assert_called_once_with("")
            widget.save_profiles.assert_called_once()
        finally:
            widget.close()
            widget.deleteLater()

    def test_shared_radial_and_slot_key_is_valid_in_both_capture_orders(self):
        for first in ("radial", "client"):
            with self.subTest(first=first):
                widget = _CaptureWidget()
                widget.profiles.update({
                    KEY_RADIAL_ENABLED: True,
                    KEY_RADIAL_HOTKEY: "F6" if first == "client" else "",
                    client_slot_hotkey_key(0): "F6" if first == "radial" else "",
                })
                try:
                    with (
                        patch("app.pages.organizer.organizer_hotkeys.QTimer"),
                        patch("app.pages.organizer.organizer_hotkeys.key_sequence_to_hotkey",
                              return_value="F6"),
                    ):
                        widget.begin_capture(first, slot=0 if first == "client" else None)
                        event = Mock()
                        event.key.return_value = Qt.Key_F6
                        event.modifiers.return_value = Qt.NoModifier
                        widget.keyPressEvent(event)
                    self.assertEqual(widget.profiles[KEY_RADIAL_HOTKEY], "F6")
                    self.assertEqual(widget.profiles[client_slot_hotkey_key(0)], "F6")
                    self.assertIn("prioritaire", widget.status_callback.call_args.args[0])
                    widget.save_profiles.assert_called_once()
                finally:
                    widget.close()
                    widget.deleteLater()

    def test_stop_priority_never_allows_same_radial_hotkey(self):
        widget = _CaptureWidget()
        widget.profiles.update({
            KEY_STOP_SCRIPT_HOTKEY: "F6",
            client_slot_hotkey_key(0): "F6",
        })
        try:
            with (
                patch("app.pages.organizer.organizer_hotkeys.QTimer"),
                patch("app.pages.organizer.organizer_hotkeys.key_sequence_to_hotkey",
                      return_value="F6"),
            ):
                widget.begin_capture("radial")
                event = Mock()
                event.key.return_value = Qt.Key_F6
                widget.keyPressEvent(event)
            self.assertNotIn(KEY_RADIAL_HOTKEY, widget.profiles)
            widget.save_profiles.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()

    def test_registered_slot_actions_follow_radial_priority_2_4_6_8(self):
        for count in (2, 4, 6, 8):
            for wheel_enabled in (False, True):
                with self.subTest(clients=count, wheel=wheel_enabled):
                    clients = [
                        SimpleNamespace(
                            index=i, handle=100 + i,
                            binding="F6" if i == 1 else f"F{6+i}",
                        )
                        for i in range(1, count + 1)
                    ]
                    settings = SimpleNamespace(
                        macro_mode="macro", clients=clients,
                        radial_hotkey="F6", radial_enabled=wheel_enabled,
                        switch_character_enabled=True,
                        switch_click_enabled=False, switch_click_hotkey="",
                        switch_double_click_enabled=False, switch_double_click_hotkey="",
                        movement_enabled=False, stop_hotkey="",
                        next_character_hotkey="",
                    )
                    actions = build_hotkey_actions(settings)
                    slot_actions = [
                        action for action in actions
                        if action.action_id.startswith("client:")
                    ]
                    self.assertEqual(len(slot_actions), count - int(wheel_enabled))
                    self.assertEqual(
                        sum(a.hotkey_text == "F6" for a in slot_actions),
                        0 if wheel_enabled else 1,
                    )

    def test_shared_slot_toggle_rebuilds_runtime_hotkeys_in_both_directions(self):
        from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin

        page = Mock()
        page.profiles = {
            KEY_RADIAL_HOTKEY: "F6",
            KEY_RADIAL_ENABLED: True,
            client_slot_hotkey_key(0): "F6",
            "__personnages_selection_camembert__": [],
        }
        page.hotkey_label = lambda key: str(page.profiles.get(key) or "")
        OrganizerHotkeysMixin.toggle_radial_enabled(page)
        self.assertFalse(page.profiles[KEY_RADIAL_ENABLED])
        page.reload_runtime_callback.assert_called_once()
        OrganizerHotkeysMixin.toggle_radial_enabled(page)
        self.assertTrue(page.profiles[KEY_RADIAL_ENABLED])
        self.assertEqual(page.reload_runtime_callback.call_count, 2)

    def test_load_settings_preserves_enabled_and_disabled_radial_keys(self):
        from app.core.settings import load_settings

        for wheel_enabled in (True, False):
            with self.subTest(enabled=wheel_enabled):
                with (
                    patch("app.core.settings.load_profile_payload", return_value={
                        KEY_RADIAL_HOTKEY: "F6", KEY_RADIAL_ENABLED: wheel_enabled,
                    }),
                    patch("app.core.settings.read_json_file",
                          return_value={"clients": []}),
                    patch("app.core.settings.read_zaap_button_ratios",
                          return_value=None),
                ):
                    settings = load_settings()
                self.assertEqual(settings.radial_hotkey, "F6")
                self.assertIs(settings.radial_enabled, wheel_enabled)

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
