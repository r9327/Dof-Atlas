from __future__ import annotations

import unittest
from unittest.mock import patch

import app.core.settings as settings
from app.constants import KEY_PRIMARY_WINDOW


class OrganizerPersistedWindowIdentityTests(unittest.TestCase):
    def _load(self, clients, primary=0, profile=None):
        payload = {
            "clients": clients,
            "global_hotkeys": {"primary_handle": primary},
        }
        with (
            patch.object(settings, "read_json_file", return_value=payload),
            patch.object(settings, "load_profile_payload",
                         return_value=profile or {}),
            patch.object(settings, "read_zaap_button_ratios", return_value=None),
        ):
            return settings.load_settings()

    def test_rejects_nonintegral_aliases_without_dropping_valid_clients(self):
        invalid = (
            True, False, 202.0, 202.9, float("nan"), float("inf"),
            "202.0", "2.02e2", "2e2", "+202", "-202", "٢٠٢",
            "", "  ", None, 0, -1, 2**64, 2**128, "9" * 5000,
        )
        clients = [
            {"handle": 101, "index": 1},
            *({"handle": value, "index": 2} for value in invalid),
            {"handle": 202, "index": 2},
            {"handle": " 303 ", "index": 3},
        ]
        loaded = self._load(clients)
        self.assertEqual(
            tuple(client.handle for client in loaded.clients),
            (101, 202, 303),
        )
        self.assertEqual(
            tuple(client.index for client in loaded.clients),
            (1, 2, 3),
        )

    def test_favorite_rejects_float_bool_and_overflow_aliases(self):
        for value in (True, False, 202.0, 202.9, float("inf"),
                      "202.0", "+202", "-202", 2**64, "9" * 5000):
            with self.subTest(value=repr(value)):
                loaded = self._load([{"handle": 202}], primary=value)
                self.assertEqual(loaded.primary_handle, 0)

    def test_decimal_string_and_native_integer_favorites_are_supported(self):
        for value in (202, "202", " 202 "):
            with self.subTest(value=repr(value)):
                loaded = self._load([{"handle": 202}], primary=value)
                self.assertEqual(loaded.primary_handle, 202)

    def test_legacy_explicit_favorite_token_uses_same_strict_range(self):
        for token, expected in (
            ("hwnd:202", 202), ("hwnd:202.9", 0), ("hwnd:+202", 0),
            ("hwnd:18446744073709551616", 0),
        ):
            with self.subTest(token=token):
                loaded = self._load(
                    [{"handle": 202}], primary=None,
                    profile={KEY_PRIMARY_WINDOW: token},
                )
                self.assertEqual(loaded.primary_handle, expected)

    def test_signed_native_hwnd_max_is_accepted_without_truncation(self):
        maximum = 2**64 - 1
        loaded = self._load(
            [{"handle": maximum, "index": 1}], primary=maximum,
        )
        self.assertEqual(loaded.clients[0].handle, maximum)
        self.assertEqual(loaded.primary_handle, maximum)


    def test_corrupt_clients_container_is_treated_as_empty_roster(self):
        for invalid in (None, False, True, 202, 101.5,
                        "not a roster", {"handle": 202}):
            with self.subTest(value=repr(invalid)):
                loaded = self._load(invalid)
                self.assertEqual(loaded.clients, ())

    def test_slot_rejects_fractional_or_boolean_alias_without_losing_client(self):
        for bad_index in (True, False, 1.75, 1.0, "1.0", "+1", "-1", "٩"):
            with self.subTest(index=repr(bad_index)):
                loaded = self._load([
                    {"handle": 101, "index": 1},
                    {"handle": 202, "index": bad_index},
                ])
                self.assertEqual(
                    tuple(c.handle for c in loaded.clients), (101, 202),
                )
                self.assertEqual(
                    tuple(c.index for c in loaded.clients), (1, 2),
                )

    def test_legacy_decimal_string_slot_is_preserved(self):
        loaded = self._load([
            {"handle": 101, "index": " 1 "},
            {"handle": 202, "index": "2"},
        ])
        self.assertEqual(tuple(c.index for c in loaded.clients), (1, 2))



if __name__ == "__main__":
    unittest.main()
