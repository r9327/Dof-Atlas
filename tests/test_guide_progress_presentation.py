from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_progress_wording import guide_progress_noun
from app.modules.encyclopedia.views.guide_progress_presentation import (
    guide_progress_state, guide_progress_style_state,
)


class GuideProgressPresentationTests(unittest.TestCase):
    def test_progress_labels_preserve_quest_and_empty_route_compatibility(self):
        quest = SimpleNamespace(required_steps=(SimpleNamespace(step_type="quest"),))
        mixed = SimpleNamespace(required_steps=(
            SimpleNamespace(step_type="quest"), SimpleNamespace(step_type="info"),
        ))
        empty = SimpleNamespace(required_steps=())
        self.assertEqual(guide_progress_noun(quest, 1), "quête")
        self.assertEqual(guide_progress_noun(quest, 2), "quêtes")
        self.assertEqual(guide_progress_noun(mixed, 2), "étapes")
        self.assertEqual(guide_progress_noun(empty, 2), "étapes")
        self.assertEqual(
            guide_progress_noun(empty, 2, empty_counts_as_quests=True), "quêtes",
        )
        self.assertEqual(guide_progress_noun(quest, 0), "étapes")

    def test_guide_qt_style_state_matches_existing_done_partial_todo_rules(self) -> None:
        for completed, total, expected in ((0, 0, "todo"), (0, 4, "todo"),
                                           (1, 4, "partial"), (4, 4, "done"),
                                           (5, 4, "done"), (2, 0, "partial")):
            with self.subTest(completed=completed, total=total):
                self.assertEqual(guide_progress_style_state(completed, total), expected)

    def test_guide_step_counter_reuses_shared_quest_and_step_wording(self):
        from app.modules.encyclopedia.services.guide_quest_view_model import guide_step_count_text

        def step(kind, tracked=True):
            return SimpleNamespace(step_type=kind, counts_for_completion=tracked)

        for steps, expected in (
            ((), ""),
            ((step("quest"),), "1 quête"),
            ((step("quest"), step("quest")), "2 quêtes"),
            ((step("quest"), step("info", False)), "1 étape"),
            ((step("info"), step("quest")), "2 étapes"),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(
                    guide_step_count_text(SimpleNamespace(required_steps=steps)), expected,
                )

    def test_display_and_style_state_share_same_completion_boundary(self):
        pairs = ((0, 0), (0, 1), (1, 1), (2, 8), (9, 8), (2, 0))
        expected = {
            "todo": "Non commencé",
            "partial": "En cours",
            "done": "Terminé",
        }
        for completed, total in pairs:
            with self.subTest(completed=completed, total=total):
                self.assertEqual(
                    guide_progress_state(completed, total),
                    expected[guide_progress_style_state(completed, total)],
                )

    def test_progress_state_matches_legacy_boundaries(self) -> None:
        self.assertEqual(guide_progress_state(0, 0), "Non commencé")
        self.assertEqual(guide_progress_state(0, 4), "Non commencé")
        self.assertEqual(guide_progress_state(1, 4), "En cours")
        self.assertEqual(guide_progress_state(4, 4), "Terminé")
        self.assertEqual(guide_progress_state(5, 4), "Terminé")


if __name__ == "__main__":
    unittest.main()
