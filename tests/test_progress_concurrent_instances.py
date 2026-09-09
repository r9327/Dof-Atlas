from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


class ProgressConcurrentInstanceTests(unittest.TestCase):
    def test_two_quest_services_preserve_each_others_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            first = QuestProgressService(path)
            stale_second = QuestProgressService(path)

            first.set_quest_completed("character:1", 101, True)
            stale_second.set_quest_completed("character:1", 202, True)

            reloaded = QuestProgressService(path)
            self.assertEqual(reloaded.completed_quest_ids("character:1"), {101, 202})

    def test_quest_and_item_mutations_preserve_legacy_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quest_path = Path(tmp) / "quest_only.json"
            QuestProgressService(quest_path).set_quest_completed("character:1", 101, True)
            self.assertEqual(
                json.loads(quest_path.read_text(encoding="utf-8")),
                {
                    "version": 1,
                    "characters": {"character:1": {"done": {"101": True}}},
                },
            )

            item_path = Path(tmp) / "item_only.json"
            QuestProgressService(item_path).set_item_completed("character:1", 303, 7001, True)
            self.assertEqual(
                json.loads(item_path.read_text(encoding="utf-8")),
                {
                    "version": 1,
                    "characters": {
                        "character:1": {
                            "done": {},
                            "quest_items": {"303": {"7001": True}},
                        }
                    },
                },
            )

    def test_two_quest_services_preserve_item_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quest_progress.json"
            first = QuestProgressService(path)
            stale_second = QuestProgressService(path)

            first.set_item_completed("character:1", 303, 7001, True)
            stale_second.set_item_completed("character:1", 303, 7002, True)

            reloaded = QuestProgressService(path)
            self.assertEqual(reloaded.completed_item_ids("character:1", 303), {7001, 7002})

            first.set_item_completed("character:1", 303, 7001, False)
            self.assertFalse(stale_second.is_item_completed("character:1", 303, 7001))
            self.assertTrue(stale_second.is_item_completed("character:1", 303, 7002))

    def test_two_guide_services_preserve_each_others_manual_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide_progress.json"
            first = GuideProgressService(path)
            stale_second = GuideProgressService(path)

            first.set_manual_step_completed("character:1", "guide", "stage-a", True)
            stale_second.set_manual_step_completed("character:1", "guide", "stage-b", True)

            reloaded = GuideProgressService(path)
            self.assertEqual(
                reloaded.manual_steps("character:1", "guide"),
                {"stage-a", "stage-b"},
            )


if __name__ == "__main__":
    unittest.main()
