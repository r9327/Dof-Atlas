from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

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


if __name__ == "__main__":
    unittest.main()
