"""Exact-name Qt tests for Organizer visual host, not the macro/Zaap engine."""
from __future__ import annotations

import inspect
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from app.pages.organizer.organizer_ui import (
    CharacterSlotsPanel, OrganizerModeSwitch, OrganizerSpeedSelector, OrganizerUiMixin,
)
from app.pages.organizer.organizer_drag_drop import OrganizerDragDropMixin
from app.ui.unity_palette import UNITY_ORGANIZER_METRICS_PX


class OrganizerUiSharedStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_organizer_two_scroll_areas_share_native_qt_defaults(self):
        source = inspect.getsource(OrganizerUiMixin.build_organizer_ui)
        self.assertEqual(source.count("configure_unity_scroll_area("), 2)
        self.assertNotIn("setHorizontalScrollBarPolicy(", source)
        self.assertNotIn("setWidgetResizable(", source)
        self.assertIn('setObjectName("OrganizerZaapViewport")', source)

    def test_speed_and_mode_share_the_same_slider_geometry(self):
        speed = OrganizerSpeedSelector(
            QPushButton("Normal"), QPushButton("Rapide"), QPushButton("Instant"),
        )
        mode = OrganizerModeSwitch(QPushButton("Macro"), QPushButton("Miroir"))
        try:
            self.assertIn("_position_organizer_highlight(",
                          inspect.getsource(OrganizerSpeedSelector._position_highlight))
            self.assertIn("_position_organizer_highlight(",
                          inspect.getsource(OrganizerModeSwitch._sync_highlight))
            speed.resize(480, speed.height())
            speed.show()
            mode.show()
            self.app.processEvents()
            speed.set_selected("rapide")
            mode.set_selected(True, armed=False)
            self.app.processEvents()
            self.assertEqual(speed.highlight.pos(), speed._choices[1].pos())
            self.assertEqual(mode.highlight.pos(), mode._choices[1].pos())
            self.assertEqual(speed._motion.duration(), 145)
            self.assertEqual(mode._animation.duration(), 155)
        finally:
            speed.close()
            mode.close()
            speed.deleteLater()
            mode.deleteLater()

    def test_repeated_selected_state_does_not_restart_slider_animation(self):
        speed = OrganizerSpeedSelector(QPushButton("Normal"), QPushButton("Rapide"), QPushButton("Instant"))
        mode = OrganizerModeSwitch(QPushButton("Macro"), QPushButton("Miroir"))
        try:
            speed.show()
            mode.show()
            self.app.processEvents()
            speed.set_selected("normal")
            mode.set_selected(False)
            with patch.object(speed, "_position_highlight", wraps=speed._position_highlight) as move_speed, \
                 patch.object(mode, "_sync_highlight", wraps=mode._sync_highlight) as move_mode:
                speed.set_selected("rapide")
                mode.set_selected(True)
                speed.set_selected("rapide")
                mode.set_selected(True, armed=True)
                move_speed.assert_called_once_with(animated=True)
                move_mode.assert_called_once_with(animate=True)
                self.assertEqual(mode.highlight.objectName(), "OrganizerModeHighlightArmed")
        finally:
            speed.close()
            mode.close()
            speed.deleteLater()
            mode.deleteLater()

    def test_static_organizer_icons_reuse_bounded_pixmaps(self):
        from app.pages.organizer.organizer_ui import _organizer_grip_icon, _organizer_favorite_icon
        self.assertEqual(_organizer_grip_icon().cacheKey(), _organizer_grip_icon().cacheKey())
        self.assertEqual(_organizer_favorite_icon(True).cacheKey(), _organizer_favorite_icon(True).cacheKey())
        self.assertNotEqual(_organizer_favorite_icon(True).cacheKey(), _organizer_favorite_icon(False).cacheKey())

    def test_drag_row_repolishes_only_when_visual_role_changes(self):
        row = QWidget()
        try:
            with patch("app.ui.components.refresh_unity_widget_style") as refresh:
                OrganizerDragDropMixin.set_session_row_state(None, row, "characterSlot")
                OrganizerDragDropMixin.set_session_row_state(None, row, "characterSlot")
                self.assertEqual(refresh.call_count, 1)
                OrganizerDragDropMixin.set_session_row_state(None, row, "characterSlotDragging")
                self.assertEqual(refresh.call_count, 2)
                self.assertEqual(row.objectName(), "characterSlotDragging")
        finally:
            row.deleteLater()

    def test_mode_switch_repolishes_only_on_real_role_change(self):
        switch = OrganizerModeSwitch(QPushButton("Macro"), QPushButton("Miroir"))
        try:
            with patch("app.ui.components.refresh_unity_widget_style") as refresh:
                switch.set_selected(mirror=True, armed=True)
                switch.set_selected(mirror=True, armed=True)
                self.assertEqual(refresh.call_count, 1)
                switch.set_selected(mirror=False)
                self.assertEqual(refresh.call_count, 2)
        finally:
            switch.deleteLater()

    def test_mode_switch_reuses_style_when_the_role_changes(self):
        switch = OrganizerModeSwitch(QPushButton("Macro"), QPushButton("Miroir"))
        try:
            switch.set_selected(mirror=True, armed=True)
            self.assertEqual(switch.highlight.objectName(), "OrganizerModeHighlightArmed")
            switch.set_selected(mirror=False)
            self.assertEqual(switch.highlight.objectName(), "OrganizerModeHighlight")
        finally:
            switch.deleteLater()

    def test_mode_switch_and_slot_grid_use_shared_dev_ui_dimensions(self):
        metrics = UNITY_ORGANIZER_METRICS_PX
        switch = OrganizerModeSwitch(QPushButton("Macro"), QPushButton("Miroir"))
        refresh = QPushButton("Actualiser")
        slots = CharacterSlotsPanel(refresh)
        try:
            self.assertEqual(switch.minimumWidth(), metrics["mode_switch_width"])
            self.assertEqual(switch.maximumWidth(), metrics["mode_switch_width"])
            self.assertEqual(switch.minimumHeight(), metrics["button_height"])
            self.assertEqual(slots.grid.horizontalSpacing(),
                             metrics["slot_horizontal_spacing"])
            self.assertEqual(slots.grid.verticalSpacing(),
                             metrics["slot_vertical_spacing"])
        finally:
            switch.deleteLater()
            slots.deleteLater()

    def test_character_slot_cleanup_preserves_qt_parent_and_grid_geometry(self):
        panel = CharacterSlotsPanel(QPushButton("Actualiser"))
        slot = QWidget()
        try:
            panel.add_slot(slot, 0)
            self.assertEqual(panel.grid.count(), 1)
            self.assertIs(slot.parent(), panel.content)
            panel.clear_slots()
            self.assertEqual(panel.grid.count(), 0)
            self.assertIs(slot.parent(), panel.content)
            self.assertEqual(panel.slot_count, 8)
            self.assertEqual(panel.grid.horizontalSpacing(), UNITY_ORGANIZER_METRICS_PX["slot_horizontal_spacing"])
        finally:
            panel.deleteLater()

    def test_character_panel_inherits_transparent_host_without_local_qss(self):
        events = []
        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(lambda: events.append("refresh"))
        panel = CharacterSlotsPanel(refresh)
        try:
            panel.resize(440, panel.height())
            panel.show()
            self.app.processEvents()
            self.assertEqual(panel.content.objectName(), "OrganizerTransparentHost")
            self.assertEqual(panel.content.styleSheet(), "")
            self.assertTrue(refresh.isVisible())
            QTest.mouseClick(refresh, Qt.LeftButton)
            self.assertEqual(events, ["refresh"])
        finally:
            panel.close()
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
