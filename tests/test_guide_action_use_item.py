from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionUseItemTests(unittest.TestCase):
    def test_use_item_keeps_quantity(self) -> None:
        action = GuideAction(GuideActionType.USE_ITEM, item_id=44, quantity=2)
        self.assertEqual(action.quantity, 2)


if __name__ == "__main__":
    unittest.main()
