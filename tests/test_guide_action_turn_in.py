from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionTurnInTests(unittest.TestCase):
    def test_turn_in_targets_item(self) -> None:
        action = GuideAction(GuideActionType.TURN_IN, item_id=8, actor_id=3)
        self.assertEqual(action.canonical_target, ("item", 8))


if __name__ == "__main__":
    unittest.main()
