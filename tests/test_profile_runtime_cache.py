from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.pages.profile_write_cache as profile_cache


class ProfileRuntimeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        profile_cache.clear_profile_runtime_cache()

    def tearDown(self) -> None:
        profile_cache.clear_profile_runtime_cache()

    @staticmethod
    def _write(path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _reader(calls: list[Path]):
        def read(path: Path, default):
            resolved = Path(path)
            calls.append(resolved)
            try:
                return json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default

        return read

    def test_repeated_profile_reads_hit_cache_and_return_independent_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            self._write(path, {"selected": "character:1", "nested": {"value": 1}})
            calls: list[Path] = []

            with (
                patch.object(profile_cache, "PROFILE_FILE", path),
                patch.object(profile_cache, "_ORIGINAL_READ_JSON", self._reader(calls)),
            ):
                first = profile_cache.cached_read_json(path, {})
                first["selected"] = "mutated"
                first["nested"]["value"] = 99
                second = profile_cache.cached_read_json(path, {})

            self.assertEqual(len(calls), 1)
            self.assertEqual(second, {"selected": "character:1", "nested": {"value": 1}})
            self.assertIsNot(first, second)
            self.assertIsNot(first["nested"], second["nested"])

    def test_external_profile_replacement_invalidates_cached_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            self._write(path, {"selected": "character:1"})
            calls: list[Path] = []

            with (
                patch.object(profile_cache, "PROFILE_FILE", path),
                patch.object(profile_cache, "_ORIGINAL_READ_JSON", self._reader(calls)),
            ):
                self.assertEqual(profile_cache.cached_read_json(path, {}), {"selected": "character:1"})
                replacement = path.with_suffix(".tmp")
                self._write(replacement, {"selected": "character:2", "extra": True})
                replacement.replace(path)
                self.assertEqual(
                    profile_cache.cached_read_json(path, {}),
                    {"selected": "character:2", "extra": True},
                )

            self.assertEqual(len(calls), 2)

    def test_identical_profile_write_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            payload = {"selected": "character:1"}
            self._write(path, payload)
            read_calls: list[Path] = []
            write_calls: list[tuple[Path, object]] = []

            def write(resolved: Path, value: object) -> None:
                write_calls.append((Path(resolved), value))
                self._write(Path(resolved), value)

            with (
                patch.object(profile_cache, "PROFILE_FILE", path),
                patch.object(profile_cache, "_ORIGINAL_READ_JSON", self._reader(read_calls)),
                patch.object(profile_cache, "_ORIGINAL_WRITE_JSON", write),
            ):
                profile_cache.cached_write_json(path, dict(payload))

            self.assertEqual(read_calls, [])
            self.assertEqual(write_calls, [])

    def test_changed_profile_write_publishes_cache_for_next_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            self._write(path, {"selected": "character:1"})
            read_calls: list[Path] = []
            write_calls: list[tuple[Path, object]] = []

            def write(resolved: Path, value: object) -> None:
                resolved = Path(resolved)
                write_calls.append((resolved, value))
                replacement = resolved.with_suffix(".tmp")
                self._write(replacement, value)
                replacement.replace(resolved)

            with (
                patch.object(profile_cache, "PROFILE_FILE", path),
                patch.object(profile_cache, "_ORIGINAL_READ_JSON", self._reader(read_calls)),
                patch.object(profile_cache, "_ORIGINAL_WRITE_JSON", write),
            ):
                profile_cache.cached_write_json(path, {"selected": "character:2"})
                after = profile_cache.cached_read_json(path, {})

            self.assertEqual(write_calls, [])
            self.assertEqual(read_calls, [])
            self.assertEqual(after, {"selected": "character:2"})

    def test_non_profile_reads_and_writes_always_delegate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profile.json"
            other = root / "other.json"
            self._write(profile, {})
            self._write(other, {"value": 1})
            read_calls: list[Path] = []
            write_calls: list[tuple[Path, object]] = []

            def write(resolved: Path, value: object) -> None:
                write_calls.append((Path(resolved), value))

            with (
                patch.object(profile_cache, "PROFILE_FILE", profile),
                patch.object(profile_cache, "_ORIGINAL_READ_JSON", self._reader(read_calls)),
                patch.object(profile_cache, "_ORIGINAL_WRITE_JSON", write),
            ):
                self.assertEqual(profile_cache.cached_read_json(other, {}), {"value": 1})
                self.assertEqual(profile_cache.cached_read_json(other, {}), {"value": 1})
                profile_cache.cached_write_json(other, {"value": 2})

            self.assertEqual(read_calls, [other, other])
            self.assertEqual(write_calls, [(other, {"value": 2})])


if __name__ == "__main__":
    unittest.main()
