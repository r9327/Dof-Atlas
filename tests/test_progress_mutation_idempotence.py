from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


class ProgressMutationIdempotenceTests(unittest.TestCase):
    def test_quest_mutations_publish_only_real_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = QuestProgressService(Path(directory) / "quests.json")

            self.assertTrue(service.set_quest_completed("character:1", 10, True))
            generation = service._coordinator.generation
            self.assertFalse(service.set_quest_completed("character:1", 10, True))
            self.assertEqual(service._coordinator.generation, generation)

            self.assertTrue(service.set_objective_completed("character:1", 20, 200, True))
            generation = service._coordinator.generation
            self.assertFalse(service.set_objective_completed("character:1", 20, 200, True))
            self.assertEqual(service._coordinator.generation, generation)

            self.assertTrue(service.set_item_completed("character:1", 30, 300, True))
            generation = service._coordinator.generation
            self.assertFalse(service.set_item_completed("character:1", 30, 300, True))
            self.assertEqual(service._coordinator.generation, generation)

    def test_guide_mutation_publishes_only_real_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = GuideProgressService(Path(directory) / "guides.json")

            self.assertTrue(
                service.set_manual_step_completed("character:1", "guide", "stage:a", True)
            )
            generation = service._coordinator.generation
            self.assertFalse(
                service.set_manual_step_completed("character:1", "guide", "stage:a", True)
            )
            self.assertEqual(service._coordinator.generation, generation)

    def test_achievement_mutations_publish_only_real_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = AchievementProgressService(Path(directory) / "achievements.json")

            self.assertTrue(service.set_achievement_completed("character:1", 40, True))
            generation = service._coordinator.generation
            self.assertFalse(service.set_achievement_completed("character:1", 40, True))
            self.assertEqual(service._coordinator.generation, generation)

            self.assertTrue(service.set_objective_completed("character:1", 50, 500, True))
            generation = service._coordinator.generation
            self.assertFalse(service.set_objective_completed("character:1", 50, 500, True))
            self.assertEqual(service._coordinator.generation, generation)

            order_name = "Ordre du Cœur Vaillant"
            self.assertTrue(
                service.set_alignment_order_choice("character:1", "bonta", order_name)
            )
            generation = service._coordinator.generation
            self.assertFalse(
                service.set_alignment_order_choice("character:1", "bonta", order_name)
            )
            self.assertEqual(service._coordinator.generation, generation)

            self.assertTrue(service.clear_alignment_order_choice("character:1"))
            generation = service._coordinator.generation
            self.assertFalse(service.clear_alignment_order_choice("character:1"))
            self.assertEqual(service._coordinator.generation, generation)


if __name__ == "__main__":
    unittest.main()
