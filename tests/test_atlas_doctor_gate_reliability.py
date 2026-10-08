from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.gates import (
    _decode_lines,
    _read_gate_progress,
    run_integrity_gate,
)


class DoctorIntegrityTimeoutTests(unittest.TestCase):
    def test_timeout_identifies_exact_blocking_group_from_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            owner = root / "tools" / "atlas_integrity.py"
            owner.parent.mkdir()
            owner.write_text("# test fixture", encoding="utf-8")

            def timed_out(_command, **kwargs):
                progress = Path(kwargs["env"]["ATLAS_INTEGRITY_PROGRESS_PATH"])
                progress.write_text(
                    '{"group":"META_INTEGRITY","event":"STARTED"}\n'
                    '{"group":"META_INTEGRITY","event":"FINISHED"}\n'
                    '{"group":"DIFF_TARGETS","event":"STARTED"}\n',
                    encoding="utf-8",
                )
                raise subprocess.TimeoutExpired(
                    cmd="atlas_integrity fast", timeout=1,
                    output=b"partial stdout", stderr=b"partial error",
                )

            with patch("tools.atlas_doctor_lib.gates.subprocess.run", side_effect=timed_out):
                result = run_integrity_gate(root, "fast", timeout=1)

            self.assertEqual(result["status"], "TIMEOUT")
            self.assertEqual(result["current_group"], "DIFF_TARGETS")
            self.assertIn("DIFF_TARGETS", result["reason"])
            self.assertEqual(result["stdout_tail"], ["partial stdout"])
            self.assertEqual(result["stderr_tail"], ["partial error"])
            self.assertEqual(result["group_progress"][-1]["event"], "STARTED")

    def test_invalid_progress_lines_are_ignored_without_false_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "partial.jsonl"
            p.write_text(
                '{"group":"IDENTITY","event":"STARTED"}\n'
                '{"group":"BROKEN","event":"BOGUS"}\n'
                '{"group":"INVALID","event":"FINISHED"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                _read_gate_progress(p), [{"group": "IDENTITY", "event": "STARTED"}]
            )
        self.assertEqual(_decode_lines(None), [])
        self.assertEqual(_decode_lines(b"\xff"), ["\ufffd"])


if __name__ == "__main__":
    unittest.main()
