"""Focused, platform-independent tests for opt-in launch instrumentation."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.distribution import startup_trace


class StartupTraceTests(unittest.TestCase):
    def test_disabled_does_not_create_file_or_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "trace.jsonl"
            with patch.dict(os.environ, {
                "DOFUS_ATLAS_STARTUP_PROFILE": "0",
                "DOFUS_ATLAS_STARTUP_PROFILE_FILE": str(target),
            }, clear=True):
                startup_trace.record_startup_event("launcher_entry")
                self.assertNotIn("DOFUS_ATLAS_STARTUP_SESSION", os.environ)
            self.assertFalse(target.exists())

    def test_correlates_process_events_and_redacts_non_numeric_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "logs" / "trace.jsonl"
            with patch.dict(os.environ, {
                "DOFUS_ATLAS_STARTUP_PROFILE": "1",
                "DOFUS_ATLAS_STARTUP_PROFILE_FILE": str(target),
            }, clear=True):
                startup_trace.record_startup_event("launcher_entry", download_bytes=123,
                                                   secret="do-not-log")  # type: ignore[arg-type]
                session = os.environ["DOFUS_ATLAS_STARTUP_SESSION"]
                startup_trace.record_startup_event("home_visible", elapsed_ms=2.5)
            rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["event"] for row in rows], ["launcher_entry", "home_visible"])
            self.assertEqual([row["session"] for row in rows], [session, session])
            self.assertEqual(rows[0]["download_bytes"], 123)
            self.assertNotIn("secret", rows[0])
            self.assertGreaterEqual(rows[1]["t_ns"], rows[0]["t_ns"])
            self.assertEqual(rows[0]["pid"], os.getpid())

    def test_unwritable_trace_path_does_not_break_startup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "DOFUS_ATLAS_STARTUP_PROFILE": "1",
                "DOFUS_ATLAS_STARTUP_PROFILE_FILE": directory,
            }, clear=True):
                startup_trace.record_startup_event("launcher_entry")

    def test_max_size_stops_unbounded_trace_growth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "trace.jsonl"
            target.write_bytes(b"X" * 128)
            with patch.dict(os.environ, {
                "DOFUS_ATLAS_STARTUP_PROFILE": "1",
                "DOFUS_ATLAS_STARTUP_PROFILE_FILE": str(target),
            }, clear=True), patch.object(startup_trace, "_MAX_LOG_BYTES", 128):
                startup_trace.record_startup_event("launcher_entry")
            self.assertEqual(target.stat().st_size, 128)


if __name__ == "__main__":
    unittest.main()
