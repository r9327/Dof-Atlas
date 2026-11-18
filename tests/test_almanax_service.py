"""Sourced Almanax data and visible calendar/Home interactions."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from time import time
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from app.services.almanax_service import (
    AlmanaxDataService, AlmanaxDay, parse_almanax_day,
)


def _source_day(key: str = "2026-11-18") -> dict:
    # Synthetic fixture matching documented Dofusdude Dofus 3 API fields.
    # No assertion below claims these are actual Dofus offerings/bonuses.
    return {
        "date": key,
        "tribute": {
            "item": {
                "name": "Objet de test",
                "image_urls": {"icon": "https://api.dofusdu.de/dofus3/v1/img/item/test-64.png"},
            },
            "quantity": 5,
        },
        "reward_kamas": 2500,
        "bonus": {
            "description": "Bonus de test.",
            "type": {"name": "Catégorie de test"},
        },
    }


class AlmanaxSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parse_real_dofus3_schema(self):
        day = parse_almanax_day(_source_day(), "2026-11-18")
        self.assertEqual(
            day,
            AlmanaxDay(
                "2026-11-18", "Objet de test", 5,
                "Bonus de test.", "Catégorie de test",
                reward_kamas=2500, item_icon_url="https://api.dofusdu.de/dofus3/v1/img/item/test-64.png",
            ),
        )

    def test_never_invent_offering_on_wrong_or_empty_source(self):
        self.assertIsNone(parse_almanax_day(_source_day(), "2026-11-19"))
        self.assertIsNone(parse_almanax_day({"date": "2026-11-18"}, "2026-11-18"))
        self.assertIsNone(parse_almanax_day([], "2026-11-18"))
        self.assertIsNone(parse_almanax_day(_source_day(), "invalid-day"))
        partial = _source_day()
        del partial["tribute"]
        day = parse_almanax_day(partial, "2026-11-18")
        self.assertEqual(day.offering, "")
        self.assertEqual(day.quantity, 0)
        self.assertEqual(day.bonus, "Bonus de test.")

    def test_offline_cache_survives_service_recreation_and_skips_http(self):
        with tempfile.TemporaryDirectory() as folder:
            cache_path = Path(folder) / "almanax.json"
            first = AlmanaxDataService(cache_path=cache_path)
            day = parse_almanax_day(_source_day(), "2026-11-18")
            first._cache[day.date] = (day, time())
            first._persist_cache()
            second = AlmanaxDataService(cache_path=cache_path)
            seen = []
            second.dayAvailable.connect(
                lambda key, value, cached: seen.append((key, value, cached))
            )
            try:
                from unittest.mock import patch

                with patch.object(second, "_request_item_icon") as image_request:
                    self.assertTrue(second.request_day("2026-11-18"))
                    image_request.assert_called_once_with(day)
                self.assertEqual(seen, [("2026-11-18", day, True)])
                self.assertEqual(second._pending, {})
                self.assertFalse(second.request_day("not-a-day"))
            finally:
                first.deleteLater()
                second.deleteLater()
                self.app.processEvents()


class AlmanaxUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_home_card_displays_sourced_offering_and_cache_provenance(self):
        from app.pages.home_page import HomePage

        page = HomePage()
        day = AlmanaxDay(
            "2026-11-18", "Objet de test", 5,
            "Bonus de test.", "Catégorie de test",
        )
        try:
            page.set_almanax_day(day)
            self.assertIn("5 × Objet de test", page.almanax_text.text())
            self.assertIn("Bonus de test.", page.almanax_text.text())
            self.assertIn("Dofusdude", page.almanax_badge.text())
            page.set_almanax_day(day, cached=True)
            self.assertIn("cache", page.almanax_badge.text())
            page.set_almanax_unavailable("2026-11-18")
            self.assertIn("5 × Objet de test", page.almanax_text.text())
            page.set_almanax_loading("2026-11-19")
            self.assertNotIn("Objet de test", page.almanax_text.text())
            page.set_almanax_unavailable("2026-11-19")
            self.assertIn("Données indisponibles", page.almanax_badge.text())
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_calendar_selects_future_date_and_offers_manual_refresh(self):
        from main import AtlasWindow

        shell = Mock()
        page = AtlasWindow.create_almanax_page(shell)
        try:
            selected = shell.almanax_calendar.selectedDate()
            shell._request_almanax_day.assert_called_with(
                selected.toString("yyyy-MM-dd")
            )
            shell._request_almanax_day.reset_mock()
            shell.almanax_calendar.setSelectedDate(QDate(2026, 12, 1))
            self.app.processEvents()
            shell._request_almanax_day.assert_called_with("2026-12-01")
            shell._request_almanax_day.reset_mock()
            # The button itself is the common AtlasButton, never local QSS.
            from app.ui.components import AtlasButton

            button = page.findChild(AtlasButton, "AlmanaxRefreshButton")
            self.assertIsNotNone(button)
            button.click()
            shell._request_almanax_day.assert_called_once_with(
                "2026-12-01", refresh=True,
            )
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_late_day_response_cannot_replace_other_selected_date(self):
        from main import AtlasWindow

        shell = Mock()
        shell.quit_requested = False
        page = AtlasWindow.create_almanax_page(shell)
        day = AlmanaxDay(
            "2026-11-18", "Objet", 3, "Bonus réel de test", "Divers",
        )
        try:
            shell.almanax_calendar.setSelectedDate(QDate(2026, 12, 1))
            before = shell.almanax_day_detail.text()
            AtlasWindow._on_almanax_day_available(shell, "2026-11-18", day, False)
            self.assertEqual(shell.almanax_day_detail.text(), before)
            # A delayed response for today can still update today's Home.
            if QDate.currentDate() == QDate(2026, 11, 18):
                shell.home_page.set_almanax_day.assert_called_once_with(
                    day, cached=False,
                )
        finally:
            page.deleteLater()
            self.app.processEvents()
