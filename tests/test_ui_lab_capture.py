from __future__ import annotations

import unittest
from pathlib import Path

from tools.ui_lab.capture import load_request


class UiLabCaptureTests(unittest.TestCase):
    def test_default_capture_request_targets_core_live_surfaces(self) -> None:
        captures, include_lab_shell = load_request(Path("tools/ui_lab/capture_request.json"))
        self.assertTrue(include_lab_shell)
        self.assertEqual(
            [capture.screen for capture in captures],
            [
                "encyclopedia.guides",
                "encyclopedia.quests",
                "encyclopedia.achievements",
                "home",
            ],
        )
        for capture in captures:
            self.assertEqual(capture.scenario, "default")
            self.assertGreaterEqual(capture.width, 320)
            self.assertGreaterEqual(capture.height, 240)


if __name__ == "__main__":
    unittest.main()
