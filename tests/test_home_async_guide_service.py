from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.pages.home_optimized_page import HomePage as OptimizedHomePage
from app.quest_catalog import QuestCatalog


class _DeferredThread:
    created: list["_DeferredThread"] = []

    def __init__(self, *, target, name: str, daemon: bool) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.__class__.created.append(self)

    def start(self) -> None:
        self.started = True


class _FakeGuideService:
    def __init__(self, available: bool) -> None:
        self.available = bool(available)
        self.load_calls = 0
        self.cards = [
            {
                "manual_source": bool(available),
                "manual_chapter_id": "chapter",
                "manual_stage_id": "stage",
                "index": 1,
            }
        ]
        self.achievement_provider = None
        self.auto_validation_contract = None

    def load(self) -> None:
        self.load_calls += 1
        self.available = True
        self.cards = [{"index": 1}]


class HomeAsyncGuideServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        _DeferredThread.created.clear()

    def test_rebuild_schedules_worker_without_composing_on_ui_call(self) -> None:
        page = OptimizedHomePage()
        page.catalog = QuestCatalog([])

        with (
            patch("app.pages.home_optimized_page.Thread", _DeferredThread),
            patch.object(OptimizedHomePage, "_build_guide_service") as build_service,
        ):
            page._rebuild_guide_ultime_service()

        self.assertEqual(len(_DeferredThread.created), 1)
        worker = _DeferredThread.created[0]
        self.assertTrue(worker.started)
        self.assertEqual(worker.name, "DofusAtlasHomeGuide")
        self.assertTrue(worker.daemon)
        build_service.assert_not_called()
        self.assertTrue(page._guide_service_building)

        page.deleteLater()
        self.app.processEvents()

    def test_same_context_does_not_spawn_duplicate_worker(self) -> None:
        page = OptimizedHomePage()
        page.catalog = QuestCatalog([])
        page.achievement_provider = object()

        with patch("app.pages.home_optimized_page.Thread", _DeferredThread):
            page._rebuild_guide_ultime_service()
            page._rebuild_guide_ultime_service()

        self.assertEqual(len(_DeferredThread.created), 1)

        page.deleteLater()
        self.app.processEvents()

    def test_new_achievement_provider_supersedes_inflight_worker(self) -> None:
        page = OptimizedHomePage()
        page.catalog = QuestCatalog([])
        first_provider = object()
        second_provider = object()
        page.achievement_provider = first_provider

        with patch("app.pages.home_optimized_page.Thread", _DeferredThread):
            page._rebuild_guide_ultime_service()
            first_token = page._guide_service_build_token
            page.achievement_provider = second_provider
            page._rebuild_guide_ultime_service()
            second_token = page._guide_service_build_token

        self.assertEqual(len(_DeferredThread.created), 2)
        self.assertGreater(second_token, first_token)
        self.assertEqual(
            page._guide_service_context_key,
            (id(page.catalog), id(second_provider)),
        )
        self.assertTrue(page._guide_service_building)

        # A stale worker result must not clear the state of the replacement.
        page._on_guide_service_ready(first_token, object(), "stale")
        self.assertTrue(page._guide_service_building)

        page.deleteLater()
        self.app.processEvents()

    def test_manual_route_does_not_load_generated_fallback_when_available(self) -> None:
        catalog = QuestCatalog([])
        service = _FakeGuideService(True)
        provider = object()
        contract = {"cards": [{"card_key": "manual:chapter:stage"}]}
        with (
            patch("app.pages.home_optimized_page.QuestProgressService", return_value=object()),
            patch("app.pages.home_optimized_page.AchievementProgressService", return_value=object()),
            patch("app.pages.home_optimized_page.GuideProgressService", return_value=object()),
            patch("app.pages.home_optimized_page.QuestProvider", return_value=object()),
            patch(
                "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service.GuideUltimeManualRuntimeService",
                return_value=service,
            ) as constructor,
            patch(
                "app.modules.encyclopedia.services.guide_auto_validation_contract.build_route_auto_validation_contract",
                return_value=contract,
            ) as build_contract,
        ):
            result, error = OptimizedHomePage._build_guide_service(catalog, provider)

        self.assertIs(result, service)
        self.assertEqual(error, "")
        self.assertEqual(service.load_calls, 0)
        self.assertFalse(constructor.call_args.kwargs["autoload"])
        self.assertIs(service.achievement_provider, provider)
        self.assertIs(service.auto_validation_contract, contract)
        build_contract.assert_called_once_with(service.cards, achievement_provider=provider)

    def test_generated_fallback_loads_once_only_when_manual_route_is_unavailable(self) -> None:
        catalog = QuestCatalog([])
        service = _FakeGuideService(False)
        with (
            patch("app.pages.home_optimized_page.QuestProgressService", return_value=object()),
            patch("app.pages.home_optimized_page.AchievementProgressService", return_value=object()),
            patch("app.pages.home_optimized_page.GuideProgressService", return_value=object()),
            patch("app.pages.home_optimized_page.QuestProvider", return_value=object()),
            patch(
                "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service.GuideUltimeManualRuntimeService",
                return_value=service,
            ),
            patch(
                "app.modules.encyclopedia.services.guide_auto_validation_contract.build_route_auto_validation_contract",
                return_value={"cards": []},
            ) as build_contract,
        ):
            result, error = OptimizedHomePage._build_guide_service(catalog)

        self.assertIs(result, service)
        self.assertEqual(error, "")
        self.assertEqual(service.load_calls, 1)
        build_contract.assert_called_once_with(service.cards, achievement_provider=None)


if __name__ == "__main__":
    unittest.main()
