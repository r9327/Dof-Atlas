from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_card_auto_validation_contract,
    build_route_auto_validation_contract,
)


class GuideAutoValidationMinimumQuantityTests(unittest.TestCase):
    def test_minimum_quantity_is_normalized_as_quantified_item_target(self) -> None:
        card = {
            "index": 1,
            "manual_source": True,
            "manual_chapter_id": "level_70_100",
            "manual_stage_id": "L70-10H",
            "manual_quest_ids": [],
            "manual_quest_names": ["Faire le mort"],
            "manual_success_names": [],
            "a_preparer": [
                {
                    "name": "Bière Atolmond",
                    "minimum_quantity": 3,
                    "for": "Faire le mort",
                }
            ],
            "manual_lines": [],
            "manual_stage_data": {"id": "L70-10H"},
        }

        row = build_card_auto_validation_contract(card)
        self.assertEqual(len(row["items"]), 1)
        self.assertEqual(row["items"][0]["minimum_quantity"], 3)
        self.assertEqual(row["items"][0]["quantity"], 3)

        route = build_route_auto_validation_contract([card])
        stock = route["inventory_plan"]["items"]
        self.assertEqual(len(stock), 1)
        self.assertEqual(stock[0]["required_quantity"], 3)
        self.assertEqual(stock[0]["quantified_target_count"], 1)
        self.assertEqual(stock[0]["unquantified_target_count"], 0)


if __name__ == "__main__":
    unittest.main()
