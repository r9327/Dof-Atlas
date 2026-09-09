from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.constants import KEY_SELECTED_CHARACTER, KEY_SESSION_ORDER
from app.network.character_runtime_state import character_runtime_state
from app.services.character_data_service import CharacterDataService


class CharacterDataServiceTests(unittest.TestCase):
    def test_delete_character_removes_identity_and_all_progress_but_preserves_other_characters(self):
        runtime_state = character_runtime_state()
        runtime_state.reset()
        try:
            runtime_state.identify(
                session_id="alpha-session",
                character_key="character:42",
                character_id=42,
                name="Alpha",
            )
            runtime_state.update_verified_profile(
                "alpha-session",
                level=199,
                achievement_points=12345,
            )
            runtime_state.identify(
                session_id="beta-session",
                character_key="character:84",
                character_id=84,
                name="Beta",
            )
            runtime_state.update_verified_profile("beta-session", level=80)

            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                profile = root / "profiles.json"
                bindings = root / "network_character_bindings.json"
                quests = root / "quest_progress.json"
                achievements = root / "achievement_progress.json"
                guides = root / "guide_progress.json"

                profile.write_text(
                    json.dumps(
                        {
                            KEY_SELECTED_CHARACTER: "character:42",
                            KEY_SESSION_ORDER: ["alpha", "beta", "offline"],
                            "other": True,
                        }
                    ),
                    encoding="utf-8",
                )
                bindings.write_text(
                    json.dumps(
                        {
                            "characters": {
                                "42": {"name": "Alpha"},
                                "84": {"name": "Beta"},
                            },
                            "slots": {
                                "1": {"character_id": 42, "name": "Alpha"},
                                "2": {"character_id": 84, "name": "Beta"},
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                for path in (quests, achievements, guides):
                    path.write_text(
                        json.dumps(
                            {
                                "version": 1,
                                "characters": {
                                    "character:42": {"value": "remove"},
                                    "character:84": {"value": "keep"},
                                },
                            }
                        ),
                        encoding="utf-8",
                    )

                service = CharacterDataService(
                    profile_path=profile,
                    binding_path=bindings,
                    quest_progress_path=quests,
                    achievement_progress_path=achievements,
                    guide_progress_path=guides,
                )
                self.assertTrue(service.delete_character("character:42"))

                persisted_profile = json.loads(profile.read_text(encoding="utf-8"))
                self.assertEqual(persisted_profile[KEY_SELECTED_CHARACTER], "")
                self.assertEqual(
                    persisted_profile[KEY_SESSION_ORDER],
                    ["beta", "offline"],
                )
                self.assertTrue(persisted_profile["other"])

                persisted_bindings = json.loads(bindings.read_text(encoding="utf-8"))
                self.assertNotIn("42", persisted_bindings["characters"])
                self.assertIn("84", persisted_bindings["characters"])
                self.assertNotIn("1", persisted_bindings["slots"])
                self.assertIn("2", persisted_bindings["slots"])

                for path in (quests, achievements, guides):
                    persisted = json.loads(path.read_text(encoding="utf-8"))
                    self.assertNotIn("character:42", persisted["characters"])
                    self.assertEqual(persisted["characters"]["character:84"], {"value": "keep"})

                self.assertIsNone(runtime_state.snapshot("character:42"))
                self.assertEqual(runtime_state.snapshot("character:84").level, 80)
        finally:
            runtime_state.reset()

    def test_delete_without_saved_binding_name_does_not_guess_order_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profiles.json"
            bindings = root / "bindings.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["alpha", "beta"]}),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps({"characters": {"42": {}}, "slots": {}}),
                encoding="utf-8",
            )
            service = CharacterDataService(
                profile_path=profile,
                binding_path=bindings,
                quest_progress_path=root / "quests.json",
                achievement_progress_path=root / "achievements.json",
                guide_progress_path=root / "guides.json",
            )

            self.assertTrue(service.delete_character("character:42"))

            persisted_profile = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(persisted_profile[KEY_SESSION_ORDER], ["alpha", "beta"])

    def test_delete_rejects_non_verified_character_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service = CharacterDataService(
                profile_path=root / "profiles.json",
                binding_path=root / "bindings.json",
                quest_progress_path=root / "quests.json",
                achievement_progress_path=root / "achievements.json",
                guide_progress_path=root / "guides.json",
            )
            self.assertFalse(service.delete_character("slot:1"))
            self.assertFalse(service.delete_character(""))


if __name__ == "__main__":
    unittest.main()
