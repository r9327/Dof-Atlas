from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


class ProgressMultiInstanceTests(unittest.TestCase):
    def test_quest_instances_refresh_after_peer_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quest_progress.json"
            first = QuestProgressService(path)
            second = QuestProgressService(path)

            self.assertFalse(second.is_quest_completed("character:1", 101))
            first.set_quest_completed("character:1", 101, True)
            self.assertTrue(second.is_quest_completed("character:1", 101))

            second.set_quest_completed("character:1", 202, True)
            self.assertEqual(first.completed_quest_ids("character:1"), {101, 202})

            first.set_objective_completed("character:1", 303, 7, True)
            self.assertTrue(second.is_objective_completed("character:1", 303, 7))

            self.assertFalse(second.is_item_completed("character:1", 404, 9001))
            first.set_item_completed("character:1", 404, 9001, True)
            self.assertTrue(second.is_item_completed("character:1", 404, 9001))
            self.assertEqual(second.completed_item_ids("character:1", 404), {9001})
            self.assertFalse(second.is_quest_completed("character:2", 101))

    def test_quest_compatibility_save_refuses_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quest_progress.json"
            first = QuestProgressService(path)
            second = QuestProgressService(path)

            first.progress.setdefault("characters", {}).setdefault("character:1", {"done": {}})["done"]["101"] = True
            second.set_quest_completed("character:1", 202, True)

            with self.assertRaises(RuntimeError):
                first.save()

            verifier = QuestProgressService(path)
            self.assertFalse(verifier.is_quest_completed("character:1", 101))
            self.assertTrue(verifier.is_quest_completed("character:1", 202))

    def test_quest_compatibility_save_still_works_without_peer_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quest_progress.json"
            service = QuestProgressService(path)
            service.progress.setdefault("characters", {}).setdefault("character:1", {"done": {}})["done"]["101"] = True

            service.save()

            verifier = QuestProgressService(path)
            self.assertTrue(verifier.is_quest_completed("character:1", 101))

    def test_guide_instances_refresh_after_peer_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide_progress.json"
            first = GuideProgressService(path)
            second = GuideProgressService(path)

            first.set_manual_step_completed("character:1", "guide", "manual:a", True)
            self.assertTrue(second.is_manual_step_completed("character:1", "guide", "manual:a"))

            second.set_manual_step_completed("character:1", "guide", "manual:b", True)
            self.assertEqual(
                first.manual_steps("character:1", "guide"),
                {"manual:a", "manual:b"},
            )
            self.assertEqual(first.manual_steps("character:2", "guide"), set())

    def test_guide_compatibility_save_refuses_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide_progress.json"
            first = GuideProgressService(path)
            second = GuideProgressService(path)

            first.progress.setdefault("characters", {}).setdefault("character:1", {}).setdefault("manual_steps", {})["guide"] = ["manual:a"]
            second.set_manual_step_completed("character:1", "guide", "manual:b", True)

            with self.assertRaises(RuntimeError):
                first.save()

            verifier = GuideProgressService(path)
            self.assertFalse(verifier.is_manual_step_completed("character:1", "guide", "manual:a"))
            self.assertTrue(verifier.is_manual_step_completed("character:1", "guide", "manual:b"))

    def test_achievement_instances_refresh_after_peer_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievement_progress.json"
            first = AchievementProgressService(path)
            second = AchievementProgressService(path)

            first.set_achievement_completed("character:1", 11, True)
            self.assertTrue(second.is_achievement_completed("character:1", 11))

            second.set_objective_completed("character:1", 22, 2201, True)
            self.assertTrue(first.is_objective_completed("character:1", 22, 2201))

            first.set_alignment_order_choice("character:1", "bonta", "Cœur Vaillant")
            self.assertEqual(
                second.alignment_order_choice("character:1"),
                ("bonta", "Cœur Vaillant"),
            )
            self.assertFalse(second.is_achievement_completed("character:2", 11))

    def test_achievement_compatibility_save_refuses_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievement_progress.json"
            first = AchievementProgressService(path)
            second = AchievementProgressService(path)

            first.progress.setdefault("characters", {}).setdefault("character:1", {}).setdefault("completed_achievements", []).append(11)
            second.set_achievement_completed("character:1", 22, True)

            with self.assertRaises(RuntimeError):
                first.save()

            verifier = AchievementProgressService(path)
            self.assertFalse(verifier.is_achievement_completed("character:1", 11))
            self.assertTrue(verifier.is_achievement_completed("character:1", 22))


if __name__ == "__main__":
    unittest.main()
