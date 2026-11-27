"""Exact route source-selection compatibility, independent of Qt and providers."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_catalog_step_index import (
    ordered_route_quest_steps, resolved_route_quests,
    route_position_key, route_positions_merge, route_positions_split,
)


class OrderedRouteQuestStepsTests(unittest.TestCase):
    def test_route_positions_use_one_renderer_policy(self):
        self.assertEqual(route_position_key(" [ -01, 02 ] "), "-1,2")
        self.assertEqual(route_position_key("  Forêt   d'Amakna "), "foret_d_amakna")
        self.assertTrue(route_positions_merge("1,2", "1,2"))
        self.assertFalse(route_positions_merge("", ""))
        self.assertTrue(route_positions_split("1,2", "3,4"))
        self.assertFalse(route_positions_split("", "3,4"))

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

    def test_provider_missing_quest_is_retryable_then_duplicate_skipped(self):
        def step(order, ident):
            return SimpleNamespace(order=order, step_type="quest", entity_id=ident)

        guide = SimpleNamespace(required_steps=[
            step(1, 7), step(2, 7), step(3, 7), step(4, 9), step(5, 9),
        ])

        class Provider:
            def __init__(self):
                self.calls = []
            def get_quest(self, ident):
                self.calls.append(ident)
                if ident == 7 and self.calls.count(7) == 1:
                    return None
                return SimpleNamespace(id=ident)

        provider = Provider()
        resolved = list(resolved_route_quests(guide, provider))
        self.assertEqual([(row.order, quest.id) for row, quest in resolved], [(2, 7), (4, 9)])
        self.assertEqual(provider.calls, [7, 7, 9])

    def test_empty_guide_and_missing_ids_are_not_artificial_quests(self):
        self.assertEqual(list(ordered_route_quest_steps(SimpleNamespace())), [])
        self.assertEqual(list(ordered_route_quest_steps(SimpleNamespace(
            required_steps=[SimpleNamespace(order=1, step_type="quest", entity_id=None)]
        ))), [])


if __name__ == "__main__":
    unittest.main()
