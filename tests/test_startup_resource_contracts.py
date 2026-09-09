from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main
from app.modules.encyclopedia.providers.achievement_provider import (
    AchievementProvider as ConcreteAchievementProvider,
)
from app.modules.encyclopedia.providers.guide_provider import GuideProvider as ConcreteGuideProvider
from app.modules.encyclopedia.services import QuestGraphService
from app.quest_catalog import QuestCatalog


class StartupResourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_window_constructor_does_not_preload_heavy_encyclopedia_owners(self) -> None:
        with (
            patch.object(main.AtlasWindow, "setup_tray", return_value=None),
            patch.object(QuestCatalog, "load", side_effect=AssertionError("Quest preload at startup")) as quests,
            patch.object(
                ConcreteAchievementProvider,
                "load_all",
                side_effect=AssertionError("Achievement preload at startup"),
            ) as achievements,
            patch.object(
                ConcreteGuideProvider,
                "load_all",
                side_effect=AssertionError("Guide preload at startup"),
            ) as guides,
            patch.object(
                QuestGraphService,
                "__init__",
                side_effect=AssertionError("QuestGraph construction at startup"),
            ) as graph,
        ):
            window = main.AtlasWindow()
        try:
            quests.assert_not_called()
            achievements.assert_not_called()
            guides.assert_not_called()
            graph.assert_not_called()
            self.assertIn("Quetes", window.page_factories)
            self.assertNotIsInstance(window.page_widgets["Quetes"], main.EncyclopediaPage)
        finally:
            window.quit_requested = True
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_encyclopedia_factory_constructs_one_quest_provider(self) -> None:
        constructions: list[object] = []

        class CountingQuestProvider:
            def __init__(self, *, catalog=None) -> None:
                self._catalog = catalog
                constructions.append(self)

        class CapturedPage:
            def __init__(self, _status_callback, **kwargs) -> None:
                self.kwargs = kwargs

            def set_character_key(self, character_key: str) -> None:
                self.character_key = character_key

        class Shell:
            preload_results = {}
            pending_encyclopedia_tab = ""
            pending_guide_target = None
            current_character_key = "character:42"
            set_status = Mock()
            launch_travel = Mock()
            on_encyclopedia_related_data_ready = Mock()

        with (
            patch.object(main, "QuestProvider", CountingQuestProvider),
            patch.object(main, "EncyclopediaPage", CapturedPage),
        ):
            page = main.AtlasWindow.create_encyclopedia_page(Shell())

        self.assertEqual(len(constructions), 1)
        self.assertIs(page.kwargs["quest_provider"], constructions[0])
        self.assertIsNone(page.kwargs["achievement_provider"])
        self.assertIsNone(page.kwargs["guide_provider"])
        self.assertIsNone(page.kwargs["quest_graph"])


if __name__ == "__main__":
    unittest.main()
