from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionInteractTests(unittest.TestCase):
    def test_interact_keeps_map_target(self) -> None:
        action = GuideAction(GuideActionType.INTERACT, map_id=88)
        self.assertEqual(action.canonical_target, ("map", 88))


if __name__ == "__main__":
    unittest.main()
