"""Read-only Ganymède preparation hints: no stock or purchase claims."""
from __future__ import annotations

from copy import deepcopy
import unittest

from app.modules.encyclopedia.services.guide_continuous_preparation import (
    visible_object_references,
)
from tests.test_guide_continuous_navigation import _source_route


class ContinuousPreparationTests(unittest.TestCase):
    def make_route(self):
        route = deepcopy(_source_route())
        route["sections"][0]["steps"][0]["source_action_candidates"] = [
            {"kind": "prepare_object", "object_id": 361,
             "label": "Cawotte", "needed_at_source_step": 3},
            {"kind": "optional_preparation", "object_id": 361,
             "label": "Cawotte facultative", "needed_at_source_step": 3},
            {"kind": "prepare_object", "object_id": 969,
             "label": "Couronne du Wa", "can_obtain_on_route": True},
            {"kind": "quest_start", "quest_id": 999,
             "label": "Démarrer une quête"},
        ]
        route["sections"][0]["steps"][1]["source_action_candidates"] = [
            {"kind": "prepare_object", "object_id": 970,
             "label": "Bâton du Wa"},
        ]
        return route

    def test_preview_tracks_due_step_and_deduplicates_by_item_id(self):
        route = self.make_route()
        first, second, third = (
            f"ganymede_2205_step_{number:04d}" for number in (1, 2, 3)
        )
        early = visible_object_references(route, first)
        self.assertEqual({item.item_id for item in early}, {361, 969})
        cawotte = next(item for item in early if item.item_id == 361)
        self.assertTrue(cawotte.optional_or_conditional)
        self.assertEqual(cawotte.needed_at_step, 3)
        self.assertTrue(next(item for item in early if item.item_id == 969).obtainable_on_route)
        middle = visible_object_references(route, second)
        self.assertEqual({item.item_id for item in middle}, {361, 970})
        self.assertEqual([item.item_id for item in visible_object_references(route, third)], [361])

    def test_rejects_corrupted_due_step_and_object_id(self):
        route = self.make_route()
        step_id = "ganymede_2205_step_0001"
        route["sections"][0]["steps"][0]["source_action_candidates"][0]["needed_at_source_step"] = 4
        with self.assertRaisesRegex(ValueError, "due step"):
            visible_object_references(route, step_id)
        route["sections"][0]["steps"][0]["source_action_candidates"][0]["needed_at_source_step"] = 3
        route["sections"][0]["steps"][0]["source_action_candidates"][0]["object_id"] = True
        with self.assertRaisesRegex(ValueError, "identifier"):
            visible_object_references(route, step_id)

    def test_rejects_untrusted_or_unselected_source_steps(self):
        route = self.make_route()
        with self.assertRaisesRegex(ValueError, "not uniquely"):
            visible_object_references(route, "ganymede_2205_step_9999")
        route["auto_completion_allowed"] = True
        with self.assertRaisesRegex(ValueError, "source-trusted"):
            visible_object_references(route, "ganymede_2205_step_0001")


if __name__ == "__main__":
    unittest.main()
