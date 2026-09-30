from __future__ import annotations

import unittest

from tools.guide_action_contract import group_consecutive_talks, validate_actions
from tools.guide_action_model import GuideAction, GuideActionType


class GuideStructuredOfficialRulesTests(unittest.TestCase):
    def test_drop_with_purchase_alternative_is_valid(self) -> None:
        action = GuideAction(GuideActionType.DROP, item_id=1, purchase_alternative=True)
        self.assertEqual(validate_actions([action]), [])

    def test_natural_purchase_is_not_preparation(self) -> None:
        action = GuideAction(GuideActionType.BUY, item_id=1, natural_acquisition_step="stage-10")
        self.assertFalse(action.requires_preparation)

    def test_same_npc_multiquest_interaction_is_groupable(self) -> None:
        groups = group_consecutive_talks([
            GuideAction(GuideActionType.TALK, actor_id=10, map_id=20, quest_ids=(1,)),
            GuideAction(GuideActionType.TALK, actor_id=10, map_id=20, quest_ids=(2, 3)),
        ])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)


if __name__ == "__main__":
    unittest.main()
