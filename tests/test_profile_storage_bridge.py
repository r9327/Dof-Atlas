from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import storage
from app.constants import KEY_SELECTED_CHARACTER, KEY_TOPMOST
from app.services.profile_settings_service import ProfileSettingsService


class ProfileStorageBridgeTests(unittest.TestCase):
    def test_stale_legacy_profile_snapshot_preserves_modern_service_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "client_profiles.json"
            initial = storage.default_profiles()
            initial[KEY_SELECTED_CHARACTER] = "character:101"
            profile_path.write_text(json.dumps(initial), encoding="utf-8")

            with patch.object(storage, "PROFILE_FILE", profile_path):
                stale = storage.read_json(profile_path, storage.default_profiles())
                ProfileSettingsService(profile_path).set_selected_character("character:202")

                stale[KEY_TOPMOST] = True
                storage.write_json(profile_path, stale)

            final = ProfileSettingsService(profile_path).load()
            self.assertEqual(final[KEY_SELECTED_CHARACTER], "character:202")
            self.assertTrue(final[KEY_TOPMOST])

    def test_legacy_snapshot_cannot_write_noncanonical_selected_character(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "client_profiles.json"
            initial = storage.default_profiles()
            initial[KEY_SELECTED_CHARACTER] = "character:101"
            profile_path.write_text(json.dumps(initial), encoding="utf-8")

            with patch.object(storage, "PROFILE_FILE", profile_path):
                snapshot = storage.read_json(profile_path, storage.default_profiles())
                snapshot[KEY_SELECTED_CHARACTER] = "slot:2"
                with self.assertRaises(ValueError):
                    storage.write_json(profile_path, snapshot)

            final = ProfileSettingsService(profile_path).load()
            self.assertEqual(final[KEY_SELECTED_CHARACTER], "character:101")


if __name__ == "__main__":
    unittest.main()
