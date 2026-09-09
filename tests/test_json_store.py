from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.json_store import read_json_resilient, write_json_atomic


class JsonStoreTests(unittest.TestCase):
    def test_corrupt_json_is_backed_up_before_default_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"broken": ', encoding="utf-8")

            payload = read_json_resilient(path, {"default": True})

            self.assertEqual(payload, {"default": True})
            backups = list(Path(tmp).glob("settings.json.corrupt.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), '{"broken": ')

    def test_atomic_writer_round_trips_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            write_json_atomic(path, {"name": "Éliotrope"})
            self.assertEqual(read_json_resilient(path, {}), {"name": "Éliotrope"})


if __name__ == "__main__":
    unittest.main()
