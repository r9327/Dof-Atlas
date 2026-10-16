from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionPreparationContractTests(unittest.TestCase):
    def test_natural_acquisition_cannot_be_preparation(self) -> None:
        with self.assertRaises(ValueError):
            GuideAction(
                GuideActionType.BUY,
                item_id=100,
                natural_acquisition_step="npc:tavernier@stage-8",
                first_use_step="stage-12",
                requires_preparation=True,
            )


if __name__ == "__main__":
    unittest.main()
