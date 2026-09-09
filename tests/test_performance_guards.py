from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app.modules.encyclopedia.services.quest_progress_service as quest_progress_module
from app.modules.encyclopedia.services.progress_service import AchievementProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService as SerializedAchievementProgressService,
)


class PerformanceGuardTests(unittest.TestCase):
    def test_quest_progress_refresh_skips_disk_until_generation_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            reader = QuestProgressService(path)
            writer = QuestProgressService(path)
            real_loader = quest_progress_module.load_quest_progress

            with patch.object(
                quest_progress_module,
                "load_quest_progress",
                wraps=real_loader,
            ) as loader:
                self.assertFalse(reader.refresh_if_changed())
                loader.assert_not_called()

                writer.set_quest_completed("character:1", 123, True)
                loader.reset_mock()

                self.assertTrue(reader.refresh_if_changed())
                self.assertEqual(loader.call_count, 1)
                self.assertTrue(reader.is_quest_completed("character:1", 123))

                loader.reset_mock()
                self.assertFalse(reader.refresh_if_changed())
                loader.assert_not_called()

    def test_achievement_completion_lookup_cache_reuses_state_and_invalidates_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            service = AchievementProgressService(path)
            service.progress = {
                "version": 1,
                "characters": {
                    "character:1": {
                        "completed_achievements": [10],
                        "completed_objectives": {"10": [100]},
                        "auto_completed_achievements": [],
                        "auto_completed_objectives": {},
                    }
                },
            }

            with patch.object(service, "_character", wraps=service._character) as character_loader:
                for _ in range(25):
                    self.assertTrue(service.is_achievement_completed("character:1", 10))
                    self.assertTrue(service.is_objective_completed("character:1", 10, 100))
                self.assertEqual(character_loader.call_count, 1)

                service.set_achievement_completed("character:1", 10, False)
                character_loader.reset_mock()

                self.assertFalse(service.is_achievement_completed("character:1", 10))
                self.assertEqual(character_loader.call_count, 1)

    def test_serialized_achievement_reader_reloads_once_per_peer_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            reader = SerializedAchievementProgressService(path)
            writer = SerializedAchievementProgressService(path)

            writer.set_achievement_completed("character:1", 10, True)
            with patch.object(reader, "_load", wraps=reader._load) as loader:
                self.assertTrue(reader.is_achievement_completed("character:1", 10))
                self.assertEqual(loader.call_count, 1)

                loader.reset_mock()
                self.assertTrue(reader.is_achievement_completed("character:1", 10))
                loader.assert_not_called()

                writer.set_achievement_completed("character:1", 10, False)
                self.assertFalse(reader.is_achievement_completed("character:1", 10))
                self.assertEqual(loader.call_count, 1)

    def test_achievement_auto_sync_skips_full_rebuild_until_inputs_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            service = AchievementProgressService(path)
            provider = Mock()
            provider.load_retained.return_value = ()
            quest_progress = Mock()
            quest_progress.completed_quest_ids.return_value = {1, 2, 3}

            self.assertFalse(
                service.sync_from_quest_progress(
                    "character:1",
                    provider,
                    quest_progress,
                )
            )
            self.assertFalse(
                service.sync_from_quest_progress(
                    "character:1",
                    provider,
                    quest_progress,
                )
            )
            self.assertEqual(provider.load_retained.call_count, 1)

            service.set_achievement_completed("character:1", 99, True)
            self.assertFalse(
                service.sync_from_quest_progress(
                    "character:1",
                    provider,
                    quest_progress,
                )
            )
            self.assertEqual(provider.load_retained.call_count, 2)

    def test_main_does_not_block_first_window_on_startup_preload(self) -> None:
        source = Path("main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        main_function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        calls = [
            node
            for node in ast.walk(main_function)
            if isinstance(node, ast.Call)
        ]
        called_names = {
            node.func.id
            for node in calls
            if isinstance(node.func, ast.Name)
        }

        self.assertIn("AtlasWindow", called_names)
        self.assertNotIn("run_startup_preload", called_names)

    def test_encyclopedia_only_builds_quest_page_for_requested_quest_tab(self) -> None:
        source = Path("app/modules/encyclopedia/views/encyclopedia_page.py").read_text(encoding="utf-8")
        self.assertIn(
            "if tab_name == QUESTS_TAB and self._initial_tab == QUESTS_TAB:",
            source,
        )
        self.assertIn(
            "if label == QUESTS_TAB and self.quest_page is None:",
            source,
        )

        main_source = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("initial_tab=self.pending_encyclopedia_tab", main_source)

    def test_home_dedupes_identical_progress_renders(self) -> None:
        source = Path("app/pages/home_page.py").read_text(encoding="utf-8")
        self.assertIn("next_key == self.character_key", source)
        self.assertIn("_last_progress_signature", source)
        self.assertIn("_progress_input_signature", source)


if __name__ == "__main__":
    unittest.main()
