from __future__ import annotations

import unittest
from unittest.mock import patch

from app.modules.encyclopedia.services import guide_auto_validation_contract


class GuideAutoValidationCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        guide_auto_validation_contract.clear_auto_validation_contract_cache()

    @staticmethod
    def manual_cards() -> list[dict[str, object]]:
        return [
            {
                "manual_source": True,
                "_manual_route_cacheable": True,
                "manual_chapter_id": "chapter",
                "manual_stage_id": "stage",
                "index": 1,
            }
        ]

    def test_same_manual_route_and_provider_reuses_contract(self) -> None:
        cards = self.manual_cards()
        provider = object()
        calls = 0

        def builder(_cards, *, achievement_provider=None):
            nonlocal calls
            calls += 1
            return {"call": calls, "provider": achievement_provider}

        with (
            patch.object(
                guide_auto_validation_contract,
                "_manual_cards_signature",
                return_value=("route", 1),
            ),
            patch.object(
                guide_auto_validation_contract,
                "_achievement_provider_signature",
                return_value=("provider", 1),
            ),
            patch.object(
                guide_auto_validation_contract,
                "_build_route_auto_validation_contract_uncached",
                side_effect=builder,
            ),
        ):
            first = guide_auto_validation_contract.build_route_auto_validation_contract(
                cards,
                achievement_provider=provider,
            )
            second = guide_auto_validation_contract.build_route_auto_validation_contract(
                cards,
                achievement_provider=provider,
            )

        self.assertIs(first, second)
        self.assertEqual(calls, 1)

    def test_route_revision_change_invalidates_contract(self) -> None:
        cards = self.manual_cards()
        calls = 0

        def builder(_cards, *, achievement_provider=None):
            nonlocal calls
            calls += 1
            return {"call": calls}

        with (
            patch.object(
                guide_auto_validation_contract,
                "_manual_cards_signature",
                side_effect=[("route", 1), ("route", 2)],
            ),
            patch.object(
                guide_auto_validation_contract,
                "_achievement_provider_signature",
                return_value=("provider", 1),
            ),
            patch.object(
                guide_auto_validation_contract,
                "_build_route_auto_validation_contract_uncached",
                side_effect=builder,
            ),
        ):
            first = guide_auto_validation_contract.build_route_auto_validation_contract(cards)
            second = guide_auto_validation_contract.build_route_auto_validation_contract(cards)

        self.assertEqual((first["call"], second["call"]), (1, 2))
        self.assertEqual(calls, 2)

    def test_provider_revision_change_invalidates_contract(self) -> None:
        cards = self.manual_cards()
        calls = 0

        def builder(_cards, *, achievement_provider=None):
            nonlocal calls
            calls += 1
            return {"call": calls}

        with (
            patch.object(
                guide_auto_validation_contract,
                "_manual_cards_signature",
                return_value=("route", 1),
            ),
            patch.object(
                guide_auto_validation_contract,
                "_achievement_provider_signature",
                side_effect=[("provider", 1), ("provider", 2)],
            ),
            patch.object(
                guide_auto_validation_contract,
                "_build_route_auto_validation_contract_uncached",
                side_effect=builder,
            ),
        ):
            first = guide_auto_validation_contract.build_route_auto_validation_contract(cards)
            second = guide_auto_validation_contract.build_route_auto_validation_contract(cards)

        self.assertEqual((first["call"], second["call"]), (1, 2))
        self.assertEqual(calls, 2)

    def test_generated_route_bypasses_manual_contract_cache(self) -> None:
        cards = [{"index": 1}]
        calls = 0

        def builder(_cards, *, achievement_provider=None):
            nonlocal calls
            calls += 1
            return {"call": calls}

        with patch.object(
            guide_auto_validation_contract,
            "_build_route_auto_validation_contract_uncached",
            side_effect=builder,
        ):
            first = guide_auto_validation_contract.build_route_auto_validation_contract(cards)
            second = guide_auto_validation_contract.build_route_auto_validation_contract(cards)

        self.assertEqual((first["call"], second["call"]), (1, 2))
        self.assertEqual(calls, 2)

    def test_synthetic_manual_cards_with_same_ids_do_not_share_stale_contract(self) -> None:
        first_card = self.manual_cards()[0]
        second_card = self.manual_cards()[0]
        first_card.pop("_manual_route_cacheable")
        second_card.pop("_manual_route_cacheable")
        first_card["manual_stage_data"] = {"dungeon": {"name": "First"}}
        second_card["manual_stage_data"] = {"dungeon": {"name": "Second"}}

        first = guide_auto_validation_contract.build_route_auto_validation_contract([first_card])
        second = guide_auto_validation_contract.build_route_auto_validation_contract([second_card])

        self.assertEqual(first["cards"][0]["dungeons"][0]["name"], "First")
        self.assertEqual(second["cards"][0]["dungeons"][0]["name"], "Second")


if __name__ == "__main__":
    unittest.main()
