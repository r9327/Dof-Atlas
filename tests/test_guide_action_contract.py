from __future__ import annotations

import unittest

from tools.guide_action_contract import group_consecutive_talks, validate_actions
from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionContractTests(unittest.TestCase):
    def test_drop_requires_purchase_alternative(self) -> None:
        violations = validate_actions([GuideAction(GuideActionType.DROP, item_id=42)])
        self.assertEqual([row.code for row in violations], ["drop_without_purchase_alternative"])

    def test_preparation_and_runtime_action_are_not_duplicated(self) -> None:
        actions = [
            GuideAction(GuideActionType.BUY, item_id=42, requires_preparation=True),
            GuideAction(GuideActionType.BUY, item_id=42),
        ]
        self.assertIn("preparation_action_duplicate", [row.code for row in validate_actions(actions)])

    def test_consecutive_same_npc_talks_group_and_are_hard_violation_until_collapsed(self) -> None:
        actions = [
            GuideAction(GuideActionType.TALK, actor_id=7, map_id=10, quest_ids=(1,)),
            GuideAction(GuideActionType.TALK, actor_id=7, map_id=10, quest_ids=(2,)),
            GuideAction(GuideActionType.TRAVEL, map_id=11),
        ]
        groups = group_consecutive_talks(actions)
        self.assertEqual([len(group) for group in groups], [2, 1])
        self.assertIn("consecutive_talks_not_grouped", [row.code for row in validate_actions(actions)])

    def test_semantic_targets_are_required(self) -> None:
        self.assertIn("talk_without_actor", [row.code for row in validate_actions([GuideAction(GuideActionType.TALK)])])
        self.assertIn("item_action_without_item", [row.code for row in validate_actions([GuideAction(GuideActionType.BUY)])])
        self.assertIn("fight_without_monster", [row.code for row in validate_actions([GuideAction(GuideActionType.FIGHT)])])

    def test_quantity_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            GuideAction(GuideActionType.FIGHT, monster_id=99, quantity=0)


if __name__ == "__main__":
    unittest.main()
