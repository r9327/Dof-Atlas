from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionTravelTests(unittest.TestCase):
    def test_travel_targets_map(self) -> None:
        action = GuideAction(GuideActionType.TRAVEL, map_id=77)
        self.assertEqual(action.canonical_target, ("map", 77))


if __name__ == "__main__":
    unittest.main()
