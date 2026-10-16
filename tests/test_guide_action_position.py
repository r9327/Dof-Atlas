from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionPositionTests(unittest.TestCase):
    def test_position_is_semantic_metadata_not_rendered_contract(self) -> None:
        action = GuideAction(GuideActionType.TRAVEL, map_id=123, position="[1,-2]")
        self.assertEqual(action.map_id, 123)
        self.assertEqual(action.position, "[1,-2]")


if __name__ == "__main__":
    unittest.main()
