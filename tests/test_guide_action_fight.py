from __future__ import annotations
import unittest
from tools.guide_action_model import GuideAction, GuideActionType
class GuideActionFightTests(unittest.TestCase):
    def test_target(self):
        self.assertEqual(GuideAction(GuideActionType.FIGHT, monster_id=1).canonical_target, ("monster", 1))
