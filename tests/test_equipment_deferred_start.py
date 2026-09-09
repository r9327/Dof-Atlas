from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.pages.equipment_page import EquipmentPage, WEBENGINE_START_DELAY_MS


class EquipmentDeferredStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_equipment_shell_is_navigation_ready_before_webengine(self) -> None:
        page = EquipmentPage(lambda _text: None)
        self.assertTrue(page.is_navigation_ready())
        self.assertFalse(page.web_loaded)
        self.assertFalse(page.web_unavailable)
        page.deleteLater()

    def test_webengine_start_is_deferred_after_page_can_paint(self) -> None:
        page = EquipmentPage(lambda _text: None)
        with patch("app.pages.equipment_page.QTimer.singleShot") as single_shot:
            page.schedule_web_start()
            single_shot.assert_called_once()
            delay_ms, callback = single_shot.call_args.args
            self.assertEqual(delay_ms, WEBENGINE_START_DELAY_MS)
            self.assertEqual(callback, page._start_scheduled_web)
            self.assertTrue(page._web_start_scheduled)
        page.deleteLater()

    def test_deferred_start_only_builds_webengine_while_visible(self) -> None:
        page = EquipmentPage(lambda _text: None)
        page._web_start_scheduled = True
        with patch.object(page, "isVisible", return_value=True), patch.object(
            page,
            "ensure_web_loaded",
        ) as ensure_web_loaded:
            page._start_scheduled_web()
            ensure_web_loaded.assert_called_once_with()
            self.assertFalse(page._web_start_scheduled)
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
