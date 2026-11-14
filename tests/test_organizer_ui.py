"""Exact-name Qt tests for Organizer visual host, not the macro/Zaap engine."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from app.pages.organizer.organizer_ui import CharacterSlotsPanel


class OrganizerUiSharedStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
