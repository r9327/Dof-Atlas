from __future__ import annotations

import unittest

from app.core.character_identity import (
    character_id_from_key,
    character_key,
    is_character_key,
)
from app.network.character_resolver import CharacterSlotResolver
from app.services.character_data_service import CharacterDataService


class CharacterIdentityContractTests(unittest.TestCase):
    def test_character_key_is_the_single_canonical_business_format(self) -> None:
        self.assertEqual(character_key(101), "character:101")
        self.assertEqual(character_key("101"), "character:101")
        self.assertEqual(character_id_from_key("character:101"), 101)
        self.assertTrue(is_character_key("character:101"))

        for legacy_or_invalid in (
            "slot:1",
            "legacy_slots:1",
            "101",
            "Alpha",
            "character:0",
            "character:-1",
            "character:001",
            "",
            None,
        ):
            self.assertIsNone(character_id_from_key(legacy_or_invalid))
            self.assertFalse(is_character_key(legacy_or_invalid))

        for invalid_id in (0, -1, True, 1.5, "1.0", ""):
            with self.assertRaises(ValueError):
                character_key(invalid_id)

    def test_runtime_resolver_uses_the_shared_canonical_builder(self) -> None:
        for character_id in (1, 101, 999999999):
            self.assertEqual(
                CharacterSlotResolver.character_key(character_id),
                character_key(character_id),
            )

    def test_character_deletion_parser_rejects_legacy_identity(self) -> None:
        self.assertEqual(CharacterDataService._character_id("character:101"), 101)
        self.assertIsNone(CharacterDataService._character_id("slot:1"))
        self.assertIsNone(CharacterDataService._character_id("character:001"))


if __name__ == "__main__":
    unittest.main()
