from __future__ import annotations

import unittest
from pathlib import Path

from tools.ui_lab.capture import load_request


class UiLabCaptureTests(unittest.TestCase):
    def test_default_capture_request_targets_core_live_surfaces_and_precise_states(self) -> None:
        captures, include_lab_shell = load_request(Path("tools/ui_lab/capture_request.json"))
        self.assertTrue(include_lab_shell)
        self.assertEqual(len(captures), 8)
        self.assertEqual(
            [capture.screen for capture in captures[:4]],
            [
                "encyclopedia.guides",
                "encyclopedia.quests",
                "encyclopedia.achievements",
                "home",
            ],
        )
        for capture in captures:
            self.assertGreaterEqual(capture.width, 320)
            self.assertGreaterEqual(capture.height, 240)

        guide_target, quest_target, achievement_target, home_progress = captures[4:]
        self.assertEqual(guide_target.scenario, "target")
        self.assertEqual(guide_target.params["guide_id"], "dofus_emeraude")
        self.assertEqual(guide_target.params["quest_id"], 1958)
        self.assertEqual(guide_target.output_name, "guide-dofus-emeraude-quest-1958")

        self.assertEqual(quest_target.scenario, "target")
        self.assertEqual(quest_target.params["quest_id"], 1958)
        self.assertEqual(achievement_target.scenario, "target")
        self.assertEqual(achievement_target.params["achievement_id"], 1048)

        self.assertEqual(home_progress.scenario, "saved_progress")
        self.assertEqual(home_progress.params["percent"], 42)


if __name__ == "__main__":
    unittest.main()
