from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.quest_catalog import QuestCatalog
from app.pages import home_page
from app.pages.home_page import GUIDE_ULTIME_LEGACY_ID, HomePage


class _FakeManualService:
    available = True

    def route_sheet_progress(self, _character_key: str) -> tuple[int, int]:
        return 3, 10

    def active_route_card(self, _character_key: str):
        return 3, {
            "manual_chapter_label": "Astrub",
            "manual_title": "Boucle Forêt et Égouts",
            "destination": "Astrub [5,-18]",
        }


class _FakeGuideProvider:
    def get_by_id(self, _guide_id: str):
        return None

    def load_all(self) -> list:
        return []


class HomeGuideUltimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_manual_progress_drives_home_and_drops_legacy_quest_target(self) -> None:
        page = HomePage()
        page.current_quest_id = 12345
        page._refresh_manual_guide_progress(_FakeManualService())

        self.assertEqual(page.current_guide_id, GUIDE_ULTIME_LEGACY_ID)
        self.assertIsNone(page.current_quest_id)
        self.assertEqual(page.progress_bar.value(), 30)
        self.assertEqual(page.progress_percent.text(), "30 %")
        self.assertEqual(page.chapter_value.text(), "Astrub")
        self.assertEqual(page.step_value.text(), "Boucle Forêt et Égouts")
        self.assertEqual(page.zone_value.text(), "Astrub [5,-18]")
        self.assertTrue(page.continue_button.isEnabled())
        page.deleteLater()

    def test_manual_home_progress_does_not_require_legacy_guide_provider(self) -> None:
        page = HomePage()
        # refresh_progress only needs a quest catalog for the canonical manual
        # route. The fake service prevents a rebuild, so no legacy GuideProvider
        # should be consulted on the primary path.
        page.catalog = object()
        page.guide_provider = None
        page.guide_ultime_service = _FakeManualService()

        page.refresh_progress()

        self.assertEqual(page.current_guide_id, GUIDE_ULTIME_LEGACY_ID)
        self.assertEqual(page.progress_bar.value(), 30)
        self.assertEqual(page.chapter_value.text(), "Astrub")
        self.assertEqual(page.step_value.text(), "Boucle Forêt et Égouts")
        self.assertTrue(page.continue_button.isEnabled())
        page.deleteLater()

    def test_home_does_not_build_manual_runtime_before_explicit_authorization(self) -> None:
        page = HomePage()
        page.catalog = QuestCatalog([])

        with patch("app.pages.home_page.QuestProvider") as quest_provider:
            page._rebuild_guide_ultime_service()

        quest_provider.assert_not_called()
        self.assertIsNone(page.guide_ultime_service)
        self.assertEqual(
            page.guide_ultime_error,
            "Ouvrez Guide pour charger la progression détaillée.",
        )
        page.deleteLater()

    def test_allow_manual_runtime_builds_real_service_then_refreshes(self) -> None:
        page = HomePage()
        page.catalog = QuestCatalog([])
        service = object()

        with (
            patch("app.pages.home_page.QuestProvider") as quest_provider,
            patch(
                "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service."
                "GuideUltimeManualRuntimeService",
                return_value=service,
            ) as service_class,
            patch.object(page, "refresh_progress") as refresh_progress,
        ):
            page.allow_guide_ultime_runtime()

        quest_provider.assert_called_once_with(catalog=page.catalog)
        service_class.assert_called_once()
        self.assertIs(page.guide_ultime_service, service)
        refresh_progress.assert_called_once_with()
        page.deleteLater()

    def test_authorization_without_catalog_does_not_build_runtime(self) -> None:
        page = HomePage()

        with (
            patch("app.pages.home_page.QuestProvider") as quest_provider,
            patch.object(page, "refresh_progress") as refresh_progress,
        ):
            page.allow_guide_ultime_runtime()

        quest_provider.assert_not_called()
        self.assertIsNone(page.guide_ultime_service)
        refresh_progress.assert_called_once_with()
        page.deleteLater()

    def test_rich_progress_does_not_write_a_secondary_home_cache(self) -> None:
        page = HomePage()
        page.character_key = "character:7"
        page.catalog = object()
        page.guide_provider = _FakeGuideProvider()
        page.guide_ultime_service = _FakeManualService()

        with patch("pathlib.Path.write_text") as write_text:
            page.refresh_progress()

        write_text.assert_not_called()
        self.assertEqual(page.progress_bar.value(), 30)
        page.deleteLater()

    def test_cold_manifest_read_is_small_and_cached_once(self) -> None:
        self.assertLessEqual(home_page._MANUAL_ROUTE_MANIFEST_PATH.stat().st_size, 64 * 1024)
        manifest = Mock()
        manifest.read_text.return_value = '{"canonical":{"chapters":[{"stage_count":3}]}}'
        home_page._manual_route_stage_total.cache_clear()
        with patch.object(home_page, "_MANUAL_ROUTE_MANIFEST_PATH", manifest):
            self.assertEqual(home_page._manual_route_stage_total(), 3)
            self.assertEqual(home_page._manual_route_stage_total(), 3)
        manifest.read_text.assert_called_once_with(encoding="utf-8")
        home_page._manual_route_stage_total.cache_clear()


if __name__ == "__main__":
    unittest.main()
