from __future__ import annotations

import unittest
from pathlib import Path

from tools.ui_lab.capture import load_request


class UiLabCaptureTests(unittest.TestCase):
    def test_default_capture_request_covers_main_groups_and_long_targets(self) -> None:
        captures, include_lab_shell = load_request(Path("tools/ui_lab/capture_request.json"))
        self.assertTrue(include_lab_shell)
        self.assertEqual(len(captures), 16)
        self.assertEqual(captures[0].screen, "home")
        self.assertEqual(captures[1].screen, "organizer")

        screens = {capture.screen for capture in captures}
        self.assertTrue(
            {
                "encyclopedia.guides",
                "encyclopedia.quests",
                "encyclopedia.achievements",
                "bestiary.dungeons",
                "bestiary.monsters",
                "bestiary.archmonsters",
                "bestiary.wanted",
                "stuffs.pvm",
                "tools.treasure_hunt",
                "tools.ocre",
                "almanax",
                "tutorials.default",
            }.issubset(screens)
        )

        for capture in captures:
            self.assertGreaterEqual(capture.width, 320)
            self.assertGreaterEqual(capture.height, 240)

        quest_target = next(
            capture
            for capture in captures
            if capture.output_name == "quest-1958"
        )
        self.assertEqual(quest_target.scenario, "target")
        self.assertEqual(quest_target.params["quest_id"], 1958)
        self.assertTrue(quest_target.capture_segments)
        self.assertTrue(quest_target.capture_full_scroll)
        self.assertEqual(quest_target.segment_overlap, 80)

        guide_target = next(
            capture
            for capture in captures
            if capture.output_name == "guide-dofus-emeraude-quest-1958"
        )
        self.assertEqual(guide_target.params["guide_id"], "dofus_emeraude")
        self.assertEqual(guide_target.params["quest_id"], 1958)
        self.assertTrue(guide_target.capture_segments)
        self.assertTrue(guide_target.capture_full_scroll)

        achievement_target = next(
            capture
            for capture in captures
            if capture.output_name == "achievement-1048"
        )
        self.assertTrue(achievement_target.capture_segments)
        self.assertTrue(achievement_target.capture_full_scroll)

        home_progress = captures[-1]
        self.assertEqual(home_progress.screen, "home")
        self.assertEqual(home_progress.scenario, "saved_progress")
        self.assertEqual(home_progress.params["percent"], 42)


if __name__ == "__main__":
    unittest.main()
