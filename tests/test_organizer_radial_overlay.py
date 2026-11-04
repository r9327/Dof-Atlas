from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from app.constants import (
    KEY_RADIAL_ENABLED, KEY_RADIAL_EXCLUDED, KEY_RADIAL_HOTKEY,
    KEY_RADIAL_PARTICIPANTS,
)
from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
from app.pages.organizer.character_sessions import CharacterSessionsMixin
from app.pages.organizer_page import OrganizerPage
from app.pages.organizer.radial_overlay import (
    OrganizerRadialHoldController,
    OrganizerRadialOverlay,
    physical_key_held,
)


class _Overlay:
    def __init__(self, selection: int | None = None):
        self.visible = False
        self.opens = []
        self.finishes = []
        self.selection = selection
        self.tracked = 0

    def isVisible(self):
        return self.visible

    def hide(self):
        self.visible = False

    def open_for(self, rows):
        self.opens.append(list(rows))
        self.visible = bool(rows)
        return self.visible

    def track_cursor(self):
        self.tracked += 1

    def finish(self, rows, *, cancel=False):
        self.visible = False
        self.finishes.append((list(rows), cancel))
        return None if cancel else self.selection


class OrganizerRadialOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_popup_is_centered_on_screen_not_cursor(self):
        overlay = OrganizerRadialOverlay()
        try:
            with patch("app.pages.organizer.radial_overlay.class_icon_path_for_window_name",
                       return_value=None):
                self.assertTrue(overlay.open_for([{"nom": "Pandawa", "hwnd": 101}]))
            from PySide6.QtGui import QCursor
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            self.assertLessEqual(abs(overlay.geometry().center().x() -
                                     screen.geometry().center().x()), 1)
            self.assertLessEqual(abs(overlay.geometry().center().y() -
                                     screen.geometry().center().y()), 1)
            self.assertTrue(bool(overlay.windowFlags() &
                                 Qt.WindowDoesNotAcceptFocus))
        finally:
            overlay.hide()
            overlay.deleteLater()

    def test_real_overlay_always_closes_even_without_mouse_movement(self):
        overlay = OrganizerRadialOverlay()
        try:
            with patch("app.pages.organizer.radial_overlay.class_icon_path_for_window_name",
                       return_value=None):
                self.assertTrue(overlay.open_for([{"nom": "Panda", "hwnd": 101}]))
            self.assertIsNone(overlay.finish([{"nom": "Panda", "hwnd": 101}]))
            self.assertFalse(overlay.isVisible())
        finally:
            overlay.hide()
            overlay.deleteLater()

    def test_explicit_center_movement_returns_atlas_without_character_handle(self):
        from PySide6.QtCore import QPoint

        overlay = OrganizerRadialOverlay()
        rows = [{"nom": "Panda", "hwnd": 101, "pid": 15}]
        try:
            with patch("app.pages.organizer.radial_overlay.class_icon_path_for_window_name",
                       return_value=None):
                self.assertTrue(overlay.open_for(rows))
            center = overlay.geometry().center()
            overlay._start_cursor = QPoint(center.x() + 100, center.y() + 100)
            with patch("app.pages.organizer.radial_overlay.QCursor") as cursor:
                cursor.pos.return_value = center
                overlay.track_cursor()
            self.assertTrue(overlay._center_hovered)
            self.assertEqual(overlay.finish(rows), 0)
            self.assertFalse(overlay._center_hovered)
            self.assertFalse(overlay.isVisible())
        finally:
            overlay.hide()
            overlay.deleteLater()

    def test_center_without_explicit_movement_never_opens_atlas(self):
        overlay = OrganizerRadialOverlay()
        rows = [{"nom": "Panda", "hwnd": 101}]
        try:
            with patch("app.pages.organizer.radial_overlay.class_icon_path_for_window_name",
                       return_value=None):
                self.assertTrue(overlay.open_for(rows))
            center = overlay.geometry().center()
            overlay._start_cursor = center
            with patch("app.pages.organizer.radial_overlay.QCursor") as cursor:
                cursor.pos.return_value = center
                overlay.track_cursor()
            self.assertFalse(overlay._center_hovered)
            self.assertIsNone(overlay.finish(rows))
        finally:
            overlay.hide()
            overlay.deleteLater()

    def test_escape_cancels_center_selection_even_if_center_hovered(self):
        overlay = OrganizerRadialOverlay()
        rows = [{"nom": "Panda", "hwnd": 101}]
        try:
            with patch("app.pages.organizer.radial_overlay.class_icon_path_for_window_name",
                       return_value=None):
                self.assertTrue(overlay.open_for(rows))
            overlay._center_hovered = True
            self.assertIsNone(overlay.finish(rows, cancel=True))
            self.assertFalse(overlay.isVisible())
        finally:
            overlay.hide()
            overlay.deleteLater()

    def test_atlas_center_logo_is_loaded_once_for_repeated_opening(self):
        overlay = OrganizerRadialOverlay()
        rows = [{"nom": "Panda", "hwnd": 101}]
        try:
            with patch("app.pages.organizer.radial_overlay.class_icon_path_for_window_name",
                       return_value=None):
                self.assertTrue(overlay.open_for(rows))
                cached = overlay._atlas_logo
                self.assertIsNotNone(cached)
                overlay.finish(rows)
                self.assertTrue(overlay.open_for(rows))
                self.assertIs(overlay._atlas_logo, cached)
        finally:
            overlay.hide()
            overlay.deleteLater()

    def test_existing_atlas_window_is_activated_from_center_without_win32(self):
        page = Mock()
        parent = Mock()
        page.window.return_value = parent
        with (
            patch("app.windows.unity_windows.is_unity_window") as unity,
            patch("app.windows.focus.activate_window") as focus,
        ):
            OrganizerPage._activate_radial_handle(page, 0)
        parent.showNormal.assert_called_once()
        parent.raise_.assert_called_once()
        parent.activateWindow.assert_called_once()
        page.status_callback.assert_called_once()
        unity.assert_not_called()
        focus.assert_not_called()

    def test_wheel_controller_dispatches_center_sentinel_just_once(self):
        overlay = _Overlay(selection=0)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        try:
            controller.poll()
            pressed[0] = False
            controller.poll()
            controller.poll()
            self.assertEqual(launched, [0])
            self.assertFalse(overlay.visible)
        finally:
            parent.deleteLater()

    def test_rebinding_while_hotkey_held_requires_release_before_open(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        try:
            self.assertTrue(controller.set_shortcut("F6"))
            controller.poll()
            self.assertFalse(overlay.visible)
            pressed[0] = False
            controller.poll()
            pressed[0] = True
            controller.poll()
            self.assertTrue(overlay.visible)
        finally:
            parent.deleteLater()

    def test_no_win32_poll_during_offscreen_test(self):
        self.assertFalse(physical_key_held(frozenset({0x70})))

    def _controller(self, overlay, pressed, allow=True):
        widget = QWidget()
        launched = []
        controller = OrganizerRadialHoldController(
            overlay,
            lambda: [{"nom": "Panda", "hwnd": 101}],
            launched.append,
            parent=widget,
            key_reader=lambda _keys: pressed[0],
            can_open=lambda: allow,
        )
        controller._timer.stop()
        controller.keys = frozenset({0x70})
        return widget, controller, launched

    def test_hold_shows_and_release_always_closes_with_no_selection(self):
        overlay = _Overlay(selection=None)
        state = [False]
        parent, controller, launched = self._controller(overlay, state)
        try:
            state[0] = True
            controller.poll()
            self.assertTrue(overlay.visible)
            self.assertEqual(len(overlay.opens), 1)
            controller.poll()
            self.assertEqual(overlay.tracked, 1)
            state[0] = False
            controller.poll()
            self.assertFalse(overlay.visible)
            self.assertEqual(len(overlay.finishes), 1)
            self.assertEqual(launched, [])
        finally:
            parent.deleteLater()

    def test_release_after_explicit_selection_activates_only_once(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        try:
            controller.poll()
            pressed[0] = False
            controller.poll()
            controller.poll()
            self.assertFalse(overlay.visible)
            self.assertEqual(launched, [101])
        finally:
            parent.deleteLater()

    def test_external_focus_loss_while_held_disarms_until_release(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        focus = [True]
        controller.can_open = lambda: focus[0]
        try:
            controller.poll()
            self.assertTrue(overlay.visible)
            focus[0] = False
            controller.poll()
            self.assertFalse(overlay.visible)
            focus[0] = True
            controller.poll()
            self.assertEqual(len(overlay.opens), 1)
            pressed[0] = False
            controller.poll()
            self.assertEqual(launched, [])
        finally:
            parent.deleteLater()

    def test_focus_loss_only_at_release_never_reactivates_game(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        focus = [True]
        controller.can_open = lambda: focus[0]
        try:
            controller.poll()
            self.assertTrue(overlay.visible)
            focus[0] = False
            pressed[0] = False  # no intermediate key-down poll
            controller.poll()
            self.assertFalse(overlay.visible)
            self.assertEqual(launched, [])
            self.assertTrue(overlay.finishes[-1][1])
        finally:
            parent.deleteLater()

    def test_capture_cancel_does_not_reopen_until_release(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        try:
            controller.poll()
            controller.cancel()
            controller.poll()
            self.assertFalse(overlay.visible)
            self.assertEqual(len(overlay.opens), 1)
            pressed[0] = False
            controller.poll()
            self.assertEqual(launched, [])
        finally:
            parent.deleteLater()

    def test_escape_closes_and_releasing_does_not_activate(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed)
        try:
            controller.poll()
            self.assertTrue(overlay.visible)
            with patch("app.pages.organizer.radial_overlay.escape_pressed", return_value=True):
                controller.poll()
            self.assertFalse(overlay.visible)
            controller.poll()  # Still holding the shortcut: must not reopen.
            self.assertEqual(len(overlay.opens), 1)
            pressed[0] = False
            controller.poll()
            self.assertEqual(launched, [])
        finally:
            parent.deleteLater()

    def test_shortcut_pressed_outside_dofus_does_not_open(self):
        overlay = _Overlay(selection=101)
        pressed = [True]
        parent, controller, launched = self._controller(overlay, pressed, allow=False)
        try:
            controller.poll()
            self.assertFalse(overlay.visible)
            pressed[0] = False
            controller.poll()
            self.assertEqual(launched, [])
        finally:
            parent.deleteLater()


class OrganizerRadialRosterTests(unittest.TestCase):
    def test_new_dofus_detection_does_not_auto_add_radial_part(self):
        page = Mock()
        page.profiles = {}
        page.sessions = [
            {"nom": "Panda", "hwnd": 101, "pid": 1001},
            {"nom": "Enu", "hwnd": 102, "pid": 1002},
        ]
        OrganizerPage.ensure_radial_participants(page)
        self.assertEqual(len(page.profiles[KEY_RADIAL_PARTICIPANTS]), 2)
        page.sessions.append({"nom": "Cra", "hwnd": 103, "pid": 1003})
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [101, 102],
        )

    def test_untracked_dofus_window_cannot_open_radial_picker(self):
        page = Mock()
        page.capture_target = None
        page.sessions = [{"nom": "Panda", "hwnd": 101, "pid": 1001}]
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=999),
        ):
            self.assertFalse(OrganizerPage._radial_can_open(page))
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
        ):
            self.assertTrue(OrganizerPage._radial_can_open(page))

    def test_new_detected_client_syncs_without_manual_slot_selection(self):
        page = Mock()
        page.profiles = {
            KEY_RADIAL_ENABLED: True,
            KEY_RADIAL_PARTICIPANTS: ["unverified:panda:1001"],
            KEY_RADIAL_EXCLUDED: [],
        }
        page.sessions = [
            {"nom": "Panda", "hwnd": 101, "pid": 1001},
            {"nom": "Enu", "hwnd": 202, "pid": 1002},
        ]
        self.assertTrue(OrganizerPage.sync_radial_participants(page))
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [101, 202],
        )
        page.save_profiles.assert_called_once()
        self.assertFalse(OrganizerPage.sync_radial_participants(page))
        page.save_profiles.assert_called_once()

    def test_manual_radial_exclusion_survives_refresh_and_new_windows(self):
        page = Mock()
        page.profiles = {
            KEY_RADIAL_ENABLED: True,
            KEY_RADIAL_PARTICIPANTS: [
                "unverified:panda:1001", "unverified:enu:1002",
            ],
        }
        page.sessions = [
            {"nom": "Panda", "hwnd": 101, "pid": 1001},
            {"nom": "Enu", "hwnd": 202, "pid": 1002},
        ]
        page.ensure_radial_participants = lambda: OrganizerPage.ensure_radial_participants(page)
        OrganizerPage.toggle_radial_session(page, page.sessions[1])
        self.assertEqual(
            page.profiles[KEY_RADIAL_EXCLUDED], ["unverified:enu:1002"],
        )
        page.sessions.append({"nom": "Éca", "hwnd": 303, "pid": 1003})
        self.assertTrue(OrganizerPage.sync_radial_participants(page))
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [101, 303],
        )
        self.assertFalse(OrganizerPage.sync_radial_participants(page))
        OrganizerPage.toggle_radial_session(page, page.sessions[1])
        self.assertEqual(page.profiles[KEY_RADIAL_EXCLUDED], [])
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [101, 202, 303],
        )

    def test_radial_sync_is_suspended_while_disabled_and_resumes_on_enable(self):
        page = Mock()
        page.profiles = {
            KEY_RADIAL_ENABLED: False,
            KEY_RADIAL_PARTICIPANTS: ["unverified:panda:1001"],
        }
        page.sessions = [
            {"nom": "Panda", "hwnd": 101, "pid": 1001},
            {"nom": "Éca", "hwnd": 303, "pid": 1003},
        ]
        self.assertFalse(OrganizerPage.sync_radial_participants(page))
        page.save_profiles.assert_not_called()
        page.profiles[KEY_RADIAL_ENABLED] = True
        self.assertTrue(OrganizerPage.sync_radial_participants(page))
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [101, 303],
        )

    def test_radial_sync_refuses_missing_or_corrupt_opt_in_profile(self):
        page = Mock()
        page.profiles = {KEY_RADIAL_ENABLED: True}
        page.sessions = [{"nom": "Panda", "hwnd": 101, "pid": 1001}]
        self.assertFalse(OrganizerPage.sync_radial_participants(page))
        page.profiles[KEY_RADIAL_PARTICIPANTS] = None
        self.assertFalse(OrganizerPage.sync_radial_participants(page))
        page.save_profiles.assert_not_called()

    def test_verified_radial_selection_follows_same_character_new_window(self):
        page = Mock()
        page.profiles = {
            KEY_RADIAL_ENABLED: True,
            KEY_RADIAL_PARTICIPANTS: ["character:42"],
        }
        page.sessions = [
            {"nom": "Panda", "hwnd": 501, "pid": 1005,
             "character_key": "character:42"},
        ]
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [501],
        )

    def test_disabled_radial_does_not_even_query_foreground(self):
        page = Mock()
        page.profiles = {KEY_RADIAL_ENABLED: False}
        page.capture_target = None
        with patch("app.windows.unity_windows.foreground_window") as focus:
            self.assertFalse(OrganizerPage._radial_can_open(page))
        focus.assert_not_called()

    def test_radial_enable_toggle_persists_and_does_not_restart_macros(self):
        page = Mock()
        page.profiles = {
            KEY_RADIAL_ENABLED: True,
            KEY_RADIAL_HOTKEY: "F6",
            KEY_RADIAL_PARTICIPANTS: ["unverified:panda:1001"],
        }
        page.hotkey_label = lambda key: page.profiles.get(key, "")
        page._radial_controller = Mock()
        OrganizerHotkeysMixin.toggle_radial_enabled(page)
        self.assertFalse(page.profiles[KEY_RADIAL_ENABLED])
        page._radial_controller.cancel.assert_called_once()
        page._radial_controller.set_shortcut.assert_called_once_with("")
        page.reload_runtime_callback.assert_not_called()
        OrganizerHotkeysMixin.toggle_radial_enabled(page)
        self.assertTrue(page.profiles[KEY_RADIAL_ENABLED])
        page._radial_controller.set_shortcut.assert_called_with("F6")
        page.sync_radial_participants.assert_called_once_with(persist=False)
        self.assertEqual(page.save_profiles.call_count, 2)
        page.reload_runtime_callback.assert_not_called()

    def test_session_change_notification_syncs_radial_only_when_changed(self):
        page = Mock()
        page._last_notified_session_signature = None
        signature = ((1, "Panda", 101, 1001),)
        page.session_identity_signature.return_value = signature
        CharacterSessionsMixin.notify_sessions_changed(page)
        CharacterSessionsMixin.notify_sessions_changed(page)
        page.sync_radial_participants.assert_called_once()
        page.sessions_changed_callback.assert_called_once()

    def test_character_can_be_removed_from_radial_and_reenabled(self):
        page = Mock()
        page.profiles = {}
        page.sessions = [
            {"nom": "Panda", "hwnd": 101, "pid": 1001},
            {"nom": "Enu", "hwnd": 102, "pid": 1002},
        ]
        page.ensure_radial_participants = lambda: OrganizerPage.ensure_radial_participants(page)
        OrganizerPage.toggle_radial_session(page, page.sessions[0])
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [102],
        )
        page.save_profiles.assert_called_once()
        OrganizerPage.toggle_radial_session(page, page.sessions[0])
        self.assertEqual(
            [row["hwnd"] for row in OrganizerPage._radial_participants(page)],
            [101, 102],
        )


if __name__ == "__main__":
    unittest.main()
