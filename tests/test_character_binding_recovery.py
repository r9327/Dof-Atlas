from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.character_resolver import (
    CharacterSlotResolver,
    merge_verified_binding_classes,
)
from app.services.character_data_service import CharacterDataService


class CharacterBindingRecoveryTests(unittest.TestCase):
    @staticmethod
    def _resolver(root: Path) -> CharacterSlotResolver:
        return CharacterSlotResolver(
            profile_path=root / "profiles.json",
            client_index_path=root / "client_index.json",
            binding_path=root / "network_character_bindings.json",
            progress_paths=(),
        )

    def test_missing_binding_accepts_first_verified_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / "network_character_bindings.json"

            resolution = self._resolver(root).resolve_for_session(
                "Alpha", "tcp:101:1", character_id=42
            )

            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.character_key, "character:42")
            payload = json.loads(binding.read_text(encoding="utf-8"))
            self.assertEqual(payload["characters"]["42"]["name"], "Alpha")

    def test_valid_empty_binding_accepts_first_verified_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / "network_character_bindings.json"
            binding.write_bytes(b"{}")

            resolution = self._resolver(root).resolve_for_session(
                "Alpha", "tcp:101:1", character_id=42
            )

            self.assertIsNotNone(resolution)
            payload = json.loads(binding.read_text(encoding="utf-8"))
            self.assertEqual(payload["characters"]["42"]["name"], "Alpha")

    def test_unreadable_binding_survives_detection_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / "network_character_bindings.json"
            original = b'{"characters":{"7":{"name":"Old"}}'
            binding.write_bytes(original)

            first = self._resolver(root).resolve_for_session(
                "New", "tcp:202:1", character_id=99
            )
            restarted = self._resolver(root).resolve_for_session(
                "New", "tcp:202:2", character_id=99
            )

            self.assertIsNone(first)
            self.assertIsNone(restarted)
            self.assertEqual(binding.read_bytes(), original)
            backups = list(binding.parent.glob(f"{binding.name}.corrupt.*.bak"))
            self.assertGreaterEqual(len(backups), 1)
            self.assertTrue(all(path.read_bytes() == original for path in backups))

    def test_schema_invalid_binding_cannot_be_replaced_by_any_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = root / "network_character_bindings.json"
            original = b'{"characters":[],"legacy_slots":{}}'
            binding.write_bytes(original)

            detected = self._resolver(root).resolve_for_session(
                "New", "tcp:202:1", character_id=99
            )
            enriched = merge_verified_binding_classes(
                binding,
                {"New": {"cra"}},
                {"cra"},
            )
            deleted = CharacterDataService(
                profile_path=root / "profiles.json",
                binding_path=binding,
                quest_progress_path=root / "quests.json",
                achievement_progress_path=root / "achievements.json",
                guide_progress_path=root / "guides.json",
            ).delete_character("character:99")

            self.assertIsNone(detected)
            self.assertFalse(enriched)
            self.assertFalse(deleted)
            self.assertEqual(binding.read_bytes(), original)
            backups = list(binding.parent.glob(f"{binding.name}.corrupt.*.bak"))
            self.assertGreaterEqual(len(backups), 1)
            self.assertTrue(all(path.read_bytes() == original for path in backups))


if __name__ == "__main__":
    unittest.main()
