from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionMonsterQuantityTests(unittest.TestCase):
    def test_fight_quantity_is_structured(self) -> None:
        action = GuideAction(GuideActionType.FIGHT, monster_id=99, quantity=4)
        self.assertEqual(action.monster_id, 99)
        self.assertEqual(action.quantity, 4)


if __name__ == "__main__":
    unittest.main()
