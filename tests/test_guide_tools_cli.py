from __future__ import annotations

import unittest
from unittest.mock import patch

from tools import guide_tools_cli


class GuideToolsCliTests(unittest.TestCase):
    def test_doctor_exit_code_tracks_status(self) -> None:
        with patch("sys.argv", ["guide-tools", "doctor"]), patch.object(guide_tools_cli, "doctor", return_value={"ok": True}):
            self.assertEqual(guide_tools_cli.main(), 0)
        with patch("sys.argv", ["guide-tools", "doctor"]), patch.object(guide_tools_cli, "doctor", return_value={"ok": False}):
            self.assertEqual(guide_tools_cli.main(), 1)


if __name__ == "__main__":
    unittest.main()
