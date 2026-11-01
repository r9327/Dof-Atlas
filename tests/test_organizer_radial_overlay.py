from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from app.constants import KEY_RADIAL_PARTICIPANTS
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
