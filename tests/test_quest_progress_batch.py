from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


class QuestProgressBatchTests(unittest.TestCase):
    def test_batch_preserves_peer_updates_and_refreshes_other_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quest_progress.json"
            first = QuestProgressService(path)
            second = QuestProgressService(path)

            self.assertTrue(first.set_quests_completed("character:1", [101, 102, 102]))
            self.assertEqual(second.completed_quest_ids("character:1"), {101, 102})

            second.set_quest_completed("character:1", 103, True)
            self.assertTrue(first.set_quests_completed("character:1", [102, 104]))
            self.assertEqual(first.completed_quest_ids("character:1"), {101, 102, 103, 104})
            self.assertEqual(second.completed_quest_ids("character:1"), {101, 102, 103, 104})

            self.assertFalse(first.set_quests_completed("character:1", [101, 104]))
            self.assertEqual(second.completed_quest_ids("character:1"), {101, 102, 103, 104})

    def test_batch_can_remove_flags_without_touching_other_quests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quest_progress.json"
            service = QuestProgressService(path)
            service.set_quests_completed("character:2", [11, 12, 13])

            self.assertTrue(service.set_quests_completed("character:2", [11, 13], completed=False))
            self.assertEqual(service.completed_quest_ids("character:2"), {12})

    def test_batch_rejects_non_positive_ids_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "quest_progress.json"
            service = QuestProgressService(path)
            service.set_quest_completed("character:1", 77, True)

            with self.assertRaises(ValueError):
                service.set_quests_completed("character:1", [78, 0, 79])

            self.assertEqual(service.completed_quest_ids("character:1"), {77})


if __name__ == "__main__":
    unittest.main()
