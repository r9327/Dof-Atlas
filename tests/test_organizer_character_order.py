from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import KEY_DEBUG_MODE, KEY_SESSION_ORDER
import app.pages.organizer_page as organizer
from app.services.character_order_service import CharacterOrderService


class OrganizerCharacterOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @contextmanager
    def organizer_page(
        self,
        root: Path,
        payload: dict[str, object] | None = None,
        *,
        sessions_changed_callback=None,
    ):
        profile = root / "client_profiles.json"
        client_index = root / "client_index.json"
        client_ini = root / "client_index.ini"
        profile.write_text(json.dumps(payload or {}), encoding="utf-8")
        client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")

        with (
            patch.object(organizer, "PROFILE_FILE", profile),
            patch.object(organizer, "CLIENT_INDEX_JSON", client_index),
            patch.object(organizer, "CLIENT_INDEX_INI", client_ini),
            patch.object(organizer, "scan_unity_sessions", return_value=[]),
            patch.object(organizer.UnityWindowEventWatcher, "start", return_value=None),
            patch.object(organizer.UnityWindowEventWatcher, "stop", return_value=None),
        ):
            page = organizer.OrganizerPage(
                lambda _text: None,
                lambda *_args: None,
                sessions_changed_callback=sessions_changed_callback,
            )
            try:
                yield page, profile, client_index
            finally:
                page.deleteLater()
                self.app.processEvents()

    def test_build_slots_uses_canonical_order_before_previous_visual_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {KEY_SESSION_ORDER: ["alpha", "beta", "gamma"]}
            with self.organizer_page(root, payload) as (page, _profile, _client_index):
                page.sessions = [
                    {"nom": "Gamma - Cra", "hwnd": 30},
                    {"nom": "Alpha - Iop", "hwnd": 10},
                ]

                ordered = page.build_session_slots(
                    [
                        {"nom": "Gamma - Cra", "hwnd": 300},
                        {"nom": "Alpha - Iop", "hwnd": 100},
                    ]
                )

                self.assertEqual(
                    [organizer.session_name(row) for row in ordered[:2]],
                    ["Alpha - Iop", "Gamma - Cra"],
                )
                self.assertEqual(len(ordered), organizer.SESSION_SLOT_COUNT)
                self.assertEqual(
                    page.character_order_service.load_order(),
                    ("alpha", "beta", "gamma"),
                )

    def test_apply_saved_order_uses_canonical_order_without_clearing_current_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {KEY_SESSION_ORDER: ["alpha", "beta"]}
            with self.organizer_page(root, payload) as (page, profile, client_index):
                page.sessions = page.build_session_slots(
                    [
                        {"nom": "Alpha - Iop", "hwnd": 101, "pid": 11},
                        {"nom": "Beta - Cra", "hwnd": 202, "pid": 22},
                    ]
                )
                current_sessions = list(page.sessions)

                other_instance = CharacterOrderService(profile)
                self.assertTrue(other_instance.save_labels(["Beta", "Alpha"]))
                page.profiles = page.load_profiles()

                reordered = page.apply_saved_session_order(current_sessions)

                self.assertEqual(
                    [organizer.clean_auto_group_name(organizer.session_name(row)) for row in page.sessions[:2]],
                    ["Alpha", "Beta"],
                )
                self.assertEqual(
                    [organizer.clean_auto_group_name(organizer.session_name(row)) for row in reordered[:2]],
                    ["Beta", "Alpha"],
                )

                page.sessions = reordered
                page.export_client_index()

                self.assertEqual(
                    page.character_order_service.load_order(),
                    ("beta", "alpha"),
                )
                exported = json.loads(client_index.read_text(encoding="utf-8"))
                self.assertEqual(
                    [row["character_name"] for row in exported["clients"]],
                    ["Beta", "Alpha"],
                )

    def test_offline_character_keeps_anchor_and_new_character_is_appended(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {KEY_SESSION_ORDER: ["alpha", "beta", "gamma"]}
            with self.organizer_page(root, payload) as (page, profile, _client_index):
                page.sessions = page.build_session_slots(
                    [
                        {"nom": "Delta - Cra", "hwnd": 40},
                        {"nom": "Gamma - Sadida", "hwnd": 30},
                        {"nom": "Alpha - Iop", "hwnd": 10},
                    ]
                )

                self.assertEqual(
                    [organizer.clean_auto_group_name(organizer.session_name(row)) for row in page.sessions[:3]],
                    ["Alpha", "Gamma", "Delta"],
                )

                page.export_client_index()

                self.assertEqual(
                    page.character_order_service.load_order(),
                    ("alpha", "beta", "gamma", "delta"),
                )
                persisted = json.loads(profile.read_text(encoding="utf-8"))
                self.assertEqual(
                    persisted[KEY_SESSION_ORDER],
                    ["alpha", "beta", "gamma", "delta"],
                )

    def test_organizer_reorder_updates_canonical_order_and_notifies_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            notifications: list[bool] = []
            payload = {KEY_SESSION_ORDER: ["alpha", "beta", "gamma"]}
            with self.organizer_page(
                root,
                payload,
                sessions_changed_callback=lambda: notifications.append(True),
            ) as (page, _profile, _client_index):
                page.sessions = page.build_session_slots(
                    [
                        {"nom": "Gamma - Cra", "hwnd": 30},
                        {"nom": "Alpha - Iop", "hwnd": 10},
                    ]
                )
                page._last_notified_session_signature = page.session_identity_signature()

                page.reorder_session(0, 1)

                self.assertEqual(
                    [organizer.clean_auto_group_name(organizer.session_name(row)) for row in page.sessions[:2]],
                    ["Gamma", "Alpha"],
                )
                self.assertEqual(
                    page.character_order_service.load_order(),
                    ("gamma", "beta", "alpha"),
                )
                self.assertEqual(notifications, [True])

    def test_sparse_legacy_order_keeps_slot_hotkey_migration_without_becoming_canonical_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_order = ["Alpha", "", "Beta", "", "", "", "", ""]
            payload = {
                KEY_SESSION_ORDER: legacy_order,
                "Alpha": "F5",
                "Beta": "F7",
            }
            with self.organizer_page(root, payload) as (page, profile, _client_index):
                self.assertEqual(page.slot_hotkey_label(0), "F5")
                self.assertEqual(page.slot_hotkey_label(2), "F7")
                self.assertEqual(
                    page.character_order_service.load_order(),
                    ("alpha", "beta"),
                )
                self.assertEqual(page.profiles[KEY_SESSION_ORDER], ["alpha", "beta"])

                persisted = json.loads(profile.read_text(encoding="utf-8"))
                self.assertEqual(persisted[KEY_SESSION_ORDER], legacy_order)

    def test_saving_other_organizer_settings_does_not_overwrite_newer_canonical_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {KEY_SESSION_ORDER: ["alpha", "beta", "gamma"]}
            with self.organizer_page(root, payload) as (page, profile, _client_index):
                other_instance = CharacterOrderService(profile)
                self.assertTrue(other_instance.save_labels(["Gamma", "Alpha", "Beta"]))
                self.assertEqual(
                    other_instance.load_order(),
                    ("gamma", "alpha", "beta"),
                )

                page.profiles[KEY_DEBUG_MODE] = True
                page.save_profiles(page.profiles)

                persisted = json.loads(profile.read_text(encoding="utf-8"))
                self.assertEqual(
                    persisted[KEY_SESSION_ORDER],
                    ["gamma", "alpha", "beta"],
                )
                self.assertTrue(persisted[KEY_DEBUG_MODE])


if __name__ == "__main__":
    unittest.main()
