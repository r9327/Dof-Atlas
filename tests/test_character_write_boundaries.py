from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.character_identity import require_character_key
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


INVALID_CHARACTER_KEYS = (
    "slot:1",
    "slots",
    "legacy_slots",
    "1",
    "character:",
    "character:abc",
    "arbitrary",
    "Alice",
    "pid:1234",
    "",
)


class CharacterWriteBoundaryTests(unittest.TestCase):
    def test_canonical_validator_rejects_every_noncanonical_key(self) -> None:
        self.assertEqual("character:1", require_character_key("character:1"))
        self.assertEqual("character:2", require_character_key(" character:2 "))
        for character_key in INVALID_CHARACTER_KEYS:
            with self.subTest(character_key=character_key), self.assertRaises(ValueError):
                require_character_key(character_key)

    def test_invalid_keys_cannot_create_quest_progress(self) -> None:
        for character_key in INVALID_CHARACTER_KEYS:
            with self.subTest(character_key=character_key), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "quests.json"
                service = QuestProgressService(path)
                with self.assertRaises(ValueError):
                    service.set_quest_completed(character_key, 101, True)
                self.assertFalse(path.exists())
                self.assertNotIn(character_key, service.progress["characters"])

    def test_invalid_keys_cannot_create_guide_progress(self) -> None:
        for character_key in INVALID_CHARACTER_KEYS:
            with self.subTest(character_key=character_key), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "guides.json"
                service = GuideProgressService(path)
                with self.assertRaises(ValueError):
                    service.set_manual_step_completed(character_key, "guide", "step", True)
                self.assertFalse(path.exists())
                self.assertNotIn(character_key, service.progress["characters"])

    def test_invalid_keys_cannot_create_achievement_progress(self) -> None:
        for character_key in INVALID_CHARACTER_KEYS:
            with self.subTest(character_key=character_key), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "achievements.json"
                service = AchievementProgressService(path)
                with self.assertRaises(ValueError):
                    service.set_achievement_completed(character_key, 201, True)
                self.assertFalse(path.exists())
                self.assertNotIn(character_key, service.progress["characters"])

    def test_modern_progress_services_reject_noncanonical_writes(self) -> None:
        service_cases = (
            (
                QuestProgressService,
                lambda service: service.set_quest_completed("slot:1", 101, True),
            ),
            (
                GuideProgressService,
                lambda service: service.set_manual_step_completed(
                    "slot:1", "guide", "step", True
                ),
            ),
            (
                AchievementProgressService,
                lambda service: service.set_achievement_completed("slot:1", 201, True),
            ),
        )
        for service_type, write in service_cases:
            with (
                self.subTest(service=service_type.__name__),
                tempfile.TemporaryDirectory() as tmp,
            ):
                path = Path(tmp) / "progress.json"
                service = service_type(path)
                with self.assertRaises(ValueError):
                    write(service)
                self.assertFalse(path.exists())

    def test_every_quest_mutation_entrypoint_checks_identity_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = QuestProgressService(Path(tmp) / "quests.json")
            calls = (
                lambda: service.set_quest_completed("slot:1", 1, True),
                lambda: service.set_quests_completed("slot:1", [1], True),
                lambda: service.set_objective_completed("slot:1", 1, 2, True),
                lambda: service.set_item_completed("slot:1", 1, 3, True),
            )
            for call in calls:
                with self.subTest(call=call), self.assertRaises(ValueError):
                    call()
            self.assertFalse(service.path.exists())

    def test_every_achievement_mutation_entrypoint_checks_identity_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = AchievementProgressService(Path(tmp) / "achievements.json")
            calls = (
                lambda: service.set_achievement_completed("slot:1", 1, True),
                lambda: service.set_objective_completed("slot:1", 1, 2, True),
                lambda: service.set_alignment_order_choice("slot:1", "bonta", "order"),
                lambda: service.clear_alignment_order_choice("slot:1"),
                lambda: service.sync_from_quest_progress("slot:1", object(), object()),
            )
            for call in calls:
                with self.subTest(call=call), self.assertRaises(ValueError):
                    call()
            self.assertFalse(service.path.exists())

    def test_compatibility_save_rejects_noncanonical_snapshot_keys(self) -> None:
        service_types = (QuestProgressService, GuideProgressService, AchievementProgressService)
        for service_type in service_types:
            with self.subTest(service=service_type.__name__), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "progress.json"
                service = service_type(path)
                service.progress["characters"]["slot:1"] = {"legacy": True}
                with self.assertRaises(ValueError):
                    service.save()
                self.assertFalse(path.exists())

    def test_legacy_progress_remains_readable_without_rewrite(self) -> None:
        fixtures = (
            (
                QuestProgressService,
                {"version": 1, "characters": {"slot:1": {"done": {"101": True}}}},
                lambda service: service.is_quest_completed("slot:1", 101),
            ),
            (
                GuideProgressService,
                {
                    "version": 1,
                    "characters": {"slot:1": {"manual_steps": {"guide": ["step"]}}},
                },
                lambda service: service.is_manual_step_completed("slot:1", "guide", "step"),
            ),
            (
                AchievementProgressService,
                {
                    "version": 1,
                    "characters": {"slot:1": {"completed_achievements": [201]}},
                },
                lambda service: service.is_achievement_completed("slot:1", 201),
            ),
        )
        for service_type, payload, read_assertion in fixtures:
            with self.subTest(service=service_type.__name__), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "progress.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                before = path.read_bytes()
                self.assertTrue(read_assertion(service_type(path)))
                self.assertEqual(before, path.read_bytes())

    def test_canonical_characters_remain_isolated_after_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quests = QuestProgressService(root / "quests.json")
            guides = GuideProgressService(root / "guides.json")
            achievements = AchievementProgressService(root / "achievements.json")

            quests.set_quest_completed("character:1", 101, True)
            quests.set_quest_completed("character:2", 202, True)
            guides.set_manual_step_completed("character:1", "guide", "one", True)
            guides.set_manual_step_completed("character:2", "guide", "two", True)
            achievements.set_achievement_completed("character:1", 301, True)
            achievements.set_achievement_completed("character:2", 302, True)

            quests = QuestProgressService(root / "quests.json")
            guides = GuideProgressService(root / "guides.json")
            achievements = AchievementProgressService(root / "achievements.json")
            self.assertEqual({101}, quests.completed_quest_ids("character:1"))
            self.assertEqual({202}, quests.completed_quest_ids("character:2"))
            self.assertEqual({"one"}, guides.manual_steps("character:1", "guide"))
            self.assertEqual({"two"}, guides.manual_steps("character:2", "guide"))
            self.assertTrue(achievements.is_achievement_completed("character:1", 301))
            self.assertFalse(achievements.is_achievement_completed("character:1", 302))
            self.assertTrue(achievements.is_achievement_completed("character:2", 302))
            self.assertFalse(achievements.is_achievement_completed("character:2", 301))


if __name__ == "__main__":
    unittest.main()
