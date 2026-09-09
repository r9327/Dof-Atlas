from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.quest_catalog import QuestCatalog
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

    def test_rich_progress_is_saved_for_the_next_cold_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_path = root / "home-progress.json"
            quest_path = root / "quest-progress.json"
            achievement_path = root / "achievement-progress.json"
            guide_path = root / "guide-progress.json"
            for path in (quest_path, achievement_path, guide_path):
                path.write_text("{}", encoding="utf-8")

            page = HomePage()
            page.character_key = "character:7"
            page.catalog = object()
            page.guide_provider = _FakeGuideProvider()
            page.guide_ultime_service = _FakeManualService()

            with (
                patch("app.pages.home_page._HOME_PROGRESS_CACHE_PATH", cache_path),
                patch("app.pages.home_page.GUIDE_PROGRESS_FILE", guide_path),
                patch("app.constants.QUEST_PROGRESS_FILE", quest_path),
                patch(
                    "app.modules.encyclopedia.services.ACHIEVEMENT_PROGRESS_FILE",
                    achievement_path,
                ),
            ):
                page.refresh_progress()

            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            row = payload["characters"]["character:7"]
            self.assertEqual(row["percent"], 30)
            self.assertEqual(row["chapter"], "Astrub")
            self.assertEqual(row["step"], "Boucle Forêt et Égouts")
            self.assertEqual(row["zone"], "Astrub [5,-18]")
            self.assertEqual(len(row["progress_signature"]), 3)
            page.deleteLater()


if __name__ == "__main__":
    unittest.main()
