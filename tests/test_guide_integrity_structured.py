from __future__ import annotations

import unittest

from tools.guide_action_model import GuideAction, GuideActionType
from tools.guide_integrity_structured import validate_runtime_lines, validate_structured_actions


class GuideIntegrityStructuredTests(unittest.TestCase):
    def test_clean_structured_action_passes(self) -> None:
        result = validate_structured_actions([GuideAction(GuideActionType.TALK, actor_id=1)])
        self.assertEqual(result["hard_error_count"], 0)

    def test_structured_violation_is_hard(self) -> None:
        result = validate_structured_actions([GuideAction(GuideActionType.DROP, item_id=1)])
        self.assertEqual(result["hard_error_count"], 1)
        self.assertEqual(result["hard_errors"][0]["code"], "drop_without_purchase_alternative")

    def test_runtime_payload_uses_same_contract(self) -> None:
        action = GuideAction(
            GuideActionType.DROP,
            item_id=42,
            quantity=2,
            purchase_alternative=True,
            quest_ids=(10, 11),
        )
        report = validate_runtime_lines([{"guide_actions": [action.to_payload()]}])
        self.assertEqual(report["structured_line_count"], 1)
        self.assertEqual(report["action_count"], 1)
        self.assertEqual(report["hard_error_count"], 0)

    def test_unstructured_runtime_line_is_not_regex_promoted_to_hard(self) -> None:
        report = validate_runtime_lines([{"kind": "action", "text": "Drop cette ressource."}])
        self.assertEqual(report["structured_line_count"], 0)
        self.assertEqual(report["hard_error_count"], 0)


if __name__ == "__main__":
    unittest.main()
