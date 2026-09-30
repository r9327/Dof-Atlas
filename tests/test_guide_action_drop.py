from __future__ import annotations
import unittest
from tools.guide_action_model import GuideAction, GuideActionType
class GuideActionDropTests(unittest.TestCase):
    def test_target(self):
        self.assertEqual(GuideAction(GuideActionType.DROP, item_id=1).canonical_target, ("item", 1))
