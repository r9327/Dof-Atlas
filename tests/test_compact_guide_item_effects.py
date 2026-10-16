from __future__ import annotations

import unittest

from app.modules.encyclopedia.providers.dofus_item_provider import (
    _EFFECT_CANDIDATE_ROW,
    _selected_effect_instances,
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


if __name__ == "__main__":
    unittest.main()
