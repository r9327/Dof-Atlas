from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.adventure_route_engine import (
    RouteAction,
    RouteLocation,
    RouteStep,
)
from app.modules.encyclopedia.services.guide_route_naming import (
    audit_title_decisions,
    title_for_route_step,
)


def _step(*actions: RouteAction, location: RouteLocation | None = None) -> RouteStep:
    return RouteStep(
        index=1,
        location=location or RouteLocation(x=1, y=2, zone="Amakna"),
        actions=actions,
        quest_ids=tuple(dict.fromkeys(action.quest_id for action in actions)),
    )


class GuideRouteNamingTests(unittest.TestCase):
    def test_dungeon_and_monster_names_remain_exact(self) -> None:
        dungeon = title_for_route_step(
            _step(
                RouteAction(
                    "q1:dungeon",
                    1,
                    "Vaincre le boss",
                    "dungeon",
                    dungeon_id=10,
                    dungeon_name="Blops Multicolores",
                )
            )
        )
        fight = title_for_route_step(
            _step(
                RouteAction(
                    "q2:fight",
                    2,
                    "Vaincre",
                    "combat",
                    monster_ids=frozenset({42}),
                    monster_names=("Tournesol sauvage",),
                )
            )
        )
        self.assertEqual(dungeon.text, "Donjon — Blops Multicolores")
        self.assertEqual(fight.text, "Combat — Tournesol sauvage")

    def test_long_official_name_is_reported_and_never_truncated(self) -> None:
        exact = "Le très long nom officiel d’un monstre impossible à raccourcir"
        decision = title_for_route_step(
            _step(
                RouteAction(
                    "q1:fight",
                    1,
                    "Vaincre",
                    "combat",
                    monster_ids=frozenset({1}),
                    monster_names=(exact,),
                )
            )
        )
        self.assertIn(exact, decision.text)
        self.assertIn(
            "title_too_long",
            [row.code for row in audit_title_decisions([decision])],
        )

    def test_duplicate_titles_are_explicit_review_findings(self) -> None:
        action = RouteAction("q1:start", 1, "Prendre — Une quête", "start")
        decision = title_for_route_step(_step(action))
        violations = audit_title_decisions([decision, decision])
        self.assertEqual(
            [row.code for row in violations],
            ["title_ambiguous_duplicate", "title_ambiguous_duplicate"],
        )

if __name__ == "__main__":
    unittest.main()
