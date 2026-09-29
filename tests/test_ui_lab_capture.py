from __future__ import annotations

import unittest
from pathlib import Path

from tools.ui_lab.capture import load_request


class UiLabCaptureTests(unittest.TestCase):
    def test_default_capture_request_targets_live_guides_preview(self) -> None:
        captures, include_lab_shell = load_request(Path("tools/ui_lab/capture_request.json"))
        self.assertTrue(include_lab_shell)
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0].screen, "encyclopedia.guides")
        self.assertEqual(captures[0].scenario, "default")
        self.assertGreaterEqual(captures[0].width, 320)
        self.assertGreaterEqual(captures[0].height, 240)


if __name__ == "__main__":
    unittest.main()
