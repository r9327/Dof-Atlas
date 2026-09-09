from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService


class GuideProgressPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "guide_progress.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_two_live_instances_do_not_overwrite_each_other(self) -> None:
        first = GuideProgressService(self.path)
        second = GuideProgressService(self.path)

        first.set_manual_step_completed("character:1", "guide_a", "stage:a", True)
        second.set_manual_step_completed("character:1", "guide_a", "stage:b", True)

        fresh = GuideProgressService(self.path)
        self.assertEqual(
            {"stage:a", "stage:b"},
            fresh.manual_steps("character:1", "guide_a"),
        )

    def test_corrupt_json_is_preserved_before_fallback(self) -> None:
        self.path.write_text('{"version": 1, "characters": ', encoding="utf-8")

        service = GuideProgressService(self.path)

        self.assertEqual(set(), service.manual_steps("character:1", "guide_a"))
        backups = list(self.path.parent.glob("guide_progress.json.corrupt.*.bak"))
        self.assertEqual(1, len(backups))
        self.assertIn('"characters": ', backups[0].read_text(encoding="utf-8"))

    def test_live_reader_observes_coordinated_peer_mutation(self) -> None:
        reader = GuideProgressService(self.path)
        writer = GuideProgressService(self.path)

        writer.set_manual_step_completed("character:1", "guide_a", "stage:a", True)

        self.assertIn("stage:a", reader.manual_steps("character:1", "guide_a"))

    def test_reload_observes_external_file_mutation(self) -> None:
        reader = GuideProgressService(self.path)
        payload = {
            "version": 1,
            "characters": {
                "character:1": {
                    "manual_steps": {
                        "guide_a": ["stage:external"],
                    }
                }
            },
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        reader.reload()

        self.assertIn("stage:external", reader.manual_steps("character:1", "guide_a"))


if __name__ == "__main__":
    unittest.main()
