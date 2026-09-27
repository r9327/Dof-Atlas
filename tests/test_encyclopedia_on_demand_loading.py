from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import main
from app.modules.encyclopedia.constants import GUIDES_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider
from app.modules.encyclopedia.services import QuestGraphService
from app.quest_catalog import QuestCatalog, QuestRecord


class EncyclopediaOnDemandTests(unittest.TestCase):
    @staticmethod
    def _catalog() -> QuestCatalog:
        return QuestCatalog(
            [
                QuestRecord(
                    id=1,
                    name="Quête test",
                    category="Incarnam",
                    level_min=1,
                    level_max=1,
                    start_criterion="",
                )
            ]
        )

    def test_canonical_factory_creates_lazy_shell_without_quest_preload(self) -> None:
        class CapturedPage:
            def __init__(self, _status_callback, **kwargs) -> None:
                self.kwargs = kwargs
                self.character_keys = []

            def set_character_key(self, character_key: str) -> None:
                self.character_keys.append(character_key)

        class Shell:
            preload_results = {}
            pending_encyclopedia_tab = GUIDES_TAB
            pending_guide_target = None
            current_character_key = "character:42"
            set_status = Mock()
            launch_travel = Mock()
            on_encyclopedia_related_data_ready = Mock()
            start_preload = Mock(side_effect=AssertionError("Quest preload forbidden"))

        with (
            patch.object(main, "EncyclopediaPage", CapturedPage),
            patch.object(main, "build_quest_preload") as build_quest_preload,
        ):
            page = main.AtlasWindow.create_encyclopedia_page(Shell())

        self.assertIsInstance(page, CapturedPage)
        self.assertIsNone(page.kwargs["quest_provider"]._catalog)
        self.assertEqual(page.kwargs["initial_tab"], GUIDES_TAB)
        self.assertEqual(page.character_keys, ["character:42"])
        Shell.start_preload.assert_not_called()
        build_quest_preload.assert_not_called()

    def test_canonical_factory_reuses_only_valid_loaded_preloads(self) -> None:
        class CapturedPage:
            def __init__(self, _status_callback, **kwargs) -> None:
                self.kwargs = kwargs

            def set_character_key(self, character_key: str) -> None:
                self.character_key = character_key

        catalog = self._catalog()
        loaded_achievement = object.__new__(AchievementProvider)
        loaded_achievement._loaded = True
        cold_achievement = object.__new__(AchievementProvider)
        cold_achievement._loaded = False
        loaded_guide = object.__new__(GuideProvider)
        loaded_guide._loaded = True
        cold_guide = object.__new__(GuideProvider)
        cold_guide._loaded = False
        graph = object.__new__(QuestGraphService)

        class Shell:
            pending_encyclopedia_tab = ""
            pending_guide_target = ("guide-test", None)
            current_character_key = "character:84"
            set_status = Mock()
            launch_travel = Mock()
            on_encyclopedia_related_data_ready = Mock()

        shell = Shell()
        shell.preload_results = {"quests": {
            "catalog": catalog,
            "owned_items": {"item:1": True},
            "achievement_provider": loaded_achievement,
            "guide_provider": cold_guide,
            "quest_graph": graph,
            "guide_progress_by_guide": {"guide-test": 50},
            "guide_progress_character_key": "character:84",
        }}

        with patch.object(main, "EncyclopediaPage", CapturedPage):
            page = main.AtlasWindow.create_encyclopedia_page(shell)

        self.assertIs(page.kwargs["quest_provider"]._catalog, catalog)
        self.assertIs(page.kwargs["achievement_provider"], loaded_achievement)
        self.assertIsNone(page.kwargs["guide_provider"])
        self.assertIs(page.kwargs["quest_graph"], graph)
        self.assertEqual(page.kwargs["guide_progress_by_guide"], {"guide-test": 50})
        self.assertEqual(page.kwargs["guide_progress_character_key"], "character:84")
        self.assertEqual(page.kwargs["owned_items"], {"item:1": True})
        self.assertEqual(page.kwargs["initial_tab"], GUIDES_TAB)
        self.assertEqual(page.character_key, "character:84")

        shell.preload_results["quests"].update({
            "achievement_provider": cold_achievement,
            "guide_provider": loaded_guide,
        })
        with patch.object(main, "EncyclopediaPage", CapturedPage):
            second_page = main.AtlasWindow.create_encyclopedia_page(shell)

        self.assertIsNone(second_page.kwargs["achievement_provider"])
        self.assertIs(second_page.kwargs["guide_provider"], loaded_guide)


if __name__ == "__main__":
    unittest.main()
