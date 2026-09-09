from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.constants import KEY_SESSION_ORDER
from app.network.character_resolver import CharacterSlotResolver
from app.quest_catalog import load_quest_characters


class CharacterSlotResolverTests(unittest.TestCase):
    def _resolver(self, root: Path, order: list[str], clients: list[dict]) -> CharacterSlotResolver:
        profile = root / "profiles.json"
        client_index = root / "client_index.json"
        profile.write_text(json.dumps({KEY_SESSION_ORDER: order}), encoding="utf-8")
        client_index.write_text(json.dumps({"clients": clients}), encoding="utf-8")
        return CharacterSlotResolver(
            profile,
            client_index,
            binding_path=root / "network_character_bindings.json",
            slot_count=max(2, len(order)),
            progress_paths=(),
        )

    def test_name_without_verified_character_id_does_not_create_progress_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = self._resolver(
                Path(temp_dir),
                ["Alice", "Bob"],
                [{"index": 2, "name": "Bob"}],
            )
            self.assertIsNone(resolver.resolve("Bob"))

    def test_duplicate_slot_names_fail_closed_even_if_one_appears_connected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = self._resolver(
                Path(temp_dir),
                ["Alice", "Alice"],
                [{"index": 2, "name": "Alice"}],
            )
            self.assertIsNone(resolver.resolve("Alice"))

    def test_placeholder_slot_name_is_never_network_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = self._resolver(Path(temp_dir), ["", ""], [])
            self.assertIsNone(resolver.resolve("Slot 1"))

    def test_name_and_pid_without_numeric_id_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            resolver = self._resolver(
                root,
                ["dofus_3_6_10_11_release_1", "dofus_3_6_10_11_release_2"],
                [
                    {"index": 1, "slot": 1, "name": "Dofus 3.6.10.11 Release 1", "pid": 4101},
                    {"index": 2, "slot": 2, "name": "Dofus 3.6.10.11 Release 2", "pid": 4102},
                ],
            )

            resolution = resolver.resolve_for_session("Rabmou", "tcp:4102:7")

            self.assertIsNone(resolution)
            self.assertFalse((root / "network_character_bindings.json").exists())

    def test_release_metadata_is_not_displayed_as_character_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            client_index = root / "client_index.json"
            bindings = root / "bindings.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["dofus_3_6_10_11_release_1", ""]}),
                encoding="utf-8",
            )
            client_index.write_text(
                json.dumps({"clients": [{"index": 1, "slot": 1, "name": "Dofus 3.6.10.11 Release 1", "pid": 4101}]}),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps({"characters": {"42": {"name": "Rabmou", "pid": 4101}}}),
                encoding="utf-8",
            )

            characters = load_quest_characters(profile, client_index, 2, binding_path=bindings)

            self.assertEqual(characters[0].label, "Rabmou")
            self.assertEqual(characters[0].key, "character:42")
            self.assertTrue(characters[0].connected)

    def test_character_name_field_hides_class_suffix_and_resolves_network_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            client_index = root / "client_index.json"
            profile.write_text(json.dumps({KEY_SESSION_ORDER: ["alice_eliotrope", ""]}), encoding="utf-8")
            client_index.write_text(
                json.dumps(
                    {
                        "clients": [
                            {
                                "index": 1,
                                "slot": 1,
                                "name": "Alice - Eliotrope",
                                "character_name": "Alice",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bindings = root / "bindings.json"
            bindings.write_text(
                json.dumps({"characters": {"99": {"name": "Alice", "pid": 0}}}),
                encoding="utf-8",
            )

            characters = load_quest_characters(profile, client_index, 2, binding_path=bindings)
            resolver = CharacterSlotResolver(
                profile,
                client_index,
                binding_path=bindings,
                slot_count=2,
            )

            self.assertEqual(characters[0].label, "Alice")
            self.assertEqual(resolver.resolve("Alice").character_key, "character:99")

    def test_new_character_id_gets_separate_dynamic_slot_on_same_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            resolver = self._resolver(
                root,
                ["Alice", ""],
                [{"slot": 1, "character_name": "Bob", "pid": 4101}],
            )

            alice = resolver.resolve_for_session(
                "Alice",
                "tcp:4101:1",
                55,
            )
            bob = resolver.resolve_for_session(
                "Bob",
                "tcp:4101:2",
                66,
            )
            resolver.client_index_path.write_text(
                json.dumps(
                    {"clients": [{"slot": 2, "character_name": "Bob", "pid": 4101}]}
                ),
                encoding="utf-8",
            )
            bob_after_reorder = resolver.resolve_for_session(
                "Bob",
                "tcp:4101:3",
                66,
            )
            alice_again = resolver.resolve_for_session(
                "Alice",
                "tcp:4101:4",
                55,
            )

            self.assertEqual(alice.character_key, "character:55")
            self.assertEqual(bob.character_key, "character:66")
            self.assertEqual(bob_after_reorder.character_key, "character:66")
            self.assertEqual(alice_again.character_key, "character:55")
            payload = json.loads(
                (root / "network_character_bindings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["characters"]["55"]["name"], "Alice")
            self.assertEqual(payload["characters"]["66"]["name"], "Bob")
            self.assertNotIn("slots", payload)

    def test_dynamic_binding_is_listed_and_owns_connected_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            client_index = root / "client_index.json"
            bindings = root / "bindings.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["Alice", ""]}),
                encoding="utf-8",
            )
            client_index.write_text(
                json.dumps(
                    {"clients": [{"slot": 1, "character_name": "Bob", "pid": 4101}]}
                ),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "characters": {
                            "1": {"name": "Alice", "organizer_slot": 1},
                            "2": {"name": "Bob", "organizer_slot": 3},
                        }
                    }
                ),
                encoding="utf-8",
            )

            characters = load_quest_characters(
                profile,
                client_index,
                2,
                binding_path=bindings,
            )
            connected_characters = load_quest_characters(
                profile,
                client_index,
                2,
                binding_path=bindings,
                connected_only=True,
            )

            self.assertEqual([row.key for row in characters], ["character:2", "character:1"])
            self.assertEqual(characters[0].label, "Bob")
            self.assertEqual(characters[1].label, "Alice")
            self.assertTrue(characters[0].connected)
            self.assertFalse(characters[1].connected)
            self.assertEqual(
                [(row.key, row.label) for row in connected_characters],
                [("character:2", "Bob")],
            )

    def test_connected_only_hides_all_empty_and_disconnected_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            client_index = root / "client_index.json"
            bindings = root / "bindings.json"
            profile.write_text(
                json.dumps({KEY_SESSION_ORDER: ["Alice", ""]}),
                encoding="utf-8",
            )
            client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            bindings.write_text(
                json.dumps({"characters": {"1": {"name": "Alice", "organizer_slot": 1}}}),
                encoding="utf-8",
            )

            characters = load_quest_characters(
                profile,
                client_index,
                2,
                binding_path=bindings,
                connected_only=True,
            )

            self.assertEqual(characters, [])

    def test_future_character_never_inherits_progress_from_organizer_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            clients = root / "client_index.json"
            bindings = root / "bindings.json"
            quest_progress = root / "quest_progress.json"
            achievement_progress = root / "achievement_progress.json"
            guide_progress = root / "guide_progress.json"
            profile.write_text(json.dumps({KEY_SESSION_ORDER: ["Ancien", "Eve"]}), encoding="utf-8")
            clients.write_text(
                json.dumps({"clients": [{"slot": 2, "character_name": "Eve", "pid": 16476}]}),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps({"legacy_slots": {"2": {"name": "Ancien", "source": "verified_network_identity"}}}),
                encoding="utf-8",
            )
            quest_progress.write_text(
                json.dumps({"version": 1, "characters": {"slot:2": {"done": {"101": True}}}}),
                encoding="utf-8",
            )
            achievement_progress.write_text(
                json.dumps({"version": 1, "characters": {"slot:2": {"completed_achievements": [7]}}}),
                encoding="utf-8",
            )
            guide_progress.write_text(
                json.dumps({"version": 1, "characters": {"slot:2": {"manual_steps": {"g": ["a"]}}}}),
                encoding="utf-8",
            )
            resolver = CharacterSlotResolver(
                profile,
                clients,
                binding_path=bindings,
                slot_count=8,
                progress_paths=(quest_progress, achievement_progress, guide_progress),
            )

            resolution = resolver.resolve_for_session(
                "Eve",
                "tcp:16476:8",
                77,
            )

            self.assertEqual(resolution.character_key, "character:77")
            for path in (quest_progress, achievement_progress, guide_progress):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("slot:2", payload["characters"])
                self.assertNotIn("character:77", payload["characters"])
            persisted = json.loads(bindings.read_text(encoding="utf-8"))
            self.assertEqual(persisted["characters"]["77"]["name"], "Eve")
            self.assertEqual(persisted["legacy_slots"]["2"]["name"], "Ancien")

    def test_verified_legacy_name_is_migrated_once_to_character_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profiles.json"
            clients = root / "client_index.json"
            bindings = root / "bindings.json"
            progress = root / "quest_progress.json"
            profile.write_text(json.dumps({KEY_SESSION_ORDER: ["Alice"]}), encoding="utf-8")
            clients.write_text(
                json.dumps({"clients": [{"slot": 1, "character_name": "Alice", "pid": 10160}]}),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps({"slots": {"1": {"name": "Alice", "source": "verified_network_identity"}}}),
                encoding="utf-8",
            )
            progress.write_text(
                json.dumps({"version": 1, "characters": {"slot:1": {"done": {"101": True}}}}),
                encoding="utf-8",
            )
            resolver = CharacterSlotResolver(
                profile,
                clients,
                binding_path=bindings,
                progress_paths=(progress,),
            )

            resolution = resolver.resolve_for_session(
                "Alice",
                "tcp:10160:1",
                55,
            )

            self.assertEqual(resolution.character_key, "character:55")
            payload = json.loads(progress.read_text(encoding="utf-8"))
            self.assertNotIn("slot:1", payload["characters"])
            self.assertTrue(payload["characters"]["character:55"]["done"]["101"])
            persisted = json.loads(bindings.read_text(encoding="utf-8"))
            self.assertNotIn("slots", persisted)
            self.assertEqual(persisted["legacy_slots"], {})
            self.assertEqual(persisted["characters"]["55"]["name"], "Alice")


if __name__ == "__main__":
    unittest.main()
