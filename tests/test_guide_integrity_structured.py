from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType
from tools.guide_integrity_structured import validate_structured_actions


class GuideIntegrityStructuredTests(unittest.TestCase):
    def test_clean_structured_action_passes(self) -> None:
        result = validate_structured_actions([GuideAction(GuideActionType.TALK, actor_id=1)])
        self.assertEqual(result["hard_error_count"], 0)

    def test_structured_violation_is_hard(self) -> None:
        result = validate_structured_actions([GuideAction(GuideActionType.DROP, item_id=1)])
        self.assertEqual(result["hard_error_count"], 1)
        self.assertEqual(result["hard_errors"][0]["code"], "drop_without_purchase_alternative")


if __name__ == "__main__":
    unittest.main()
