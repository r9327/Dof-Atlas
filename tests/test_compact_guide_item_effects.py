from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.providers.dofus_item_provider import (
    _EFFECT_CANDIDATE_ROW,
    _selected_effect_instances,
    _read_guide_items_index,
)


class CompactGuideItemEffectTests(unittest.TestCase):
    def test_compact_effects_keep_requested_values_and_last_duplicate(self) -> None:
        packed = bytearray()
        for row in (
            (41, 5, 8, 6, -17),
            (99, 6, 40, 0, 23),
            (41, 7, 0, -3, 0),
            (78, 8, 6, 2, 30),
        ):
            packed.extend(_EFFECT_CANDIDATE_ROW.pack(*row))
        self.assertEqual(
            _selected_effect_instances(packed, {41, 78, 12345}),
            {
                41: {"effectId": 7, "diceNum": 0, "diceSide": -3, "value": 0},
                78: {"effectId": 8, "diceNum": 6, "diceSide": 2, "value": 30},
            },
        )
        self.assertEqual(_selected_effect_instances(packed, set()), {})
        self.assertEqual(_selected_effect_instances(bytearray(), {41}), {})

    def test_compact_effects_keep_signed_64bit_source_values(self) -> None:
        packed = _EFFECT_CANDIDATE_ROW.pack(456, 123, -(2**40), 2**40, -1)
        self.assertEqual(
            _selected_effect_instances(packed, {456})[456],
            {
                "effectId": 123,
                "diceNum": -(2**40),
                "diceSide": 2**40,
                "value": -1,
            },
        )


class CompactGuideItemIndexIntegrityTests(unittest.TestCase):
    def test_valid_items_and_malformed_rows_are_not_silently_dropped(self):
        from app.modules.encyclopedia.providers import dofus_item_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide_items.json"
            valid = {
                "schema_version": mod._GUIDE_ITEMS_INDEX_SCHEMA,
                "source_signature": [["items.json", 23, 45]],
                "items": {
                    "42": {"id": 42, "name": "Item"},
                    "99": {"id": 99, "name": "Second"},
                },
            }
            with patch.object(mod, "_guide_item_source_signature",
                              return_value=valid["source_signature"]):
                path.write_text(json.dumps(valid), encoding="utf-8")
                self.assertEqual(
                    set(_read_guide_items_index(path=path)), {42, 99},
                )
                for bad in (
                    {"items": {}},
                    {"items": {"42": {"id": 99}}},
                    {"items": {"42": {"id": True}}},
                    {"items": {"42": "invalid"}},
                    {"items": {"042": {"id": 42}}},
                    {"items": {"false": {"id": 42}}},
                    {"items": {"0": {"id": 0}}},
                    {"items": {"42": {"id": 42}, "042": {"id": 42}}},
                    {"schema_version": True},
                    {"source_signature": []},
                ):
                    with self.subTest(bad=bad):
                        path.write_text(json.dumps({**valid, **bad}), encoding="utf-8")
                        self.assertIsNone(_read_guide_items_index(path=path))
                path.write_text("{broken", encoding="utf-8")
                self.assertIsNone(_read_guide_items_index(path=path))


if __name__ == "__main__":
    unittest.main()
