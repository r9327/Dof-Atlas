from __future__ import annotations

import unittest

from tools.guide_action_model import GuideActionType


class GuideActionTypesCompleteTests(unittest.TestCase):
    def test_official_action_vocabulary(self) -> None:
        self.assertEqual(
            {value.value for value in GuideActionType},
            {"talk", "buy", "drop", "fight", "travel", "interact", "use_item", "turn_in"},
        )


if __name__ == "__main__":
    unittest.main()
