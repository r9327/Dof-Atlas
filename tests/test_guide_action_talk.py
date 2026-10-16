from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionTalkTests(unittest.TestCase):
    def test_talk_targets_actor(self) -> None:
        action = GuideAction(GuideActionType.TALK, actor_id=55)
        self.assertEqual(action.canonical_target, ("actor", 55))


if __name__ == "__main__":
    unittest.main()
