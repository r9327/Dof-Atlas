from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.constants import KEY_PRIMARY_WINDOW
from app.core.settings import AtlasSettings
from app.pages.organizer.character_sessions import CharacterSessionsMixin


class OrganizerIdentityOverflowTests(unittest.TestCase):
    def test_settings_client_lookup_skips_bad_hwnds_and_keeps_valid_slot(self):
        valid = SimpleNamespace(handle=202, index=2)
        owner = SimpleNamespace(clients=(
            SimpleNamespace(handle=float("inf"), index=0),
            SimpleNamespace(handle=None, index=1),
            SimpleNamespace(handle=True, index=3),
            SimpleNamespace(handle=202.5, index=4),
            SimpleNamespace(handle="9" * 5000, index=5),
            SimpleNamespace(handle=2**128, index=6),
            valid,
        ))
        self.assertIs(AtlasSettings.client_by_handle(owner, 202), valid)
        self.assertIs(AtlasSettings.client_by_handle(owner, "202"), valid)

    def test_settings_client_lookup_rejects_invalid_requested_hwnd(self):
        owner = SimpleNamespace(clients=(
            SimpleNamespace(handle=101, index=1),
        ))
        for value in (
            None, True, False, float("nan"), float("inf"), 101.5,
            0, -1, "invalid", "9" * 5000, 2**128, object(),
        ):
            with self.subTest(handle=repr(value)[:36]):
                self.assertIsNone(AtlasSettings.client_by_handle(owner, value))

    def test_settings_client_lookup_never_converts_float_to_another_client(self):
        client = SimpleNamespace(handle=101, index=1)
        owner = SimpleNamespace(clients=(client,))
        self.assertIsNone(AtlasSettings.client_by_handle(owner, 101.9))
        self.assertIsNone(AtlasSettings.client_by_handle(
            SimpleNamespace(clients=(SimpleNamespace(handle=101.9),)), 101,
        ))

    def test_verified_identity_scan_skips_invalid_digit_strings(self):
        owner = CharacterSessionsMixin()
        owner.network_character_bindings_file = Path(
            "/path/that/does/not/exist/network-bindings.json"
        )
        row = {"source": "verified_network_identity", "name": "Valid"}
        payload = {"characters": {
            "²": row,  # Unicode isdigit() is True but int("²") raises ValueError.
            "9" * 5000: row,  # Python's integer-string limit refuses this.
            "101": row,
        }}
        with patch(
            "app.pages.organizer.character_sessions.read_json",
            return_value=payload,
        ):
            self.assertEqual(owner._verified_character_rows(), ((101, row),))

    def test_session_order_ignores_infinite_hwnd(self):
        owner = CharacterSessionsMixin()
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(hwnd=str(value)):
                keys = owner.session_order_keys({"nom": "Witsis", "hwnd": value})
                self.assertTrue(keys)
                self.assertFalse(any(key.startswith("hwnd:") for key in keys))

    def test_favorite_does_not_change_on_corrupted_hwnd(self):
        owner = CharacterSessionsMixin()
        owner.profiles = {KEY_PRIMARY_WINDOW: "original"}
        owner.primary_token_for_session = Mock(return_value="")
        owner.detected_session_count = Mock(return_value=0)
        owner.status_callback = Mock()
        with patch(
            "app.pages.organizer.character_sessions.record_validation",
        ) as record:
            owner.set_primary_window({"nom": "Witsis", "hwnd": float("inf")})
        owner.primary_token_for_session.assert_called_once_with(
            "Witsis", 0, {"nom": "Witsis", "hwnd": float("inf")},
        )
        self.assertEqual(owner.profiles[KEY_PRIMARY_WINDOW], "original")
        record.assert_called_once()
        owner.status_callback.assert_called_once()

    def test_verified_identity_still_matches_unique_name_when_pid_overflows(self):
        owner = CharacterSessionsMixin()
        owner.sessions = [{"nom": "Witsis", "hwnd": 101, "pid": 42}]
        owner._verified_character_rows = Mock(return_value=((
            101, {"pid": float("inf"), "name": "Witsis",
                  "class_key": "panda"},
        ),))
        with (
            patch(
                "app.pages.organizer.character_sessions.session_is_detected",
                return_value=True,
            ),
            patch(
                "app.pages.organizer.character_sessions.session_name",
                return_value="Witsis",
            ),
            patch(
                "app.pages.organizer.character_sessions.session_pid",
                return_value=42,
            ),
            patch(
                "app.pages.organizer.character_sessions.dofus_class_key_from_window_name",
                return_value="panda",
            ),
        ):
            self.assertEqual(
                owner.verified_character_token_for_session(owner.sessions[0]),
                "character:101",
            )


if __name__ == "__main__":
    unittest.main()
