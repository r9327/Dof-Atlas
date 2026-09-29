from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualView
from tests.test_guide_ultime_manual_ui_navigation import _FakeManualUiService


class GuideManualNavigationContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self) -> tuple[_FakeManualUiService, GuideUltimeManualView]:
        service = _FakeManualUiService()
        view = GuideUltimeManualView(service, character_key="character:1")
        view.resize(560, 320)
        view.show()
        QApplication.processEvents()
        return service, view

    def test_go_active_returns_to_first_incomplete_sheet(self) -> None:
        service, view = self._view()
        try:
            view.navigate_relative(1)
            QApplication.processEvents()
            self.assertEqual(view.view_index, 1)

            service.active_index = 0
            view.go_active()
            QApplication.processEvents()

            self.assertEqual(view.active_index, 0)
            self.assertEqual(view.view_index, 0)
            self.assertEqual(view.nav_page_label.text(), "Page 1 / 2")
        finally:
            view.close()

    def test_clicking_position_copies_travel_command(self) -> None:
        _service, view = self._view()
        try:
            labels = [
                label
                for label in view.findChildren(QLabel)
                if bool(label.property("travelCopyEnabled"))
                and str(label.property("travelCommand") or "").strip()
            ]
            self.assertTrue(labels)
            label = labels[0]
            expected = str(label.property("travelCommand"))
            self.assertTrue(expected.startswith("/travel "))

            QApplication.clipboard().clear()
            QTest.mouseClick(label, Qt.LeftButton)
            QApplication.processEvents()

            self.assertEqual(QApplication.clipboard().text(), expected)
            self.assertEqual(label.toolTip(), f"Copié : {expected}")
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
