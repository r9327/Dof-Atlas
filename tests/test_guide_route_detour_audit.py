from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_route_detour_audit import (
    card_map_key,
    find_avoidable_revisits,
    has_explicit_route_barrier,
)


class GuideRouteDetourAuditTests(unittest.TestCase):
    def test_card_map_key_prefers_concrete_coordinates(self) -> None:
        self.assertEqual(card_map_key({"x": 1, "y": 2, "destination": "[9,9]"}), "1,2")
        self.assertEqual(card_map_key({"destination": "Astrub [3, -4]"}), "3,-4")
        self.assertEqual(card_map_key({"destination": "Astrub"}), "")

    def test_consecutive_same_map_is_not_a_detour(self) -> None:
        cards = [
            {"manual_stage_id": "a1", "destination": "[1,2]"},
            {"manual_stage_id": "a2", "destination": "[1,2]"},
            {"manual_stage_id": "b", "destination": "[5,6]"},
        ]
        self.assertEqual(find_avoidable_revisits(cards), [])

    def test_a_b_a_without_barrier_is_reported(self) -> None:
        cards = [
            {"manual_stage_id": "a1", "destination": "[1,2]"},
            {"manual_stage_id": "b", "destination": "[5,6]"},
            {"manual_stage_id": "a2", "destination": "[1,2]"},
        ]
        findings = find_avoidable_revisits(cards)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["map"], "1,2")
        self.assertEqual(findings[0]["first_stage_id"], "a1")
        self.assertEqual(findings[0]["return_stage_id"], "a2")
        self.assertEqual(findings[0]["intermediate_maps"], ["5,6"])

    def test_explicit_prerequisite_suppresses_candidate(self) -> None:
        cards = [
            {"manual_stage_id": "a1", "destination": "[1,2]"},
            {"manual_stage_id": "b", "destination": "[5,6]"},
            {
                "manual_stage_id": "a2",
                "destination": "[1,2]",
                "manual_stage_data": {"prerequisites": ["finish-b"]},
            },
        ]
        self.assertTrue(has_explicit_route_barrier(cards[-1]))
        self.assertEqual(find_avoidable_revisits(cards), [])

    def test_unknown_location_breaks_the_chain(self) -> None:
        cards = [
            {"manual_stage_id": "a1", "destination": "[1,2]"},
            {"manual_stage_id": "unknown", "destination": "Astrub"},
            {"manual_stage_id": "a2", "destination": "[1,2]"},
        ]
        self.assertEqual(find_avoidable_revisits(cards), [])


if __name__ == "__main__":
    unittest.main()
