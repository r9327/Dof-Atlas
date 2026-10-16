from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionQuestLinksTests(unittest.TestCase):
    def test_one_action_can_reference_multiple_quests(self) -> None:
        action = GuideAction(GuideActionType.TALK, actor_id=7, quest_ids=(10, 11, 12))
        self.assertEqual(action.quest_ids, (10, 11, 12))


if __name__ == "__main__":
    unittest.main()
