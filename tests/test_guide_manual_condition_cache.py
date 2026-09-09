from __future__ import annotations

import unittest
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)


class _CountingCards(list):
    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


class GuideManualConditionCacheTests(unittest.TestCase):
    @staticmethod
    def service(**attributes):
        service = object.__new__(GuideUltimeManualRuntimeService)
        for name, value in attributes.items():
            setattr(service, name, value)
        return service

    def test_success_ids_use_prebuilt_contract_without_full_provider_fallback(self) -> None:
        card = {
            "manual_source": True,
            "manual_chapter_id": "chapter",
            "manual_stage_id": "stage",
            "index": 1,
        }
        service = self.service(
            auto_validation_contract={
                "cards": [
                    {
                        "card_key": "manual:chapter:stage",
                        "successes": [
                            {"achievement_id": 101},
                            {"achievement_id": None},
                            {"achievement_id": 202},
                        ],
                    }
                ]
            },
            card_key=lambda _card, _fallback=0: "manual:chapter:stage",
        )

        result = service.card_success_ids(card)

        self.assertEqual(result, (101, 202))

    def test_success_ids_keep_legacy_fallback_without_contract(self) -> None:
        service = self.service(auto_validation_contract=None)
        card = {"manual_source": True, "index": 1}
        with patch.object(
            GuideUltimeManualRuntimeService,
            "_card_success_ids_uncached",
            return_value=(303,),
        ) as fallback:
            result = service.card_success_ids(card)

        self.assertEqual(result, (303,))
        fallback.assert_called_once_with(card)

    def test_order_gate_is_computed_once_per_static_card(self) -> None:
        service = self.service()
        card = {
            "manual_chapter_id": "chapter",
            "manual_stage_id": "stage",
            "index": 1,
        }
        gate = {"rank": 20}
        with patch.object(
            GuideUltimeManualRuntimeService,
            "_manual_order_gate_for_card_uncached",
            return_value=gate,
        ) as resolver:
            first = service.manual_order_gate_for_card(card)
            second = service.manual_order_gate_for_card(card)

        self.assertIs(first, gate)
        self.assertIs(second, gate)
        resolver.assert_called_once_with(card)

    def test_class_gate_negative_result_is_cached(self) -> None:
        service = self.service()
        card = {
            "manual_chapter_id": "chapter",
            "manual_stage_id": "stage",
            "index": 1,
        }
        with patch.object(
            GuideUltimeManualRuntimeService,
            "_manual_class_gate_for_card_uncached",
            return_value=None,
        ) as resolver:
            self.assertIsNone(service.manual_class_gate_for_card(card))
            self.assertIsNone(service.manual_class_gate_for_card(card))

        resolver.assert_called_once_with(card)

    def test_ocre_unlock_transition_is_scanned_once(self) -> None:
        cards = _CountingCards(
            [
                {
                    "index": 1,
                    "manual_stage_data": {},
                },
                {
                    "index": 4,
                    "manual_stage_data": {"capture_transition": "unlock"},
                },
                {
                    "index": 8,
                    "manual_stage_data": {},
                },
            ]
        )
        service = self.service(cards=cards)

        before = service._ocre_capture_unlocked_for_card(cards[0])
        after = service._ocre_capture_unlocked_for_card(cards[2])

        self.assertFalse(before)
        self.assertTrue(after)
        self.assertEqual(cards.iterations, 1)


if __name__ == "__main__":
    unittest.main()
