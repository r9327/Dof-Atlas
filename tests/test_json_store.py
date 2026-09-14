from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.json_store import read_json_resilient, write_json_atomic
from local_dofus_data import utils


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

    def test_atomic_writer_orders_file_sync_replace_and_directory_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            operations: list[str] = []
            real_replace = utils.os.replace

            def replace(source, target) -> None:
                operations.append("replace")
                real_replace(source, target)

            with (
                patch.object(
                    utils,
                    "_flush_and_sync",
                    side_effect=lambda handle: (
                        handle.flush(),
                        operations.append("file_fsync"),
                    ),
                ),
                patch.object(utils.os, "replace", side_effect=replace),
                patch.object(
                    utils,
                    "_sync_parent_directory",
                    side_effect=lambda _directory: operations.append("directory_fsync"),
                ),
            ):
                utils.save_json_atomic(path, {"revision": 1})

            self.assertEqual(operations, ["file_fsync", "replace", "directory_fsync"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"revision": 1})

    def test_file_sync_failure_preserves_previous_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"revision": 1}', encoding="utf-8")

            with patch.object(utils, "_flush_and_sync", side_effect=OSError("fsync failed")):
                with self.assertRaisesRegex(OSError, "fsync failed"):
                    utils.save_json_atomic(path, {"revision": 2})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"revision": 1})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_replace_failure_preserves_previous_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"revision": 1}', encoding="utf-8")

            with patch.object(utils.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    utils.save_json_atomic(path, {"revision": 2})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"revision": 1})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_directory_sync_failure_is_reported_after_valid_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"revision": 1}', encoding="utf-8")

            with patch.object(
                utils,
                "_sync_parent_directory",
                side_effect=OSError("directory fsync failed"),
            ):
                with self.assertRaisesRegex(OSError, "directory fsync failed"):
                    utils.save_json_atomic(path, {"revision": 2})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"revision": 2})


if __name__ == "__main__":
    unittest.main()
