from __future__ import annotations
import unittest
from tools.guide_action_model import GuideAction, GuideActionType
class GuideActionQuantityTests(unittest.TestCase):
    def test_default_quantity(self):
        self.assertEqual(GuideAction(GuideActionType.TALK, actor_id=1).quantity, 1)
