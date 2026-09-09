from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


class QuestProgressBatchContractTests(unittest.TestCase):
    def test_batch_rejects_non_integer_ids_without_mutating_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            service = QuestProgressService(path)

            for quest_ids in ((True,), ("5",), (1, False, 2)):
                with self.subTest(quest_ids=quest_ids):
                    with self.assertRaises(ValueError):
                        service.set_quests_completed("character:1", quest_ids, True)
                    self.assertEqual(service.completed_quest_ids("character:1"), set())

    def test_batch_keeps_existing_local_progress_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            service = QuestProgressService(path)
            service.set_quest_completed("character:1", 999, True)

            self.assertTrue(service.set_quests_completed("character:1", (1, 2, 3, 3), True))
            self.assertEqual(service.completed_quest_ids("character:1"), {1, 2, 3, 999})
            generation = service._coordinator.generation

            self.assertFalse(service.set_quests_completed("character:1", (3, 2, 1), True))
            self.assertEqual(service._coordinator.generation, generation)
            self.assertEqual(service.completed_quest_ids("character:1"), {1, 2, 3, 999})


if __name__ == "__main__":
    unittest.main()
