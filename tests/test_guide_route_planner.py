from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.adventure_route_engine import (
    AdventureRouteEngine,
    ItemRequirement,
    RouteAction,
    RouteLocation,
    RouteProgress,
)
from app.modules.encyclopedia.services.guide_route_planner import (
    CaptureKind,
    GuideCaptureRequirement,
    GuideParticipantState,
    GuideRoutePlanner,
    TravelMode,
    VerifiedZaapRoute,
    schedule_success_passes,
)


DESTINATION = RouteLocation(map_id=10, x=5, y=-2, zone="Amakna")


def _engine() -> AdventureRouteEngine:
    return AdventureRouteEngine(
        [
            RouteAction(
                "quest:start",
                1,
                "Prendre — Première mission",
                "start",
                location=DESTINATION,
                activates_quest=True,
                item_requirements=(ItemRequirement(100, "Clef précise", 2, True),),
            ),
            RouteAction(
                "quest:capture",
                1,
                "Capturer la cible",
                "combat",
                location=RouteLocation(map_id=11, x=6, y=-2, zone="Amakna"),
                prerequisites_actions=frozenset({"quest:start"}),
                monster_ids=frozenset({99}),
                monster_names=("Cible exacte",),
            ),
        ]
    )


class GuideRoutePlannerTests(unittest.TestCase):
    def test_zero_selected_characters_is_empty_not_an_error(self) -> None:
        plan = GuideRoutePlanner(_engine()).plan([])
        self.assertEqual(plan.participants, ())
        self.assertEqual(plan.activities, ())
        self.assertEqual(plan.stock, ())
        self.assertEqual(
            [issue.code for issue in plan.issues],
            ["no_selected_participants"],
        )

    def test_progress_and_stock_stay_per_character(self) -> None:
        plan = GuideRoutePlanner(_engine()).plan(
            [
                GuideParticipantState(
                    "character:1",
                    progress=RouteProgress(owned_items={100: 1}),
                ),
                GuideParticipantState(
                    "character:2",
                    progress=RouteProgress(
                        active_quest_ids={1},
                        completed_action_ids={"quest:start"},
                        owned_items={100: 9},
                    ),
                ),
            ]
        )
        by_action = {row.action.action_id: row for row in plan.activities}
        self.assertEqual(by_action["quest:start"].participant_keys, ("character:1",))
        self.assertEqual(
            by_action["quest:capture"].participant_keys,
            ("character:1", "character:2"),
        )
        self.assertEqual(plan.stock[0].required_by_character, {"character:1": 2})
        self.assertEqual(plan.stock[0].remaining_by_character, {"character:1": 1})

    def test_zaap_requires_verified_route_and_every_participant(self) -> None:
        participants = [
            GuideParticipantState("character:1", world="Monde des Douze"),
            GuideParticipantState("character:2", world="Monde des Douze"),
        ]
        incomplete = VerifiedZaapRoute(
            destination=DESTINATION,
            zaap=RouteLocation(map_id=2, x=0, y=0, zone="Amakna"),
            world="Monde des Douze",
            eligible_character_keys=frozenset({"character:1"}),
            evidence="verified:test",
        )
        plan = GuideRoutePlanner(_engine()).plan(
            participants,
            verified_zaap_routes=[incomplete],
        )
        start = next(row for row in plan.activities if row.action.action_id == "quest:start")
        self.assertEqual(start.travel_plan.mode, TravelMode.DIRECT)
        self.assertIn("zaap_ineligible_participant", [row.code for row in plan.issues])

        complete = VerifiedZaapRoute(
            destination=DESTINATION,
            zaap=RouteLocation(map_id=2, x=0, y=0, zone="Amakna"),
            world="Monde des Douze",
            eligible_character_keys=frozenset({"character:1", "character:2"}),
            evidence="verified:test",
        )
        plan = GuideRoutePlanner(_engine()).plan(
            participants,
            verified_zaap_routes=[complete],
        )
        start = next(row for row in plan.activities if row.action.action_id == "quest:start")
        self.assertEqual(start.travel_plan.mode, TravelMode.ZAAP_THEN_TRAVEL)
        self.assertEqual(
            start.travel_plan.participant_keys,
            ("character:1", "character:2"),
        )

    def test_zaap_fails_closed_when_world_is_unknown(self) -> None:
        route = VerifiedZaapRoute(
            destination=DESTINATION,
            zaap=RouteLocation(map_id=2, x=0, y=0, zone="Amakna"),
            world="Monde des Douze",
            eligible_character_keys=frozenset({"character:1"}),
            evidence="verified:test",
        )
        plan = GuideRoutePlanner(_engine()).plan(
            [GuideParticipantState("character:1")],
            verified_zaap_routes=[route],
        )
        start = next(row for row in plan.activities if row.action.action_id == "quest:start")
        self.assertEqual(start.travel_plan.mode, TravelMode.DIRECT)

    def test_capture_kind_is_explicit_and_never_inferred_from_title(self) -> None:
        planner = GuideRoutePlanner(_engine())
        without_contract = planner.plan([GuideParticipantState("character:1")])
        capture = next(
            row for row in without_contract.activities if row.action.action_id == "quest:capture"
        )
        self.assertEqual(capture.captures, ())

        requirement = GuideCaptureRequirement(
            "capture:99",
            "quest:capture",
            CaptureKind.ZONE_SPECIAL,
            evidence="dataset:test",
        )
        with_contract = planner.plan(
            [GuideParticipantState("character:1")],
            capture_requirements=[requirement],
        )
        capture = next(
            row for row in with_contract.activities if row.action.action_id == "quest:capture"
        )
        self.assertEqual(capture.captures, (requirement,))
        self.assertIsNone(capture.captures[0].consumable_item_id)

    def test_soul_stone_stock_is_remaining_per_participant(self) -> None:
        requirement = GuideCaptureRequirement(
            "capture:stone:99",
            "quest:capture",
            CaptureKind.SOUL_STONE,
            quantity=3,
            consumable_item_id=500,
            consumable_name="Pierre d’âme 100",
            evidence="dataset:test",
        )
        plan = GuideRoutePlanner(_engine()).plan(
            [
                GuideParticipantState(
                    "character:1",
                    progress=RouteProgress(owned_items={500: 1}),
                ),
                GuideParticipantState(
                    "character:2",
                    progress=RouteProgress(owned_items={500: 3}),
                ),
            ],
            capture_requirements=[requirement],
        )
        stones = next(row for row in plan.stock if row.item_id == 500)
        self.assertEqual(
            stones.required_by_character,
            {"character:1": 3, "character:2": 3},
        )
        self.assertEqual(
            stones.remaining_by_character,
            {"character:1": 2, "character:2": 0},
        )
        self.assertEqual(stones.total_remaining, 2)

    def test_invalid_identity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GuideParticipantState("slot:1")

    def test_incompatible_successes_are_split_deterministically(self) -> None:
        self.assertEqual(
            schedule_success_passes([3, 1, 2], [(1, 2)]),
            ((1, 3), (2,)),
        )


if __name__ == "__main__":
    unittest.main()
