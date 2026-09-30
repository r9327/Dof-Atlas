from __future__ import annotations

import unittest

from tools.guide_action_contract import validate_actions
from tools.guide_action_model import GuideAction, GuideActionType


class GuideActionDropContractTests(unittest.TestCase):
    def test_drop_purchase_alternative_is_structured_not_textual(self) -> None:
        good = GuideAction(GuideActionType.DROP, item_id=100, quantity=2, purchase_alternative=True)
        bad = GuideAction(GuideActionType.DROP, item_id=100, quantity=2, purchase_alternative=False)
        self.assertEqual(validate_actions([good]), [])
        self.assertEqual(validate_actions([bad])[0].code, "drop_without_purchase_alternative")


if __name__ == "__main__":
    unittest.main()
