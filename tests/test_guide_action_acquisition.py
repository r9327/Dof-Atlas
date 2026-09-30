from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionAcquisitionTests(unittest.TestCase):
    def test_acquisition_timing_is_explicit(self) -> None:
        action = GuideAction(
            GuideActionType.BUY,
            item_id=5,
            primary_acquisition="npc",
            natural_acquisition_step="stage-4",
            first_use_step="stage-9",
        )
        self.assertEqual(action.natural_acquisition_step, "stage-4")
        self.assertEqual(action.first_use_step, "stage-9")
        self.assertFalse(action.requires_preparation)


if __name__ == "__main__":
    unittest.main()
