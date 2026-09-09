from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.guide_progress_presentation import guide_progress_state


class GuideProgressPresentationTests(unittest.TestCase):
    def test_progress_state_matches_legacy_boundaries(self) -> None:
        self.assertEqual(guide_progress_state(0, 0), "Non commencé")
        self.assertEqual(guide_progress_state(0, 4), "Non commencé")
        self.assertEqual(guide_progress_state(1, 4), "En cours")
        self.assertEqual(guide_progress_state(4, 4), "Terminé")
        self.assertEqual(guide_progress_state(5, 4), "Terminé")


if __name__ == "__main__":
    unittest.main()
