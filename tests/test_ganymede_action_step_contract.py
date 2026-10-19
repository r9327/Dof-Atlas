"""No dangling preparations or invented source links in Ganymède candidates."""
from __future__ import annotations

import unittest

from tools.ganymede_action_step_contract import validate_step_action


def review(action, *, stage=4, total=10, monsters=None):
    return validate_step_action(
        action, step_number=stage, source_step_count=total,
        observed_monster_ids=monsters if monsters is not None else [100, 101, 102],
    )


class StageActionScopeTests(unittest.TestCase):
    def test_forward_preparation_is_allowed_without_fake_completion(self):
        self.assertEqual(review({
            "kind": "optional_preparation",
            "quantity": 2, "needed_at_source_step": 8,
            "can_obtain_on_route": True,
        }), [])

    def test_future_deadline_past_guide_is_rejected(self):
        self.assertTrue(review({"needed_at_source_step": 11}))
        self.assertTrue(review({"needed_at_source_step": 2}))
        self.assertTrue(review({"needed_at_source_step": True}))
        self.assertTrue(review({"collection_window_end": 11}))
        self.assertTrue(review({"collection_window_end": 3}))

    def test_previous_stage_must_precede_current_stage(self):
        self.assertEqual(review({"references_previous_stage": 2}), [])
        for invalid in (0, 4, 5, 11, "2", True):
            with self.subTest(invalid=invalid):
                self.assertIn("invalid references_previous_stage", " ".join(
                    review({"references_previous_stage": invalid})))

    def test_boolean_flags_are_not_inferred_from_text(self):
        self.assertEqual(review({
            "optional_branch": True, "stay_at_end": True,
            "daily_reset": False, "capture_required": True,
        }), [])
        self.assertTrue(review({"capture_required": 1}))
        self.assertTrue(review({"can_obtain_on_route": "true"}))
        self.assertTrue(review({"optional_branch": "yes"}))

    def test_counts_must_be_positive_integers_not_bools(self):
        for key in ("quantity_per_character", "repeat_count", "quantity"):
            for value in (0, -1, 2.1, True, "2"):
                with self.subTest(key=key, value=value):
                    self.assertTrue(review({key: value}))
        self.assertEqual(review({
            "quantity_per_character": 1, "repeat_count": 2,
        }), [])

    def test_alternative_monsters_are_checked_against_source(self):
        self.assertEqual(review({
            "alternative_monster_ids": [101, 102],
        }), [])
        for values in ([101, 101], [200], [100, True], [], "100"):
            with self.subTest(values=values):
                self.assertTrue(review({"alternative_monster_ids": values}))

    def test_invalid_stage_bounds_are_fail_closed(self):
        self.assertTrue(review({}, stage=0))
        self.assertTrue(review({}, stage=11))


if __name__ == "__main__":
    unittest.main()
