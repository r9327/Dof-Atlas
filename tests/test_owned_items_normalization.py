"""Legacy Craft quantity compatibility for Quest preparation, without a game runtime."""
from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from app.pages._quests_page_impl import normalize_owned_items, owned_item_identifier
from app.core.craft_selection import (
    selection_item_id, selection_item_row, iter_selection_item_rows,
)


class OwnedItemsNormalizationTests(unittest.TestCase):
    def test_common_selection_reader_keeps_legacy_mapping_quest_only(self):
        payload = {"8": {"quantity": 3}, "9": "invalid"}
        self.assertEqual(list(iter_selection_item_rows(payload)), [])
        self.assertEqual(list(iter_selection_item_rows(payload, allow_legacy=True)), [
            {"item_id": "8", "quantity": 3},
            {"item_id": "9", "quantity": 0},
        ])
        self.assertEqual(
            list(iter_selection_item_rows({"items": [None, {"item_id": 8}, 11]})),
            [{"item_id": 8}],
        )
        self.assertEqual(list(iter_selection_item_rows(None, allow_legacy=True)), [])

    def test_quest_quantity_save_uses_shared_filtered_rows_without_losing_metadata(self):
        from app.pages._quests_page_impl import save_owned_item_quantity

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "craft-selection.json"
            path.write_text(json.dumps({"items": [
                None, {"item_id": 8, "quantity": 2, "custom": "keep"},
                17, {"item_id": 12, "quantity": 9},
            ]}), encoding="utf-8")
            save_owned_item_quantity({"item_id": 8, "name": "Cawotte"}, 5, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved, {"items": [
                {"item_id": 8, "ankama_id": 8, "name": "Cawotte",
                 "quantity": 5, "custom": "keep"},
                {"item_id": 12, "quantity": 9},
            ]})

    def test_shared_craft_saved_row_preserves_order_and_alias(self):
        self.assertEqual(
            selection_item_row(42, "Cawotte", 7),
            {"item_id": 42, "ankama_id": 42, "name": "Cawotte", "quantity": 7},
        )
        self.assertEqual(
            list(selection_item_row(42, "Cawotte", 7)),
            ["item_id", "ankama_id", "name", "quantity"],
        )

    def test_quest_and_craft_reuse_one_identifier_codec(self):
        self.assertIs(owned_item_identifier, selection_item_id)
        self.assertIsNone(selection_item_id({"ankama_id": "invalid", "item_id": 42}))
        self.assertEqual(selection_item_id({"ankama_id": "", "item_id": 42}), 42)

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
