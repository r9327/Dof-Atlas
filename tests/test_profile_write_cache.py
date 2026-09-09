from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.pages import profile_write_cache


class ProfileWriteCacheTests(unittest.TestCase):
    def test_identical_profile_skips_atomic_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client_profiles.json"
            payload = {"selected": "character:1", "order": ["Alpha"]}
            path.write_text(json.dumps(payload), encoding="utf-8")

            with (
                patch.object(profile_write_cache, "PROFILE_FILE", path),
                patch.object(profile_write_cache, "_ORIGINAL_WRITE_JSON") as write_json,
            ):
                profile_write_cache.cached_write_json(path, dict(payload))

            write_json.assert_not_called()

    def test_changed_profile_uses_original_writer_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client_profiles.json"
            path.write_text(json.dumps({"selected": "character:1"}), encoding="utf-8")
            changed = {"selected": "character:2"}

            with patch.object(profile_write_cache, "PROFILE_FILE", path):
                profile_write_cache.cached_write_json(path, changed)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), changed)

    def test_non_profile_json_never_pays_read_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "client_profiles.json"
            other = Path(tmp) / "other.json"
            payload = {"value": 1}

            with (
                patch.object(profile_write_cache, "PROFILE_FILE", profile),
                patch.object(profile_write_cache, "_ORIGINAL_WRITE_JSON") as write_json,
            ):
                profile_write_cache.cached_write_json(other, payload)

            write_json.assert_called_once_with(other, payload)


if __name__ == "__main__":
    unittest.main()
