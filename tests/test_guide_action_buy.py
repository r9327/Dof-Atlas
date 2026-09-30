from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionBuyTests(unittest.TestCase):
    def test_buy_targets_item(self) -> None:
        action = GuideAction(GuideActionType.BUY, item_id=66)
        self.assertEqual(action.canonical_target, ("item", 66))


if __name__ == "__main__":
    unittest.main()
