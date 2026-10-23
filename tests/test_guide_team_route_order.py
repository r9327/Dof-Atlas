"""Focused geographic/team order tests: genuine action edges always win."""
from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.adventure_route_engine import (
    AdventureRouteEngine, RouteAction, RouteLocation,
)
from app.modules.encyclopedia.services.guide_route_planner import (
    GuideParticipantState, GuideRoutePlanner,
)
from app.modules.encyclopedia.services.guide_team_route_order import (
    order_team_actions,
)


def _loc(x: int) -> RouteLocation:
    return RouteLocation(x=x, y=0, zone="Amakna")


class GuideTeamGeographicOrderTests(unittest.TestCase):
    def test_shorter_geographic_sequence_for_independent_actions(self):
        engine = AdventureRouteEngine([
            RouteAction("far", 1, "Far", "start", location=_loc(60)),
            RouteAction("near", 2, "Near", "start", location=_loc(1)),
            RouteAction("middle", 3, "Middle", "start", location=_loc(2)),
        ])
        graph = {key: set() for key in engine.by_id}
        memberships = {"far": [(0, "character:1")],
                       "middle": [(1, "character:1")],
                       "near": [(2, "character:1")]}
        ordered = order_team_actions(
            graph, dict.fromkeys(graph, 0), memberships, engine,
            {"character:1": _loc(0)},
        )
        self.assertEqual(ordered, ("near", "middle", "far"))

    def test_action_dependency_cannot_be_skipped_to_save_travel(self):
        engine = AdventureRouteEngine([
            RouteAction("required_first", 1, "Start", "start", location=_loc(60)),
            RouteAction("near_second", 1, "Next", "dialogue",
                        location=_loc(0),
                        prerequisites_actions=frozenset({"required_first"})),
        ])
        graph = {"required_first": {"near_second"}, "near_second": set()}
        memberships = {x: [(i, "character:1")]
                       for i, x in enumerate(engine.by_id)}
        ordered = order_team_actions(
            graph, {"required_first": 0, "near_second": 1},
            memberships, engine, {"character:1": _loc(0)},
        )
        self.assertEqual(ordered, ("required_first", "near_second"))

    def test_coordinate_tiebreak_sums_only_action_participants(self):
        engine = AdventureRouteEngine([
            RouteAction("solo", 1, "Solo", "start", location=_loc(8)),
            RouteAction("team", 2, "Team", "start", location=_loc(1)),
        ])
        graph = {key: set() for key in engine.by_id}
        ordered = order_team_actions(
            graph, dict.fromkeys(graph, 0),
            {"solo": [(0, "character:1")],
             "team": [(1, "character:1"), (1, "character:2")]},
            engine, {"character:1": _loc(0), "character:2": _loc(0),
                     "character:3": _loc(1000)},
        )
        self.assertEqual(ordered, ("team", "solo"))

    def test_unknown_start_coordinates_preserve_source_order(self):
        engine = AdventureRouteEngine([
            RouteAction("far", 1, "Far", "start", location=_loc(60)),
            RouteAction("near", 2, "Near", "start", location=_loc(1)),
        ])
        graph = {key: set() for key in engine.by_id}
        ordered = order_team_actions(
            graph, dict.fromkeys(graph, 0),
            {"far": [(0, "character:1")], "near": [(1, "character:1")]},
            engine, {"character:1": RouteLocation(zone="Amakna")},
        )
        self.assertEqual(ordered, ("far", "near"))

    def test_quest_start_kind_is_respected_even_without_activates_flag(self):
        engine = AdventureRouteEngine([
            RouteAction("start", 10, "Démarrer quête", "start", location=_loc(60)),
            RouteAction("finish", 10, "Terminer quête", "dialogue", location=_loc(1),
                        completes_quest=True),
        ])
        result = GuideRoutePlanner(engine).plan([
            GuideParticipantState("character:1", start_location=_loc(0)),
        ])
        self.assertEqual(
            [x.action.action_id for x in result.activities],
            ["start", "finish"],
        )
        self.assertNotIn("shared_route_order_conflict", [x.code for x in result.issues])

    def test_positions_are_independent_for_each_selected_character(self):
        engine = AdventureRouteEngine([
            RouteAction("west", 10, "West", "start", location=_loc(0)),
            RouteAction("east", 20, "East", "start", location=_loc(100)),
        ])
        graph = {"west": set(), "east": set()}
        membership = {"west": [(0, "character:1")],
                      "east": [(0, "character:2")]}
        ordered = order_team_actions(
            graph, dict.fromkeys(graph, 0), membership, engine,
            {"character:1": _loc(1), "character:2": _loc(99)},
        )
        self.assertEqual(set(ordered), {"west", "east"})

    def test_unknown_member_and_dependency_cycle_fail_closed(self):
        engine = AdventureRouteEngine([
            RouteAction("a", 1, "A", "start", location=_loc(0)),
            RouteAction("b", 2, "B", "start", location=_loc(1)),
        ])
        with self.assertRaises(ValueError):
            order_team_actions(
                {"a": set()}, {"a": 0},
                {"a": [(0, "character:unknown")]},
                engine, {"character:1": None},
            )
        self.assertIsNone(order_team_actions(
            {"a": {"b"}, "b": {"a"}}, {"a": 1, "b": 1},
            {"a": [(0, "character:1")], "b": [(1, "character:1")]},
            engine, {"character:1": None},
        ))


if __name__ == "__main__":
    unittest.main()
