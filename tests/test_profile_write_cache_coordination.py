from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.constants import KEY_SELECTED_CHARACTER
from app.pages import profile_write_cache
from app.services.profile_settings_service import ProfileSettingsService


class ProfileWriteCacheCoordinationTests(unittest.TestCase):
    def test_stale_legacy_snapshot_replays_only_its_own_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text(
                json.dumps(
                    {
                        KEY_SELECTED_CHARACTER: "character:101",
                        "__topmost__": False,
                        "organizer_option": False,
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(profile_write_cache, "PROFILE_FILE", profile_path):
                profile_write_cache.clear_profile_runtime_cache()
                stale = profile_write_cache.cached_read_json(profile_path, {})
                stale["organizer_option"] = True

                ProfileSettingsService(profile_path).set_selected_character("character:202")
                profile_write_cache.cached_write_json(profile_path, stale)

                final = ProfileSettingsService(profile_path).load()
                self.assertEqual(final[KEY_SELECTED_CHARACTER], "character:202")
                self.assertTrue(final["organizer_option"])
                self.assertFalse(final["__topmost__"])

    def test_legacy_topmost_write_preserves_unrelated_newer_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profiles.json"
            profile_path.write_text(
                json.dumps({"__topmost__": False, "last_quest": 1}),
                encoding="utf-8",
            )

            with patch.object(profile_write_cache, "PROFILE_FILE", profile_path):
                profile_write_cache.clear_profile_runtime_cache()
                stale = profile_write_cache.cached_read_json(profile_path, {})
                stale["__topmost__"] = True

                ProfileSettingsService(profile_path).set_value("last_quest", 99)
                profile_write_cache.cached_write_json(profile_path, stale)

                final = ProfileSettingsService(profile_path).load()
                self.assertTrue(final["__topmost__"])
                self.assertEqual(final["last_quest"], 99)


if __name__ == "__main__":
    unittest.main()
