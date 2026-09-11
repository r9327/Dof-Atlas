from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import storage
import app.constants as constants
from app.constants import KEY_SELECTED_CHARACTER, KEY_TOPMOST
from app.services.profile_settings_service import ProfileSettingsService


ROOT = Path(__file__).resolve().parents[1]


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

    def test_profile_write_without_bridge_baseline_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "client_profiles.json"
            initial = storage.default_profiles()
            initial[KEY_SELECTED_CHARACTER] = "character:101"
            profile_path.write_text(json.dumps(initial), encoding="utf-8")

            payload = dict(initial)
            payload[KEY_SELECTED_CHARACTER] = "character:202"
            with (
                patch.object(storage, "PROFILE_FILE", profile_path),
                patch.object(constants, "PROFILE_FILE", profile_path),
            ):
                storage._PROFILE_READ_STATE.path = None
                storage._PROFILE_READ_STATE.baseline = None
                with self.assertRaisesRegex(RuntimeError, "ProfileSettingsService"):
                    storage.write_json(profile_path, payload)

            final = ProfileSettingsService(profile_path).load()
            self.assertEqual(final[KEY_SELECTED_CHARACTER], "character:101")

    def test_organizer_routes_profile_snapshot_through_targeted_service_delta(self) -> None:
        tree = ast.parse(
            (ROOT / "app" / "pages" / "organizer_page.py").read_text(encoding="utf-8")
        )
        organizer = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OrganizerPage"
        )
        load_profiles = next(
            node
            for node in organizer.body
            if isinstance(node, ast.FunctionDef) and node.name == "load_profiles"
        )
        save_profiles = next(
            node
            for node in organizer.body
            if isinstance(node, ast.FunctionDef) and node.name == "save_profiles"
        )

        load_source = ast.unparse(load_profiles)
        save_source = ast.unparse(save_profiles)

        self.assertIn("self._profiles_baseline = dict(cleaned)", load_source)
        self.assertIn("ProfileSettingsService(PROFILE_FILE).update_values", save_source)
        self.assertIn("remove_keys=removals", save_source)
        self.assertNotIn("write_json(PROFILE_FILE", save_source)


if __name__ == "__main__":
    unittest.main()
