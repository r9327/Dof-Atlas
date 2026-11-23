"""Legacy Craft quantity compatibility for Quest preparation, without a game runtime."""
from __future__ import annotations

import unittest

from app.pages._quests_page_impl import normalize_owned_items, owned_item_identifier


class OwnedItemsNormalizationTests(unittest.TestCase):
    def test_row_ids_keep_ankama_priority_and_legacy_boolean_conversion(self):
        self.assertEqual(owned_item_identifier({"ankama_id": "42", "item_id": 51}), 42)
        self.assertEqual(owned_item_identifier({"ankama_id": 0, "item_id": "51"}), 51)
        self.assertEqual(owned_item_identifier({"item_id": True}), 1)
        self.assertIsNone(owned_item_identifier({"ankama_id": "invalid", "item_id": 51}))

    def test_item_list_aggregates_only_valid_positive_quantities(self):
        payload = {"items": [
            {"item_id": "42", "quantity": "2"},
            {"ankama_id": 42, "quantity": 3},
            {"item_id": "51", "quantity": True},
            {"item_id": "51", "quantity": "-8"},
            {"item_id": 99, "quantity": "invalid"},
            {"item_id": None, "quantity": 15},
        ]}
        self.assertEqual(normalize_owned_items(payload), {42: 5, 51: 1})

    def test_legacy_dictionary_and_invalid_payload(self):
        self.assertEqual(normalize_owned_items({
            "8": {"quantity": "4"}, "9": {"quantity": 0}, "bad": {"quantity": 2},
        }), {8: 4})
        self.assertEqual(normalize_owned_items(None), {})
        self.assertEqual(normalize_owned_items({"items": [None, 15]}), {})


if __name__ == "__main__":
    unittest.main()
