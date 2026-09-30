from __future__ import annotations

import unittest

from tools import guide_semantics


class GuideSemanticsTests(unittest.TestCase):
    def test_public_surface_is_available(self) -> None:
        self.assertTrue(callable(guide_semantics.validate_actions))
        self.assertTrue(callable(guide_semantics.group_consecutive_talks))
        self.assertEqual(guide_semantics.GuideActionType.TALK.value, "talk")


if __name__ == "__main__":
    unittest.main()
