"""The state factories and cache stamps must stay cross-module compatible."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.file_stamp import (
    mtime_ctime_size_stamp, mtime_ctime_size_stamp_or_zero, mtime_size_stamp, resolved_mtime_size_stamp,
)
from app.core.progress_coordinator import empty_progress_payload


class CoreSharedStateTests(unittest.TestCase):
    def test_quest_progress_int_adapter_keeps_legacy_coercion(self) -> None:
        from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
        for value, expected in (("12", 12), (True, 1), (-2, -2), (None, None), ("bad", None)):
            with self.subTest(value=value):
                self.assertEqual(QuestProgressService._safe_int(value), expected)

    def test_progress_payload_is_fresh_and_versioned(self) -> None:
        first = empty_progress_payload()
        self.assertEqual(first, {"version": 1, "characters": {}})
        first["characters"]["character:1"] = {"done": {"123": True}}
        second = empty_progress_payload()
        self.assertEqual(second, {"version": 1, "characters": {}})
        self.assertIsNot(first["characters"], second["characters"])

    def test_file_stamps_match_existing_cache_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            self.assertEqual(mtime_size_stamp(None), (0, 0))
            self.assertEqual(mtime_size_stamp(path), (0, 0))
            self.assertEqual(resolved_mtime_size_stamp(path), (str(path.resolve()), 0, 0))
            path.write_bytes(b"Atlas cache")
            stat = path.stat()
            stamp = (int(stat.st_mtime_ns), int(stat.st_size))
            self.assertEqual(mtime_size_stamp(path), stamp)
            self.assertEqual(
                resolved_mtime_size_stamp(path), (str(path.resolve()), *stamp)
            )
            self.assertEqual(
                mtime_ctime_size_stamp(path),
                (int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size)),
            )
            self.assertEqual(mtime_ctime_size_stamp_or_zero(path), mtime_ctime_size_stamp(path))
            path.unlink()
            self.assertEqual(mtime_size_stamp(path), (0, 0))
            self.assertIsNone(mtime_ctime_size_stamp(path))
            self.assertEqual(mtime_ctime_size_stamp_or_zero(path), (0, 0, 0))


    def test_write_validation_is_shared_by_three_progress_services(self) -> None:
        from app.core.progress_coordinator import validate_progress_character_keys

        validate_progress_character_keys({"characters": {"character:1": {}}})
        validate_progress_character_keys({})
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            validate_progress_character_keys({"characters": []})
        for invalid in ("slot:1", "character:0", "character:01"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_progress_character_keys({"characters": {invalid: {}}})


if __name__ == "__main__":
    unittest.main()
