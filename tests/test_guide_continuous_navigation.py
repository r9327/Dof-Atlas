"""Source-trusted step navigation uses real per-character durable state."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_continuous_navigation import (
    ContinuousGuideNavigation,
)
from app.modules.encyclopedia.services.guide_progress_service import (
    GuideProgressService,
)


def _source_route() -> dict:
    return {
        "id": "dofus_cawotte",
        "category": "dofus",
        "source_guide_id": 2205,
        "route_origin": "GANYMEDE_CONTINUOUS_STEP_ORDER",
        "replacement_status": "TRUSTED_SOURCE_STEPS",
        "auto_completion_allowed": False,
        "canonical_objectives_certified": False,
        "expected_source_step_count": 3,
        "sections": [{
            "steps": [{
                "id": f"ganymede_2205_step_{i:04d}",
                "source_guide_id": 2205,
                "source_step_number": i,
                "manual_completion_allowed": True,
                "auto_completion_allowed": False,
                "verified_actions": [],
            } for i in range(1, 4)]
        }],
    }


class ContinuousGuideNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "guide_progress.json"
        self.progress = GuideProgressService(self.path)
        self.route = _source_route()

    def _navigator(self, *keys: str) -> ContinuousGuideNavigation:
        return ContinuousGuideNavigation(self.route, self.progress, keys)

    def test_no_selected_character_means_no_imaginary_actual_step(self):
        nav = self._navigator()
        self.assertEqual(nav.position().status, "NO_SELECTED_CHARACTER")
        self.assertIsNone(nav.show_actual())
        self.assertIsNone(nav.position().viewed_step_id)
        self.assertFalse(nav.mark_manual_step("ganymede_2205_step_0001", True))
        self.assertEqual(nav.position().completed_by_character, {})

    def test_actual_uses_earliest_incomplete_across_selected_characters(self):
        first = self._navigator("character:1")
        first.mark_manual_step("ganymede_2205_step_0001", True)
        first.mark_manual_step("ganymede_2205_step_0002", True)
        second = self._navigator("character:2")
        second.mark_manual_step("ganymede_2205_step_0001", True)

        nav = self._navigator("character:1", "character:2")
        self.assertEqual(nav.show_actual(), "ganymede_2205_step_0002")
        self.assertEqual(
            nav.position().completed_by_character,
            {"character:1": 2, "character:2": 1},
        )
        nav.show_step("ganymede_2205_step_0003")
        self.assertEqual(nav.position().viewed_step_id, "ganymede_2205_step_0003")
        self.assertEqual(nav.position().actual_step_id, "ganymede_2205_step_0002")
        self.assertEqual(nav.show_actual(), "ganymede_2205_step_0002")

    def test_zero_selected_can_browse_without_creating_progress(self):
        nav = self._navigator()
        self.assertIsNone(nav.position().actual_step_id)
        self.assertEqual(nav.next_step(), "ganymede_2205_step_0001")
        self.assertEqual(nav.next_step(), "ganymede_2205_step_0002")
        self.assertEqual(nav.previous_step(), "ganymede_2205_step_0001")
        self.assertIsNone(nav.position().actual_step_id)
        self.assertFalse(nav.mark_manual_step("ganymede_2205_step_0001", True))
        self.assertFalse(self.path.exists())

    def test_next_previous_do_not_modify_progress_or_actual(self):
        nav = self._navigator("character:1")
        self.assertEqual(nav.next_step(), "ganymede_2205_step_0001")
        self.assertIsNone(nav.previous_step())
        self.assertEqual(nav.next_step(), "ganymede_2205_step_0002")
        self.assertEqual(nav.next_step(), "ganymede_2205_step_0003")
        self.assertIsNone(nav.next_step())
        self.assertEqual(nav.position().actual_step_id, "ganymede_2205_step_0001")
        self.assertEqual(nav.position().completed_by_character, {"character:1": 0})

    def test_selected_characters_validate_and_uncheck_independently(self):
        nav = self._navigator("character:1", "character:2")
        first = "ganymede_2205_step_0001"
        self.assertTrue(nav.mark_manual_step(first, True))
        self.assertEqual(nav.position().actual_step_id, "ganymede_2205_step_0002")
        self.assertEqual(nav.position().completed_by_character,
                         {"character:1": 1, "character:2": 1})
        nav.select_characters(("character:1",))
        self.assertTrue(nav.mark_manual_step(first, False))
        self.assertEqual(nav.position().actual_step_id, first)
        reopened = GuideProgressService(self.path)
        self.assertFalse(reopened.is_manual_step_completed(
            "character:1", "dofus_cawotte", first,
        ))
        self.assertTrue(reopened.is_manual_step_completed(
            "character:2", "dofus_cawotte", first,
        ))
        with self.assertRaises(ValueError):
            nav.select_characters(("character:1", "character:1"))
        with self.assertRaises(ValueError):
            nav.select_characters(("slot:1",))

    def test_current_recomputes_after_external_instance_changes(self):
        nav = self._navigator("character:1")
        fresh = GuideProgressService(self.path)
        fresh.set_manual_step_completed(
            "character:1", "dofus_cawotte", "ganymede_2205_step_0001", True,
        )
        self.assertEqual(nav.position().actual_step_id, "ganymede_2205_step_0002")

    def test_all_complete_is_explicit_and_not_a_fake_destination(self):
        nav = self._navigator("character:1")
        for step_id in nav.step_ids:
            nav.mark_manual_step(step_id, True)
        self.assertEqual(nav.position().status, "ALL_COMPLETE")
        self.assertIsNone(nav.show_actual())
        self.assertIsNone(nav.position().viewed_step_id)

    def test_no_objective_validation_or_corrupt_source_route(self):
        for key, value in [
            ("auto_completion_allowed", True),
            ("canonical_objectives_certified", True),
            ("replacement_status", "DRAFT_NOT_PLAYABLE"),
        ]:
            route = _source_route()
            route[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ContinuousGuideNavigation(route, self.progress, ["character:1"])
        bad = _source_route()
        bad["sections"][0]["steps"][1]["source_step_number"] = 99
        with self.assertRaises(ValueError):
            ContinuousGuideNavigation(bad, self.progress, ["character:1"])

    def test_one_five_participants_and_total_remain_exact(self):
        nav = self._navigator(*(f"character:{i}" for i in range(1, 6)))
        self.assertTrue(nav.mark_manual_step("ganymede_2205_step_0001", True))
        self.assertEqual(nav.position().completed_by_character,
                         {f"character:{i}": 1 for i in range(1, 6)})
        self.assertEqual(nav.position().total_steps, 3)
        nav.select_characters(())
        self.assertEqual(nav.position().status, "NO_SELECTED_CHARACTER")


if __name__ == "__main__":
    unittest.main()
