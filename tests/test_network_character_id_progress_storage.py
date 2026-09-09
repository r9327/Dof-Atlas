from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


class CharacterIdProgressStorageTests(unittest.TestCase):
    def test_missing_identity_cannot_create_fallback_slot_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            quest_path = root / "quests.json"
            achievement_path = root / "achievements.json"
            guide_path = root / "guides.json"
            quests = QuestProgressService(quest_path)
            achievements = AchievementProgressService(achievement_path)
            guides = GuideProgressService(guide_path)

            writes = (
                lambda: quests.set_quest_completed("", 101, True),
                lambda: achievements.set_achievement_completed("", 201, True),
                lambda: guides.set_manual_step_completed("", "guide", "step", True),
            )
            for write in writes:
                with self.assertRaises(ValueError):
                    write()

            self.assertFalse(quest_path.exists())
            self.assertFalse(achievement_path.exists())
            self.assertFalse(guide_path.exists())

    def test_verified_character_id_is_the_only_created_progress_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            character_key = "character:77"
            quest_path = root / "quests.json"
            achievement_path = root / "achievements.json"
            guide_path = root / "guides.json"

            QuestProgressService(quest_path).set_quest_completed(character_key, 101, True)
            AchievementProgressService(achievement_path).set_achievement_completed(
                character_key,
                201,
                True,
            )
            GuideProgressService(guide_path).set_manual_step_completed(
                character_key,
                "guide",
                "step",
                True,
            )

            for path in (quest_path, achievement_path, guide_path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(set(payload["characters"]), {character_key})
                self.assertNotIn("slot:1", payload["characters"])


if __name__ == "__main__":
    unittest.main()
