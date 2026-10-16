from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionCanonicalTargetTests(unittest.TestCase):
    def test_use_item_targets_item(self) -> None:
        self.assertEqual(GuideAction(GuideActionType.USE_ITEM, item_id=4).canonical_target, ("item", 4))


if __name__ == "__main__":
    unittest.main()
