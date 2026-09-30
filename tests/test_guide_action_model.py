from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionModelTests(unittest.TestCase):
    def test_canonical_targets_are_structured(self) -> None:
        self.assertEqual(GuideAction(GuideActionType.TALK, actor_id=12).canonical_target, ("actor", 12))
        self.assertEqual(GuideAction(GuideActionType.FIGHT, monster_id=34).canonical_target, ("monster", 34))
        self.assertEqual(GuideAction(GuideActionType.BUY, item_id=56).canonical_target, ("item", 56))

    def test_natural_acquisition_is_not_preparation(self) -> None:
        with self.assertRaises(ValueError):
            GuideAction(
                GuideActionType.BUY,
                item_id=56,
                natural_acquisition_step="map:10",
                requires_preparation=True,
            )


if __name__ == "__main__":
    unittest.main()
