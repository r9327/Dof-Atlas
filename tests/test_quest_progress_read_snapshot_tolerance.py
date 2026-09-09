from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


class QuestProgressReadSnapshotToleranceTests(unittest.TestCase):
    def test_malformed_legacy_containers_are_treated_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = QuestProgressService(Path(tmp_dir) / "quest_progress.json")
            service.progress = {
                "version": 1,
                "characters": {
                    "slot:1": {
                        "done": [],
                        "completed_quest_objectives": {"42": {"bad": True}},
                        "quest_items": {"42": [123]},
                    }
                },
            }
            service._clear_read_caches()

            self.assertEqual(service.completed_quest_ids("slot:1"), set())
            self.assertEqual(service.completed_objectives("slot:1", 42), set())
            self.assertEqual(service.completed_item_ids("slot:1", 42), set())
            self.assertFalse(service.is_quest_completed("slot:1", 42))
            self.assertFalse(service.is_objective_completed("slot:1", 42, 7))
            self.assertFalse(service.is_item_completed("slot:1", 42, 123))


if __name__ == "__main__":
    unittest.main()
