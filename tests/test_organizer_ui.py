"""Exact-name Qt tests for Organizer visual host, not the macro/Zaap engine."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from app.pages.organizer.organizer_ui import CharacterSlotsPanel, OrganizerModeSwitch
from app.ui.unity_palette import UNITY_ORGANIZER_METRICS_PX


class OrganizerUiSharedStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
