from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.guide_progress_presentation import guide_progress_state, guide_progress_style_state


class GuideProgressPresentationTests(unittest.TestCase):
    def test_guide_qt_style_state_matches_existing_done_partial_todo_rules(self) -> None:
        for completed, total, expected in ((0, 0, "todo"), (0, 4, "todo"),
                                           (1, 4, "partial"), (4, 4, "done"),
                                           (5, 4, "done"), (2, 0, "partial")):
            with self.subTest(completed=completed, total=total):
                self.assertEqual(guide_progress_style_state(completed, total), expected)

    def test_progress_state_matches_legacy_boundaries(self) -> None:
        self.assertEqual(guide_progress_state(0, 0), "Non commencé")
        self.assertEqual(guide_progress_state(0, 4), "Non commencé")
        self.assertEqual(guide_progress_state(1, 4), "En cours")
        self.assertEqual(guide_progress_state(4, 4), "Terminé")
        self.assertEqual(guide_progress_state(5, 4), "Terminé")


if __name__ == "__main__":
    unittest.main()
