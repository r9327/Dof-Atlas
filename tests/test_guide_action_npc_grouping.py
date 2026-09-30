from __future__ import annotations

import unittest

from tools.guide_action_contract import group_consecutive_talks
from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionNpcGroupingTests(unittest.TestCase):
    def test_different_maps_do_not_group_same_actor(self) -> None:
        groups = group_consecutive_talks([
            GuideAction(GuideActionType.TALK, actor_id=1, map_id=10),
            GuideAction(GuideActionType.TALK, actor_id=1, map_id=11),
        ])
        self.assertEqual(len(groups), 2)


if __name__ == "__main__":
    unittest.main()
