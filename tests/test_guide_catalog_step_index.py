"""Exact route source-selection compatibility, independent of Qt and providers."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_catalog_step_index import (
    ordered_route_quest_steps,
)


class OrderedRouteQuestStepsTests(unittest.TestCase):
    def test_orders_source_steps_and_keeps_provider_side_duplicate_semantics(self):
        def step(order, step_type, entity_id):
            return SimpleNamespace(order=order, step_type=step_type, entity_id=entity_id)

        guide = SimpleNamespace(required_steps=(
            step(30, "quest", "4"),
            step(10, "quest", "4"),
            step(20, "travel", "10"),
            step(25, "quest", "invalid"),
            step(40, "quest", True),
            step(50, "quest", -2),
        ))
        self.assertEqual(
            [(row.order, ident) for row, ident in ordered_route_quest_steps(guide)],
            [(10, 4), (30, 4), (40, 1), (50, -2)],
        )

    def test_empty_guide_and_missing_ids_are_not_artificial_quests(self):
        self.assertEqual(list(ordered_route_quest_steps(SimpleNamespace())), [])
        self.assertEqual(list(ordered_route_quest_steps(SimpleNamespace(
            required_steps=[SimpleNamespace(order=1, step_type="quest", entity_id=None)]
        ))), [])


if __name__ == "__main__":
    unittest.main()
