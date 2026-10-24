from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import validation_log as log


class LocalValidationLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.patch = patch.object(log, "LOG_DIR", self.directory)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        log._LAST.clear()

    def rows(self):
        path = self.directory / "atlas_validation.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_only_allowlisted_fields_are_written(self):
        log.record_validation("organizer_sessions", detected=2, verified=1,
                              unverified=1, primary=True, classes_verified=1,
                              character_name="PRIVATE_CHAR", pid=1234,
                              raw_title="PRIVATE_WINDOW", payload="PRIVATE_PACKET")
        output = (self.directory / "atlas_validation.jsonl").read_text(encoding="utf-8")
        self.assertEqual(self.rows()[0]["detected"], 2)
        self.assertNotIn("PRIVATE_", output)
        self.assertNotIn("pid", output)
        self.assertNotIn("payload", output)
        self.assertNotIn("raw_title", output)
        self.assertNotIn("character_name", output)

    def test_repeated_states_do_not_flood_disk(self):
        for _ in range(100):
            log.record_validation("network_status", running=True,
                                  calibrating=False, reason="running",
                                  mapping_present=True)
        self.assertEqual(len(self.rows()), 1)
        log.record_validation("network_status", running=False,
                              calibrating=False, reason="stopped")
        self.assertEqual(len(self.rows()), 2)

    def test_unknown_events_and_sensitive_strings_are_discarded(self):
        log.record_validation("bad_event", token="PRIVATE_TOKEN")
        self.assertFalse((self.directory / "atlas_validation.jsonl").exists())
        log.record_validation("network_status", reason="C:\\Users\\Private\\token.txt")
        self.assertEqual(self.rows()[0]["reason"], "unclassified")

    def test_log_rotates_without_exceeding_bound(self):
        path = self.directory / "atlas_validation.jsonl"
        path.write_text("x" * (log._MAX_BYTES + 1), encoding="utf-8")
        log.record_validation("organizer_favorite", selected=True, rejected=False,
                              verified=True, detected=2)
        self.assertTrue(path.with_suffix(".jsonl.old").exists())
        self.assertEqual(len(self.rows()), 1)
        self.assertTrue(self.rows()[0]["selected"])


if __name__ == "__main__":
    unittest.main()
