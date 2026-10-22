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
    GuideTravelPlan,
    unbound_direct_travel_payload,
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

    def test_missing_doduda_coordinate_never_generates_travel_command(self) -> None:
        missing = -(2**31)
        for destination in (
            RouteLocation(map_id=20, x=missing, y=6),
            RouteLocation(map_id=20, x=6, y=missing),
            RouteLocation(map_id=20, x=6, y=None),
        ):
            with self.subTest(destination=destination):
                self.assertEqual(
                    unbound_direct_travel_payload(destination)["status"],
                    "unavailable",
                )
                with self.assertRaisesRegex(ValueError, "exact coordinates"):
                    GuideTravelPlan(TravelMode.DIRECT, destination, ("character:1",))

        self.assertEqual(
            unbound_direct_travel_payload(RouteLocation(x=-32, y=-56))["status"],
            "template",
        )

    def test_verified_zaap_rejects_sentinel_coordinates(self) -> None:
        missing = -(2**31)
        for destination, zaap in (
            (RouteLocation(map_id=10, x=missing, y=0), DESTINATION),
            (DESTINATION, RouteLocation(map_id=3, x=0, y=missing)),
        ):
            with self.subTest(destination=destination, zaap=zaap):
                with self.assertRaisesRegex(ValueError, "exact coordinates"):
                    VerifiedZaapRoute(
                        destination=destination, zaap=zaap,
                        world="Monde des Douze",
                        eligible_character_keys=frozenset({"character:1"}),
                        evidence="test:verified",
                    )

    def test_guide_plan_reports_unresolved_sentinel_without_route(self) -> None:
        missing = -(2**31)
        engine = AdventureRouteEngine([
            RouteAction(
                "quest:start", 1, "Prendre la quête", "start",
                location=RouteLocation(map_id=20, x=missing, y=0),
                activates_quest=True,
            )
        ])
        plan = GuideRoutePlanner(engine).plan([GuideParticipantState("character:1")])
        self.assertEqual(len(plan.activities), 1)
        self.assertIsNone(plan.activities[0].travel_plan)
        self.assertIn(
            "transport_destination_unresolved",
            [issue.code for issue in plan.issues],
        )

    def test_optimizer_export_matches_organizer_two_command_protocol(self) -> None:
        direct = GuideTravelPlan(
            TravelMode.DIRECT, DESTINATION, ("character:2",)
        )
        self.assertEqual(direct.to_chat_command(), "/travel 5,-2")
        self.assertEqual(direct.to_payload()["participant_keys"], ["character:2"])
        combined = GuideTravelPlan(
            TravelMode.ZAAP_THEN_TRAVEL,
            DESTINATION,
            ("character:1", "character:2"),
            world="Monde des Douze",
            zaap=RouteLocation(map_id=2, x=-32, y=-56),
            evidence="verified:zaap:atlas",
        )
        self.assertEqual(
            combined.to_chat_command(),
            "/zaap -32,-56 ; /travel 5,-2",
        )
        self.assertEqual(
            combined.to_payload()["participant_keys"],
            ["character:1", "character:2"],
        )

    def test_invalid_travel_mode_must_not_degrade_to_direct(self) -> None:
        with self.assertRaisesRegex(ValueError, "travel mode"):
            GuideTravelPlan("zaap_then_travel", DESTINATION, ("character:1",))

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

    def test_no_team_zaap_when_a_participant_is_already_on_the_map(self) -> None:
        route = VerifiedZaapRoute(
            destination=DESTINATION,
            zaap=RouteLocation(map_id=2, x=0, y=0, zone="Amakna"),
            world="Monde des Douze",
            eligible_character_keys=frozenset({"character:1", "character:2"}),
            evidence="verified:test",
        )
        plan = GuideRoutePlanner(_engine()).plan(
            [
                GuideParticipantState(
                    "character:1", world="Monde des Douze",
                    start_location=DESTINATION,
                ),
                GuideParticipantState(
                    "character:2", world="Monde des Douze",
                    start_location=RouteLocation(map_id=3, x=20, y=0, zone="Amakna"),
                ),
            ],
            verified_zaap_routes=[route],
        )
        start = next(row for row in plan.activities if row.action.action_id == "quest:start")
        self.assertEqual(start.travel_plan.mode, TravelMode.DIRECT)
        self.assertEqual(start.travel_plan.participant_keys,
                         ("character:1", "character:2"))

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

    def test_incomplete_stock_never_invents_a_missing_quantity(self) -> None:
        requirement = GuideCaptureRequirement(
            "capture:unknown-stock", "quest:capture", CaptureKind.SOUL_STONE,
            quantity=3, consumable_item_id=500,
            consumable_name="Pierre d’âme 100", evidence="dataset:test",
        )
        plan = GuideRoutePlanner(_engine()).plan(
            [
                GuideParticipantState(
                    "character:1", progress=RouteProgress(owned_items={}),
                ),
                GuideParticipantState(
                    "character:2",
                    progress=RouteProgress(owned_items={500: 1}),
                ),
            ],
            capture_requirements=[requirement],
        )
        stones = next(row for row in plan.stock if row.item_id == 500)
        self.assertEqual(stones.required_by_character, {
            "character:1": 3, "character:2": 3,
        })
        self.assertEqual(stones.remaining_by_character, {
            "character:1": None, "character:2": 2,
        })
        self.assertIsNone(stones.total_remaining)

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

    def test_shared_route_preserves_all_characters_prerequisite_order(self) -> None:
        # Player 1 already finished the first action. An earliest-index-only
        # sort would put 'finish' before 'start' for player 2.
        engine = AdventureRouteEngine([
            RouteAction(
                "quest:start", 1, "Prendre — Mission", "start",
                location=RouteLocation(map_id=20, x=20, y=0),
                activates_quest=True,
            ),
            RouteAction(
                "quest:finish", 1, "Vaincre la cible", "combat",
                location=RouteLocation(map_id=10, x=0, y=0),
                prerequisites_actions=frozenset({"quest:start"}),
                monster_ids=frozenset({99}),
            ),
        ])
        plan = GuideRoutePlanner(engine).plan([
            GuideParticipantState(
                "character:1",
                progress=RouteProgress(
                    active_quest_ids={1},
                    completed_action_ids={"quest:start"},
                ),
            ),
            GuideParticipantState("character:2"),
        ])
        self.assertEqual(
            [row.action.action_id for row in plan.activities],
            ["quest:start", "quest:finish"],
        )
        self.assertEqual(plan.activities[0].participant_keys, ("character:2",))
        self.assertEqual(
            plan.activities[1].participant_keys,
            ("character:1", "character:2"),
        )
        self.assertNotIn(
            "shared_route_order_conflict", [issue.code for issue in plan.issues],
        )

    def test_independent_actions_remain_shared_despite_different_solo_routes(self) -> None:
        # Geographic preferences are not canonical prerequisites. If players
        # start on opposite sides of a zone, one common route is still valid.
        a = RouteLocation(map_id=11, x=0, y=0, zone="Amakna")
        b = RouteLocation(map_id=12, x=30, y=0, zone="Amakna")
        engine = AdventureRouteEngine([
            RouteAction("quest:a", 1, "Prendre — A", "start",
                        location=a, activates_quest=True),
            RouteAction("quest:b", 2, "Prendre — B", "start",
                        location=b, activates_quest=True),
        ])
        plan = GuideRoutePlanner(engine).plan([
            GuideParticipantState("character:1", start_location=a),
            GuideParticipantState("character:2", start_location=b),
        ])
        self.assertEqual(
            [step.actions[0].action_id for step in plan.participants[0].route.steps],
            ["quest:a", "quest:b"],
        )
        self.assertEqual(
            [step.actions[0].action_id for step in plan.participants[1].route.steps],
            ["quest:b", "quest:a"],
        )
        self.assertEqual(
            {row.action.action_id for row in plan.activities},
            {"quest:a", "quest:b"},
        )
        self.assertTrue(all(row.participant_keys == (
            "character:1", "character:2",
        ) for row in plan.activities))
        self.assertNotIn(
            "shared_route_order_conflict", [issue.code for issue in plan.issues],
        )

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
