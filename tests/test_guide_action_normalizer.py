from __future__ import annotations

import unittest

from tools.guide_action_model import GuideActionType
from tools.guide_action_normalizer import normalize_action


class GuideActionNormalizerTests(unittest.TestCase):
    def test_normalizes_runtime_payload(self) -> None:
        action = normalize_action({"action_type": "fight", "monster_id": 7, "quantity": 3, "quest_ids": [1, 2]})
        self.assertIs(action.action_type, GuideActionType.FIGHT)
        self.assertEqual(action.quantity, 3)
        self.assertEqual(action.quest_ids, (1, 2))

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_action({"action_type": "regex_magic"})


if __name__ == "__main__":
    unittest.main()
