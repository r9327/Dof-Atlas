from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QScrollArea

import app.pages.organizer_page as organizer
import app.pages.organizer.character_sessions as organizer_sessions
from app.pages.organizer.organizer_ui import CharacterSlotsPanel


class OrganizerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_session_ids_refuse_fractional_boolean_and_corrupt_native_values(self):
        from app.pages.organizer.common import (
            session_hwnd, session_pid, session_is_detected, session_name,
        )

        for count in (2, 4, 6, 8):
            for hwnd in range(101, 101 + count):
                with self.subTest(count=count, hwnd=hwnd):
                    self.assertEqual(session_hwnd({"hwnd": hwnd}), hwnd)
                    self.assertEqual(session_hwnd({"hwnd": f" {hwnd} "}), hwnd)
                    self.assertTrue(session_is_detected({
                        "nom": "Witsis", "hwnd": hwnd,
                    }))
        bad_hwnds = (
            True, False, 101.0, 101.9, float("nan"), float("inf"),
            None, "-101", "+101", "101.5", object(), 0, -1, 2**64,
        )
        for raw in bad_hwnds:
            with self.subTest(hwnd=repr(raw)):
                self.assertEqual(session_hwnd({"hwnd": raw}), 0)
                self.assertFalse(session_is_detected({
                    "nom": "Witsis", "hwnd": raw,
                }))
        for raw in (None, False, True, float("inf"), 2**32, "1.5"):
            with self.subTest(pid=repr(raw)):
                self.assertEqual(session_pid({"pid": raw}), 0)
        self.assertEqual(session_pid({"pid": " 12345 "}), 12345)
        for invalid_name in (None, False, 101, object()):
            with self.subTest(name=repr(invalid_name)):
                self.assertEqual(session_name({"nom": invalid_name}), "")
                self.assertFalse(session_is_detected({
                    "nom": invalid_name, "hwnd": 101,
                }))

    @contextmanager
    def organizer_page(self, root: Path):
        profile = root / "client_profiles.json"
        client_index = root / "client_index.json"
        client_ini = root / "client_index.ini"
        profile.write_text("{}", encoding="utf-8")
        client_index.write_text(json.dumps({"clients": []}), encoding="utf-8")

        with (
            patch.object(organizer, "PROFILE_FILE", profile),
            patch.object(organizer_sessions, "PROFILE_FILE", profile),
            patch.object(organizer_sessions, "CLIENT_INDEX_JSON", client_index),
            patch.object(organizer_sessions, "CLIENT_INDEX_INI", client_ini),
            patch.object(organizer_sessions, "scan_unity_sessions", return_value=[]),
            patch.object(organizer.UnityWindowEventWatcher, "start", return_value=None),
            patch.object(organizer.UnityWindowEventWatcher, "stop", return_value=None),
        ):
            page = organizer.OrganizerPage(lambda _text: None, lambda *_args: None)
            try:
                page.render_sessions()
                page.resize(900, page.sizeHint().height())
                page.show()
                self.app.processEvents()
                yield page
            finally:
                page.close()
                page.deleteLater()
                self.app.processEvents()

    def test_organizer_duplicate_scanner_windows_never_hide_eighth_client(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.pages.organizer.common import session_hwnd, session_is_detected

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                page = Mock()
                page.character_order_service.sort_rows.side_effect = (
                    lambda rows, **_kwargs: rows
                )
                distinct = [
                    {"nom": f"Perso{i}", "hwnd": 101 + i}
                    for i in range(count)
                ]
                scanned = [
                    distinct[0],
                    {"nom": "Duplicated event", "hwnd": 101},
                    *distinct[1:],
                ]
                slots = CharacterSessionsMixin.build_session_slots(page, scanned)
                self.assertEqual(len(slots), 8)
                active = [row for row in slots if session_is_detected(row)]
                self.assertEqual(len(active), count)
                self.assertEqual(
                    tuple(session_hwnd(row) for row in active),
                    tuple(range(101, 101 + count)),
                )
                self.assertEqual(active[0]["nom"], "Perso0")

    def test_organizer_scanner_skips_malformed_rows_without_losing_eighth_window(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.pages.organizer.common import session_hwnd, session_is_detected

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                page = Mock()
                page.character_order_service.sort_rows.side_effect = (
                    lambda rows, **_kwargs: rows
                )
                valid = [
                    {"nom": f"Perso{i}", "hwnd": 101 + i}
                    for i in range(count)
                ]
                # Invalid native callback rows must never crash a refresh or
                # consume the fixed-size slot budget before the final client.
                scanned = [None, False, 123, "invalid", [],
                           {"nom": "Broken", "hwnd": 101.5},
                           *valid[:-1], object(), valid[-1]]
                slots = CharacterSessionsMixin.build_session_slots(page, scanned)
                active = [row for row in slots if session_is_detected(row)]
                self.assertEqual(len(slots), 8)
                self.assertEqual(len(active), count)
                self.assertEqual(
                    tuple(session_hwnd(row) for row in active),
                    tuple(range(101, 101 + count)),
                )

    def test_organizer_invalid_scanner_result_keeps_prior_sessions_2_4_6_8(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for count in (2, 4, 6, 8):
            for corrupt in (None, False, "broken", 42, {"nom": "wrong"},
                            [None, "broken", {"nom": "Broken", "hwnd": 101.5}]):
                with self.subTest(count=count, corrupt=repr(corrupt)):
                    page = Mock()
                    previous = [
                        {"nom": f"Perso{i}", "hwnd": 101 + i}
                        for i in range(count)
                    ]
                    page.sessions = previous
                    page.load_profiles.return_value = {}
                    page._scan_unity_sessions.return_value = corrupt
                    with patch.object(organizer_sessions.os, "name", "nt"):
                        refreshed = CharacterSessionsMixin.refresh_sessions_and_export(page)
                    self.assertFalse(refreshed)
                    self.assertIs(page.sessions, previous)
                    page.build_session_slots.assert_not_called()
                    page.export_client_index.assert_not_called()
                    page.sync_event_watcher_sessions.assert_not_called()
                    page.notify_sessions_changed.assert_not_called()

    def test_organizer_scanner_exception_preserves_prior_sessions_and_index(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        page = Mock()
        previous = [{"nom": "Perso1", "hwnd": 101}]
        page.sessions = previous
        page.load_profiles.return_value = {}
        page._scan_unity_sessions.side_effect = RuntimeError("scanner failed")
        with patch.object(organizer_sessions.os, "name", "nt"):
            self.assertFalse(CharacterSessionsMixin.refresh_sessions_and_export(page))
        self.assertIs(page.sessions, previous)
        page.export_client_index.assert_not_called()
        page.notify_sessions_changed.assert_not_called()

    def test_organizer_empty_successful_scan_clears_closed_windows(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.pages.organizer.common import session_is_detected

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                page = Mock()
                page.sessions = [
                    {"nom": f"Perso{i}", "hwnd": 101 + i}
                    for i in range(count)
                ]
                page.load_profiles.return_value = {}
                page._scan_unity_sessions.return_value = []
                page.character_order_service.sort_rows.side_effect = (
                    lambda rows, **_kwargs: rows
                )
                page.build_session_slots.side_effect = (
                    lambda rows: CharacterSessionsMixin.build_session_slots(page, rows)
                )
                with patch.object(organizer_sessions.os, "name", "nt"):
                    self.assertFalse(CharacterSessionsMixin.refresh_sessions_and_export(page))
                self.assertEqual(len(page.sessions), 8)
                self.assertFalse(any(session_is_detected(row) for row in page.sessions))
                page.export_client_index.assert_called_once()
                page.notify_sessions_changed.assert_called_once()

    def test_organizer_partial_corrupt_scan_keeps_all_valid_clients(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.pages.organizer.common import session_hwnd, session_is_detected

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                page = Mock()
                page.load_profiles.return_value = {}
                page._scan_unity_sessions.return_value = [
                    None, False, {"nom": "broken", "hwnd": 101.5},
                    *({"nom": f"Perso{i}", "hwnd": 101 + i}
                      for i in range(count)),
                ]
                page.character_order_service.sort_rows.side_effect = (
                    lambda rows, **_kwargs: rows
                )
                page.build_session_slots.side_effect = (
                    lambda rows: CharacterSessionsMixin.build_session_slots(page, rows)
                )
                with patch.object(organizer_sessions.os, "name", "nt"):
                    self.assertTrue(CharacterSessionsMixin.refresh_sessions_and_export(page))
                valid = [row for row in page.sessions if session_is_detected(row)]
                self.assertEqual(
                    tuple(session_hwnd(row) for row in valid),
                    tuple(range(101, 101 + count)),
                )
                page.export_client_index.assert_called_once()
                page.notify_sessions_changed.assert_called_once()

    def test_explicit_scan_failure_preserves_sessions_without_reload(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for outcome in (None, False, [None], RuntimeError("bad scanner")):
            with self.subTest(outcome=repr(outcome)):
                page = Mock()
                previous = [{"nom": "Perso", "hwnd": 101}]
                page.sessions = previous
                if isinstance(outcome, Exception):
                    page._scan_unity_sessions.side_effect = outcome
                else:
                    page._scan_unity_sessions.return_value = outcome
                with patch.object(organizer_sessions.os, "name", "nt"):
                    CharacterSessionsMixin.scan_sessions(page)
                self.assertIs(page.sessions, previous)
                page.export_client_index.assert_not_called()
                page.request_sessions_render.assert_not_called()
                page.sync_event_watcher_sessions.assert_not_called()
                page.reload_runtime_callback.assert_not_called()
                self.assertIn("conservées", page.status_callback.call_args.args[0])

    def test_window_event_scan_failure_preserves_roster_without_export(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for outcome in (None, {}, [{"nom": "Broken", "hwnd": 3.2}],
                        RuntimeError("bad scanner")):
            with self.subTest(outcome=repr(outcome)):
                page = Mock()
                previous = [{"nom": "Perso", "hwnd": 101}]
                page.sessions = previous
                if isinstance(outcome, Exception):
                    scan = patch.object(
                        CharacterSessionsMixin, "_scan_unity_sessions",
                        side_effect=outcome,
                    )
                else:
                    scan = patch.object(
                        CharacterSessionsMixin, "_scan_unity_sessions",
                        return_value=outcome,
                    )
                with patch.object(organizer_sessions.os, "name", "nt"), scan:
                    CharacterSessionsMixin.refresh_sessions_from_window_event(page)
                self.assertIs(page.sessions, previous)
                page.build_session_slots.assert_not_called()
                page.export_client_index.assert_not_called()
                page.request_sessions_render.assert_not_called()
                page.sync_event_watcher_sessions.assert_not_called()
                page.begin_release_identity_retries.assert_not_called()

    def test_generic_release_retry_failed_scan_retries_without_erasing_roster(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for outcome in (None, 123, [None], RuntimeError("bad scanner")):
            with self.subTest(outcome=repr(outcome)):
                page = Mock()
                previous = [{"nom": "Dofus", "hwnd": 101}]
                page.sessions = previous
                page.sessions_have_generic_names.return_value = True
                if isinstance(outcome, Exception):
                    scan = patch.object(
                        CharacterSessionsMixin, "_scan_unity_sessions",
                        side_effect=outcome,
                    )
                else:
                    scan = patch.object(
                        CharacterSessionsMixin, "_scan_unity_sessions",
                        return_value=outcome,
                    )
                with patch.object(organizer_sessions.os, "name", "nt"), scan:
                    CharacterSessionsMixin.retry_release_identity(page)
                self.assertIs(page.sessions, previous)
                page.export_client_index.assert_not_called()
                page.sync_event_watcher_sessions.assert_not_called()
                page.schedule_next_release_identity_retry.assert_called_once()

    def test_successful_empty_scans_clear_stale_slots_across_all_entrypoints(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.pages.organizer.common import session_is_detected

        for action in ("scan_sessions", "refresh_sessions_from_window_event",
                       "retry_release_identity"):
            for count in (2, 4, 6, 8):
                with self.subTest(action=action, clients=count):
                    page = Mock()
                    page.sessions = [
                        {"nom": f"Perso{i}", "hwnd": 101 + i}
                        for i in range(count)
                    ]
                    page.detected_session_count.return_value = 0
                    page.sessions_have_generic_names.side_effect = [True, False]
                    page.session_identity_signature.side_effect = [
                        ("old_roster",), ("empty_roster",),
                    ]
                    page._scan_unity_sessions.return_value = []
                    page.load_profiles.return_value = {}
                    page.character_order_service.sort_rows.side_effect = (
                        lambda rows, **_kwargs: rows
                    )
                    page.build_session_slots.side_effect = (
                        lambda rows: CharacterSessionsMixin.build_session_slots(page, rows)
                    )
                    with (
                        patch.object(organizer_sessions.os, "name", "nt"),
                        patch.object(
                            CharacterSessionsMixin, "_scan_unity_sessions",
                            return_value=[],
                        ),
                    ):
                        getattr(CharacterSessionsMixin, action)(page)
                    self.assertEqual(len(page.sessions), 8)
                    self.assertFalse(any(session_is_detected(row) for row in page.sessions))
                    page.export_client_index.assert_called_once()

    def test_native_window_event_never_truncates_corrupt_hwnd_or_id(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.windows_embed import EVENT_SYSTEM_FOREGROUND

        for invalid in (None, True, False, 101.0, 101.9, "101", -1, 0, 2**64):
            with self.subTest(hwnd=repr(invalid)):
                page = Mock()
                CharacterSessionsMixin.on_unity_window_event(
                    page, EVENT_SYSTEM_FOREGROUND, invalid
                )
                page.active_session_callback.assert_not_called()
                page.window_event_refresh_timer.start.assert_not_called()
        for invalid_event in (None, True, 3.0, "3", float("inf")):
            with self.subTest(event=repr(invalid_event)):
                page = Mock()
                CharacterSessionsMixin.on_unity_window_event(
                    page, invalid_event, 101
                )
                page.active_session_callback.assert_not_called()
                page.window_event_refresh_timer.start.assert_not_called()

    def test_native_window_event_preserves_exact_2_4_6_8_client_selection(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin
        from app.windows_embed import EVENT_SYSTEM_FOREGROUND

        for count in (2, 4, 6, 8):
            for hwnd in range(101, 101 + count):
                with self.subTest(clients=count, hwnd=hwnd):
                    page = Mock()
                    CharacterSessionsMixin.on_unity_window_event(
                        page, EVENT_SYSTEM_FOREGROUND, hwnd
                    )
                    page.active_session_callback.assert_called_once_with(hwnd)
                    page.window_event_refresh_timer.start.assert_called_once_with()
        page = Mock()
        CharacterSessionsMixin.on_unity_window_event(
            page, EVENT_SYSTEM_FOREGROUND + 1, 101
        )
        page.active_session_callback.assert_not_called()
        page.window_event_refresh_timer.start.assert_called_once_with()

    def test_organizer_order_and_favorite_never_coerce_foreign_window_ids(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for count in (2, 4, 6, 8):
            for index in range(count):
                with self.subTest(count=count, index=index):
                    hwnd = 101 + index
                    page = Mock()
                    page.profiles = {}
                    page.primary_token_for_session.return_value = ""
                    valid = {"nom": f"Perso{index}", "hwnd": str(hwnd)}
                    keys = CharacterSessionsMixin.session_order_keys(page, valid)
                    self.assertIn(f"hwnd:{hwnd}", keys)
                    for invalid in (float(hwnd), True, f"+{hwnd}", 2**64):
                        row = {"nom": f"Perso{index}", "hwnd": invalid}
                        bad = CharacterSessionsMixin.session_order_keys(page, row)
                        self.assertFalse(any(key.startswith("hwnd:") for key in bad))
                        with patch.object(
                            organizer_sessions, "record_validation",
                        ):
                            CharacterSessionsMixin.set_primary_window(page, row)
                        page.primary_token_for_session.assert_called_with(
                            f"Perso{index}", 0, row,
                        )
                        page.reload_runtime_callback.assert_not_called()
                        page.primary_token_for_session.reset_mock()

    def test_organizer_autogroup_reports_accepted_rejected_and_legacy_launch(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for accepted in (True, False, None):
            with self.subTest(accepted=accepted):
                page = Mock()
                page.sessions = [
                    {"nom": "Leader", "hwnd": 101, "pid": 1001},
                    {"nom": "Friend", "hwnd": 202, "pid": 1002},
                ]
                page.launch_auto_group_callback.return_value = accepted
                CharacterSessionsMixin.launch_auto_group(page)
                page.export_client_index.assert_called_once()
                page.launch_auto_group_callback.assert_called_once()
                message = page.status_callback.call_args.args[0]
                if accepted is True:
                    self.assertIn("en cours", message)
                    self.assertNotIn("invitation(s)", message)
                elif accepted is False:
                    self.assertIn("non lancé", message)
                else:
                    self.assertIn("non confirmé", message)

    def test_organizer_autogroup_passes_all_unique_detected_clients_2_4_6_8(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                page = Mock()
                page.sessions = [
                    {"nom": f"Perso-{i}", "hwnd": 101 + i, "pid": 1001 + i}
                    for i in range(count)
                ]
                page.launch_auto_group_callback.return_value = True
                CharacterSessionsMixin.launch_auto_group(page)
                page.export_client_index.assert_called_once()
                entries = page.launch_auto_group_callback.call_args.args[0]
                self.assertEqual(len(entries), count)
                self.assertEqual(
                    {entry["handle"] for entry in entries},
                    set(range(101, 101 + count)),
                )
                self.assertIn("en cours", page.status_callback.call_args.args[0])

    def test_organizer_autogroup_refuses_duplicate_or_unaddressable_clients(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        for count in (2, 4, 6, 8):
            sessions = [
                {"nom": f"Perso{i}", "hwnd": 101 + i, "pid": 1001 + i}
                for i in range(count)
            ]
            for invalid in ("duplicate_name", "duplicate_hwnd", "empty_invite_name"):
                with self.subTest(count=count, invalid=invalid):
                    page = Mock()
                    page.sessions = [dict(session) for session in sessions]
                    if invalid == "duplicate_name":
                        page.sessions[-1]["nom"] = page.sessions[0]["nom"] + " - Dofus"
                    elif invalid == "duplicate_hwnd":
                        page.sessions[-1]["hwnd"] = page.sessions[0]["hwnd"]
                    else:
                        page.sessions[-1]["nom"] = " - Dofus"
                    CharacterSessionsMixin.launch_auto_group(page)
                    page.export_client_index.assert_not_called()
                    page.launch_auto_group_callback.assert_not_called()
                    self.assertIn("non lancé", page.status_callback.call_args.args[0])
                    self.assertIn("Actualiser Organizer", page.status_callback.call_args.args[0])

    def test_organizer_autogroup_callback_exception_fails_safely_without_ui_crash(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        page = Mock()
        page.sessions = [
            {"nom": "Leader", "hwnd": 101, "pid": 1001},
            {"nom": "Friend", "hwnd": 202, "pid": 1002},
        ]
        page.launch_auto_group_callback.side_effect = RuntimeError("runtime failed")
        with self.assertLogs("app.pages.organizer.character_sessions", level="ERROR"):
            CharacterSessionsMixin.launch_auto_group(page)
        self.assertIn("non lancé", page.status_callback.call_args.args[0])

    def test_organizer_autogroup_does_not_claim_success_without_any_sessions(self):
        from unittest.mock import Mock
        from app.pages.organizer.character_sessions import CharacterSessionsMixin

        page = Mock()
        page.sessions = []
        CharacterSessionsMixin.launch_auto_group(page)
        page.launch_auto_group_callback.assert_not_called()
        page.export_client_index.assert_not_called()
        self.assertIn("aucun personnage", page.status_callback.call_args.args[0])


    def test_busy_organizer_next_button_does_not_scan_live_windows(self):
        from unittest.mock import Mock
        import main as app_main

        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                fake = Mock()
                fake.quit_requested = False
                fake._background_services_stopped = False
                fake._ensure_runtime.return_value.macro_lock.active_label = "Auto groupe"
                app_main.AtlasWindow.launch_next_character(fake)
                fake._ensure_runtime.assert_called_once()
                fake._ensure_runtime.return_value.switch_character.activate_next.assert_not_called()
                fake.set_status.assert_called_once_with(
                    "Personnage suivant indisponible : macro déjà en cours."
                )

    def test_armed_mirror_blocks_both_shell_navigation_buttons(self):
        from unittest.mock import Mock
        import main as app_main

        for label, method in (
            ("suivant", app_main.AtlasWindow.launch_next_character),
            ("précédent", app_main.AtlasWindow.launch_previous_character),
        ):
            with self.subTest(action=label):
                shell = Mock()
                shell.quit_requested = False
                shell._background_services_stopped = False
                runtime = shell._ensure_runtime.return_value
                runtime.mirror_armed = True
                runtime.macro_lock.active_label = ""
                method(shell)
                runtime.switch_character.activate_next.assert_not_called()
                runtime.switch_character.activate_previous.assert_not_called()
                shell.set_status.assert_called_once_with(
                    "Arrêter Miroir avant de changer de personnage."
                )

    def test_next_button_never_resurrects_runtime_during_shutdown(self):
        from unittest.mock import Mock
        import main as app_main

        for stopped_attr in ("quit_requested", "_background_services_stopped"):
            with self.subTest(shutdown=stopped_attr):
                fake = Mock()
                fake.quit_requested = False
                fake._background_services_stopped = False
                setattr(fake, stopped_attr, True)
                app_main.AtlasWindow.launch_next_character(fake)
                fake._ensure_runtime.assert_not_called()
                fake.set_status.assert_not_called()

    def test_next_button_aborts_if_shutdown_begins_during_runtime_init(self):
        from unittest.mock import Mock
        import main as app_main

        for stopped_attr in ("quit_requested", "_background_services_stopped"):
            with self.subTest(shutdown=stopped_attr):
                fake = Mock()
                fake.quit_requested = False
                fake._background_services_stopped = False
                runtime = Mock()
                def init_and_close():
                    setattr(fake, stopped_attr, True)
                    return runtime
                fake._ensure_runtime.side_effect = init_and_close
                app_main.AtlasWindow.launch_next_character(fake)
                fake._ensure_runtime.assert_called_once_with()
                runtime.switch_character.activate_next.assert_not_called()
                fake.set_status.assert_not_called()

    def test_idle_organizer_next_button_preserves_normal_action(self):
        from unittest.mock import Mock
        import main as app_main

        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                fake = Mock()
                fake.quit_requested = False
                fake._background_services_stopped = False
                runtime = fake._ensure_runtime.return_value
                runtime.macro_lock.active_label = ""
                runtime.switch_character.activate_next.return_value = accepted
                app_main.AtlasWindow.launch_next_character(fake)
                runtime.switch_character.activate_next.assert_called_once_with()
                if accepted:
                    fake.set_status.assert_not_called()
                else:
                    fake.set_status.assert_called_once_with(
                        "Personnage suivant : aucune autre fenêtre DOFUS activable."
                    )

    def test_organizer_auto_group_and_zaap_cannot_launch_during_shutdown(self):
        from unittest.mock import Mock
        import main as app_main

        fake = Mock()
        fake.quit_requested = False
        fake._background_services_stopped = False
        for method, args in (
            (app_main.AtlasWindow.launch_auto_group,
             ([{"name": "Friend", "handle": 202}],)),
            (app_main.AtlasWindow.launch_zaap, ("/zaap 1,2",)),
        ):
            for stopped_attr in ("quit_requested", "_background_services_stopped"):
                with self.subTest(method=method.__name__, attr=stopped_attr):
                    setattr(fake, stopped_attr, True)
                    self.assertFalse(method(fake, *args))
                    fake.reload_runtime.assert_not_called()
                    fake._ensure_runtime.assert_not_called()
                    setattr(fake, stopped_attr, False)


    def test_busy_organizer_quick_action_refuses_before_session_refresh(self):
        from unittest.mock import Mock
        import main as app_main

        for count in (2, 4, 6, 8):
            for busy in ("Auto groupe", "Auto zaap", "Miroir", "Switch clique"):
                for method, args in (
                    (app_main.AtlasWindow.launch_auto_group,
                     ([{"name": "Friend", "handle": 202}],)),
                    (app_main.AtlasWindow.launch_zaap, ("/zaap 1,2",)),
                ):
                    with self.subTest(clients=count, busy=busy, method=method.__name__):
                        fake = Mock()
                        fake.quit_requested = False
                        fake._background_services_stopped = False
                        fake.runtime.macro_lock.active_label = busy
                        fake.runtime.settings.clients = [
                            SimpleNamespace(handle=101 + i) for i in range(count)
                        ]
                        old = fake.runtime.settings
                        self.assertFalse(method(fake, *args))
                        fake.reload_runtime.assert_not_called()
                        fake._ensure_runtime.assert_not_called()
                        self.assertIs(fake.runtime.settings, old)

    def test_organizer_macro_launch_aborts_if_shutdown_begins_during_reload(self):
        from unittest.mock import Mock
        import main as app_main

        for method, args in (
            (app_main.AtlasWindow.launch_auto_group,
             ([{"name": "Friend", "handle": 202}],)),
            (app_main.AtlasWindow.launch_zaap, ("/zaap 1,2",)),
        ):
            with self.subTest(method=method.__name__):
                fake = Mock()
                fake.runtime = None
                fake.quit_requested = False
                fake._background_services_stopped = False
                fake.reload_runtime.side_effect = lambda: setattr(
                    fake, "_background_services_stopped", True,
                )
                self.assertFalse(method(fake, *args))
                fake.reload_runtime.assert_called_once()
                fake._ensure_runtime.assert_not_called()

    def test_organizer_macro_launch_still_returns_runtime_acceptance(self):
        from unittest.mock import Mock
        import main as app_main

        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                fake = Mock()
                fake.runtime = None
                fake.quit_requested = False
                fake._background_services_stopped = False
                fake._ensure_runtime.return_value.launch_auto_group.return_value = accepted
                fake._ensure_runtime.return_value.launch_zaap.return_value = accepted
                self.assertIs(app_main.AtlasWindow.launch_auto_group(
                    fake, [{"name": "Friend", "handle": 202}],
                ), accepted)
                self.assertIs(app_main.AtlasWindow.launch_zaap(
                    fake, "/zaap 1,2",
                ), accepted)

    def test_stop_button_cancels_radial_before_runtime_callback(self):
        from unittest.mock import Mock
        from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin

        events = []
        page = SimpleNamespace(
            _radial_controller=Mock(),
            stop_runtime_callback=lambda: events.append("runtime_stop"),
            status_callback=Mock(),
        )
        page._radial_controller.cancel.side_effect = lambda: events.append("radial_cancel")
        OrganizerHotkeysMixin.stop_script(page)
        self.assertEqual(events, ["radial_cancel", "runtime_stop"])
        page.status_callback.assert_not_called()

    def test_runtime_red_indicator_cancels_held_radial_controller(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                controller = page._radial_controller
                with patch.object(controller, "cancel", wraps=controller.cancel) as cancel:
                    page.set_runtime_active(True)
                    cancel.assert_not_called()
                    page.set_runtime_active(False)
                    cancel.assert_called_once_with()

    def test_refused_mirror_toggle_never_turns_emergency_led_green(self):
        from unittest.mock import Mock
        import main as app_main

        shell = Mock()
        shell.quit_requested = False
        shell._background_services_stopped = False
        organizer = Mock()
        shell.page_widgets = {"Organizer": organizer}
        shell.runtime._running = True
        shell.runtime._admin_ok = True
        shell.runtime.mirror_armed = False
        shell.runtime.macro_lock.emergency_latched = True
        shell.runtime.toggle_mirror.return_value = False
        shell.update_runtime_badge.side_effect = (
            lambda connected: app_main.AtlasWindow.update_runtime_badge(
                shell, connected,
            )
        )
        self.assertFalse(app_main.AtlasWindow.toggle_mirror(shell))
        organizer.set_runtime_active.assert_called_with(False)
        organizer.set_mirror_arm_active.assert_called_with(False)
        # Only a real Relancer/runtime-ready state can turn the badge green.
        shell.runtime.macro_lock.emergency_latched = False
        app_main.AtlasWindow.update_runtime_badge(shell, True)
        organizer.set_runtime_active.assert_called_with(True)
        shell.runtime._admin_ok = False
        self.assertFalse(app_main.AtlasWindow.toggle_mirror(shell))
        organizer.set_runtime_active.assert_called_with(False)

    def test_emergency_stop_and_reconfiguration_are_distinct(self):
        from unittest.mock import Mock
        import main as app_main

        shell = Mock()
        shell.runtime = Mock()
        app_main.AtlasWindow.stop_runtime(shell)
        shell.runtime.emergency_stop.assert_called_once_with(
            "bouton stop", latch=True,
        )
        shell.runtime.emergency_stop.reset_mock()
        app_main.AtlasWindow.stop_runtime(shell, True)
        shell.runtime.emergency_stop.assert_called_once_with(
            "reconfiguration Organizer", latch=False,
        )

    def test_runtime_badge_cannot_turn_green_while_emergency_stop_is_latched(self):
        from unittest.mock import Mock
        import main as app_main

        shell = Mock()
        organizer_widget = Mock()
        shell.page_widgets = {"Organizer": organizer_widget}
        shell.runtime = SimpleNamespace(
            macro_lock=SimpleNamespace(emergency_latched=True),
            mirror_armed=False,
        )
        app_main.AtlasWindow.update_runtime_badge(shell, True)
        organizer_widget.set_runtime_active.assert_called_once_with(False)
        organizer_widget.set_mirror_arm_active.assert_called_once_with(False)

        organizer_widget.reset_mock()
        shell.runtime.macro_lock.emergency_latched = False
        app_main.AtlasWindow.update_runtime_badge(shell, True)
        organizer_widget.set_runtime_active.assert_called_once_with(True)

    def test_mirror_toggle_refusal_after_stop_cannot_reenable_green_badge(self):
        from unittest.mock import Mock
        import main as app_main

        shell = Mock()
        shell.quit_requested = False
        shell._background_services_stopped = False
        runtime = shell.runtime
        runtime._running = True
        runtime._admin_ok = True
        runtime.macro_lock.emergency_latched = True
        runtime.toggle_mirror.return_value = False
        self.assertFalse(app_main.AtlasWindow.toggle_mirror(shell))
        shell.update_runtime_badge.assert_called_once_with(False)
        runtime.toggle_mirror.assert_called_once_with()

    def test_explicit_relancer_refuses_busy_workers_before_green_light(self):
        from unittest.mock import Mock
        import main as app_main

        for allowed in (False, True):
            with self.subTest(allowed=allowed):
                shell = Mock()
                shell.quit_requested = False
                shell._background_services_stopped = False
                runtime = shell._ensure_runtime.return_value
                runtime._running = True
                runtime.macro_lock.resume_after_stop.return_value = allowed
                app_main.AtlasWindow.reload_runtime(shell, True)
                runtime.macro_lock.resume_after_stop.assert_called_once()
                if allowed:
                    runtime.reload_hotkeys.assert_called_once_with(True)
                    shell.update_runtime_badge.assert_not_called()
                else:
                    runtime.reload_hotkeys.assert_not_called()
                    shell.update_runtime_badge.assert_called_once_with(False)
                    shell.set_status.assert_called_once()
                runtime.macro_lock.resume_after_stop.reset_mock()
                runtime.reload_hotkeys.reset_mock()
                app_main.AtlasWindow.reload_runtime(shell, False)
                runtime.macro_lock.resume_after_stop.assert_not_called()
                runtime.reload_hotkeys.assert_called_once_with(False)

    def test_character_slots_panel_calculates_height_from_grid_geometry(self):
        refresh = QFrame()
        refresh.setFixedSize(32, organizer.BUTTON_HEIGHT)
        panel = CharacterSlotsPanel(
            refresh,
            slot_count=organizer.SESSION_SLOT_COUNT,
            row_height=organizer.CHARACTER_SLOT_HEIGHT,
            card_padding=organizer.CARD_PADDING,
            card_spacing=organizer.CARD_SPACING,
        )
        try:
            for index in range(organizer.SESSION_SLOT_COUNT):
                slot = QFrame()
                slot.setFixedHeight(organizer.CHARACTER_SLOT_HEIGHT)
                panel.add_slot(slot, index)

            expected_grid_height = 4 * organizer.CHARACTER_SLOT_HEIGHT + 3 * panel.vertical_spacing
            self.assertEqual(panel.row_count(), 4)
            self.assertEqual(panel.slot_grid_height(), expected_grid_height)
            self.assertEqual(panel.grid.count(), organizer.SESSION_SLOT_COUNT)
            self.assertEqual(panel.findChildren(QScrollArea), [])
            self.assertEqual(panel.sizeHint().height(), panel.calculated_height())
            self.assertEqual(panel.height(), panel.calculated_height())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_organizer_always_displays_eight_reorderable_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.assertEqual(page.session_slot_count(), 8)
                self.assertEqual(len(page.session_slot_widgets), 8)
                self.assertFalse(hasattr(page.sessions_panel, "expand_button"))
                self.assertEqual(page.sessions_panel.findChildren(QScrollArea), [])
                self.assertEqual(
                    sorted(page.sessions_panel.grid_position(index) for _widget, index in page.session_slot_widgets),
                    [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)],
                )
                self.assertGreaterEqual(page.sessions_panel.height(), page.sessions_panel.calculated_height())
                self.assertEqual(page.sessions_content.height(), page.sessions_panel.slot_grid_height())
                content_rect = page.sessions_content.rect()
                for widget, _index in page.session_slot_widgets:
                    geometry = widget.geometry()
                    self.assertEqual(geometry.height(), organizer.CHARACTER_SLOT_HEIGHT)
                    self.assertGreaterEqual(geometry.top(), content_rect.top())
                    self.assertLessEqual(geometry.bottom(), content_rect.bottom())
                    # No unexplained circular per-character selector.
                    from PySide6.QtWidgets import QPushButton
                    self.assertFalse(any(
                        button.text() in {"◉", "○"}
                        for button in widget.findChildren(QPushButton)
                    ))

    def test_hidden_organizer_evicts_only_slots_and_preserves_live_watcher(self):
        from PySide6.QtCore import QCoreApplication, QEvent

        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.assertEqual(len(page.session_slot_widgets), 8)
                watcher = page.session_event_watcher
                previous_sessions = list(page.sessions)
                page.hide()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                self.assertEqual(page.sessions_panel.grid.count(), 0)
                self.assertEqual(page.session_slot_widgets, [])
                self.assertTrue(page._sessions_render_dirty)
                self.assertIs(page.session_event_watcher, watcher)
                self.assertEqual(page.sessions, previous_sessions)
                page.show()
                self.app.processEvents()
                self.assertEqual(page.sessions_panel.grid.count(), 8)
                self.assertEqual(len(page.session_slot_widgets), 8)
                self.assertIs(page.session_event_watcher, watcher)

    def test_reorder_keeps_exactly_eight_slots_and_persists_detected_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                page.sessions = page.build_session_slots(
                    [
                        {"nom": "Alpha", "hwnd": 101, "pid": 1},
                        {"nom": "Beta", "hwnd": 202, "pid": 2},
                    ]
                )
                self.assertEqual(len(page.sessions), 8)
                self.assertTrue(page.move_session_to_slot(0, 1))
                page.save_session_order()
                expected = tuple(
                    page.persisted_session_order_key(session)
                    for session in page.sessions
                    if organizer.session_is_detected(session)
                )
                self.assertEqual(page.character_order_service.load_order(), expected)
                self.assertEqual(len(page.sessions), 8)


    def test_zaap_legacy_position_controls_are_hidden_without_losing_destination_ui(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.assertFalse(page.zaap.show_position_controls)
                for control in (
                    page.zaap.position_label,
                    page.zaap.position_wrapper,
                    page.zaap.lock_button,
                    page.zaap.calibrate_button,
                ):
                    self.assertTrue(control.isHidden())
                self.assertTrue(page.zaap.search_input.isVisible())
                self.assertIsNotNone(page.zaap.suggestion_popup)
                self.assertTrue(page.zaap.show_favorites)

    def test_mirror_requires_explicit_arm_and_navigation_buttons_share_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.app.processEvents()
                self.assertTrue(page.mirror_arm_button.isHidden())
                self.assertFalse(page.mirror_arm_button.isEnabled())
                self.assertIs(
                    page.mirror_mode_button.parentWidget(),
                    page.mirror_toggle_hotkey_button.parentWidget(),
                )
                from app.constants import KEY_ORGANIZER_MACRO_MODE
                page.profiles[KEY_ORGANIZER_MACRO_MODE] = "mirror"
                page.update_macro_mode_buttons()
                self.assertTrue(page.mirror_arm_button.isEnabled())
                self.assertEqual(page.mirror_arm_button.text(), "Activer Miroir")
                self.assertEqual(page.mirror_mode_button.text(), "Miroir")
                self.assertFalse(page._mirror_arm_active)
                self.assertFalse(page.switch_character.isEnabled())
                self.assertFalse(page.switch_click.isEnabled())
                self.assertTrue(page.next_character.isEnabled())
                self.assertTrue(page.previous_character.isEnabled())
                self.assertTrue(page.next_character_hotkey_button.isEnabled())
                self.assertTrue(page.previous_character_hotkey_button.isEnabled())
                page.set_mirror_arm_active(True)
                self.assertEqual(page.mirror_arm_button.text(), "Arrêter Miroir")
                self.assertEqual(page.mirror_mode_button.objectName(), "primaryButton")
                self.assertFalse(page.next_character.isEnabled())
                self.assertFalse(page.previous_character.isEnabled())
                page.set_mirror_arm_active(False)
                self.assertEqual(page.mirror_arm_button.text(), "Activer Miroir")
                self.assertEqual(page.mirror_mode_button.objectName(), "segmentedButtonActive")
                self.assertTrue(page.next_character.isEnabled())
                self.assertTrue(page.previous_character.isEnabled())
                previous_cell = page.previous_character.parentWidget()
                next_cell = page.next_character.parentWidget()
                self.assertIs(previous_cell.parentWidget(), next_cell.parentWidget())
                self.assertEqual(previous_cell.y(), next_cell.y())
                self.assertLess(previous_cell.x(), next_cell.x())
                self.assertEqual(page.previous_character.height(), page.next_character.height())
                self.assertTrue(page.mirror_arm_button.isHidden())

    def test_organizer_three_panels_and_small_window_scroll(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                page.resize(1380, 900)
                self.app.processEvents()
                self.assertIs(page.controls_panels_grid.itemAtPosition(1, 0).widget(), page.macro_panel)
                self.assertIs(page.controls_panels_grid.itemAtPosition(1, 1).widget(), page.quick_actions_panel)
                self.assertIs(page.controls_panels_grid.itemAtPosition(1, 2).widget(), page.controls_panel)
                for column, (header, panel) in enumerate(zip(
                    page._organizer_panel_headers, page._organizer_panels
                )):
                    self.assertIs(page.controls_panels_grid.itemAtPosition(0, column).widget(), header)
                    self.assertLess(header.height(), panel.height())
                self.assertTrue(all(
                    panel.graphicsEffect() is None for panel in
                    (*page._organizer_panels, page.zaap_panel, page.sessions_panel)
                ))
                self.assertEqual(page.macro_panel.height(), 154)
                self.assertIn("border-image: none", page.styleSheet())
                self.assertEqual(len(page.session_slot_widgets), 8)
                self.assertIs(page.runtime_status_dot.parentWidget(), page.organizer_scroll.widget())
                self.assertLessEqual(page.macro_panel.y(), page.quick_actions_panel.y())
                self.assertEqual(page.macro_panel.y(), page.controls_panel.y())
                page.resize(1000, 470)
                self.app.processEvents()
                self.assertIs(page.controls_panels_grid.itemAtPosition(3, 0).widget(), page.controls_panel)
                self.assertEqual(len(page.session_slot_widgets), 8)
                self.assertGreater(page.organizer_scroll.verticalScrollBar().maximum(), 0)
                page.organizer_scroll.ensureWidgetVisible(page.sessions_panel)
                self.app.processEvents()
                self.assertGreater(page.organizer_scroll.verticalScrollBar().value(), 0)
                self.assertEqual(page.organizer_scroll.horizontalScrollBar().maximum(), 0)

    def test_mirror_button_is_explicit_arm_and_badge_does_not_arm(self):
        from app.constants import KEY_ORGANIZER_MACRO_MODE
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                states = []
                armed = [False]
                def toggle():
                    armed[0] = not armed[0]
                    states.append(armed[0])
                    return armed[0]
                page.mirror_arm_callback = toggle
                page.reload_runtime_callback = lambda *_args: None
                page.stop_runtime_callback = lambda *_args: None
                self.assertFalse(page._mirror_arm_active)
                self.assertEqual(page.profiles.get(KEY_ORGANIZER_MACRO_MODE, "macro"), "macro")
                page.mirror_toggle_hotkey_button.click()
                self.assertEqual(states, [])
                page.mirror_mode_button.click()
                self.assertEqual(page.profiles[KEY_ORGANIZER_MACRO_MODE], "mirror")
                self.assertEqual(states, [True])
                self.assertTrue(page._mirror_arm_active)
                self.assertFalse(page.next_character.isEnabled())
                page.mirror_mode_button.click()
                self.assertEqual(states, [True, False])
                self.assertFalse(page._mirror_arm_active)
                self.assertTrue(page.next_character.isEnabled())
                page.macro_mode_button.click()
                self.assertEqual(page.profiles[KEY_ORGANIZER_MACRO_MODE], "macro")
                self.assertFalse(page._mirror_arm_active)

    def test_navigation_enable_badges_share_canonical_switch_flag(self):
        from app.constants import KEY_SWITCH_CHARACTER
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.assertTrue(page.profiles[KEY_SWITCH_CHARACTER])
                for badge in (page.next_character_enable_button,
                              page.previous_character_enable_button):
                    self.assertEqual(badge.text(), "ON")
                    self.assertTrue(badge.isEnabled())
                page.next_character_enable_button.click()
                self.assertFalse(page.profiles[KEY_SWITCH_CHARACTER])
                self.assertFalse(page.next_character.isEnabled())
                self.assertFalse(page.previous_character.isEnabled())
                self.assertEqual(page.next_character_enable_button.text(), "OFF")
                self.assertEqual(page.previous_character_enable_button.text(), "OFF")
                page.previous_character_enable_button.click()
                self.assertTrue(page.profiles[KEY_SWITCH_CHARACTER])
                self.assertTrue(page.next_character.isEnabled())
                self.assertTrue(page.previous_character.isEnabled())
                self.assertEqual(page.next_character_enable_button.text(), "ON")
                self.assertEqual(page.previous_character_enable_button.text(), "ON")
                # Mirror can only arm after the profile selects Mirror mode.
                from app.constants import KEY_ORGANIZER_MACRO_MODE
                page.profiles[KEY_ORGANIZER_MACRO_MODE] = "mirror"
                page.update_macro_mode_buttons()
                page.set_mirror_arm_active(True)
                self.assertFalse(page.next_character_enable_button.isEnabled())
                self.assertFalse(page.previous_character_enable_button.isEnabled())
                page.set_mirror_arm_active(False)
                self.assertTrue(page.next_character_enable_button.isEnabled())

    def test_embedded_hotkey_badges_leave_space_for_full_button_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                page.resize(1380, 900)
                self.app.processEvents()
                for action, reserve in (
                    (page.radial_select_button, 40),
                    (page.previous_character, 75),
                    (page.next_character, 75),
                    (page.mirror_mode_button, 40),
                ):
                    with self.subTest(button=action.text()):
                        available = action.width() - reserve - 4
                        label_width = action.fontMetrics().horizontalAdvance(action.text())
                        self.assertGreaterEqual(available, label_width)
                self.assertEqual(
                    page.previous_character_enable_button.parentWidget(),
                    page.previous_character_hotkey_button.parentWidget(),
                )
                self.assertEqual(
                    page.next_character_enable_button.parentWidget(),
                    page.next_character_hotkey_button.parentWidget(),
                )

    def test_three_visible_speed_presets_and_compact_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.app.processEvents()
                normal = page.script_speed_normal
                rapid = page.script_speed_fast
                instant = page.script_speed_instant
                classic = page.script_speed_legacy
                self.assertTrue(page.script_speed_title.isVisible())
                self.assertEqual(page.script_speed_title.text(), "Vitesse :")
                self.assertIs(page.script_speed_title.parentWidget(), normal.parentWidget())
                self.assertIs(
                    normal.parentWidget().parentWidget().parentWidget(),
                    page.controls_panel,
                )
                self.assertEqual(page.script_speed_title.y(), normal.y())
                self.assertLess(page.script_speed_title.x(), normal.x())
                self.assertLessEqual(
                    instant.x() + instant.width(), instant.parentWidget().width(),
                )
                self.assertTrue(classic.isHidden())
                self.assertEqual(normal.parent(), rapid.parent())
                self.assertEqual(normal.parent(), instant.parent())
                self.assertEqual(normal.y(), rapid.y())
                self.assertEqual(rapid.y(), instant.y())
                self.assertLess(normal.x(), rapid.x())
                self.assertLess(rapid.x(), instant.x())
                self.assertTrue(all(button.isVisible() for button in (normal, rapid, instant)))
                self.assertEqual(page.radial_select_button.height(), page.switch_fake.height())
                self.assertEqual(page.radial_select_button.text(), "Sélection perso")
                self.assertIs(page.stop_script_button.parentWidget(),
                              page.stop_script_hotkey_button.parentWidget())
                self.assertGreaterEqual(page.stop_script_hotkey_button.x(), 0)
                self.assertLessEqual(
                    page.stop_script_hotkey_button.x() + page.stop_script_hotkey_button.width(),
                    page.stop_script_button.width(),
                )
                from app.constants import KEY_SCRIPT_SPEED, KEY_SCRIPT_SPEED_SCHEMA
                for value, selected in (
                    ("normal", normal), ("rapide", rapid),
                    ("instantane", instant),
                ):
                    page.profiles[KEY_SCRIPT_SPEED] = value
                    page.profiles[KEY_SCRIPT_SPEED_SCHEMA] = 2
                    page.update_script_speed_buttons()
                    for button in (normal, rapid, instant):
                        self.assertEqual(
                            button.objectName(),
                            "segmentedButtonActive" if button is selected
                            else "segmentedButton",
                        )
                # Legacy profiles retain their slower timing, but Classique
                # is never displayed or misrepresented as Normal.
                page.profiles[KEY_SCRIPT_SPEED] = "classique"
                page.update_script_speed_buttons()
                self.assertTrue(classic.isHidden())
                self.assertTrue(all(
                    button.objectName() == "segmentedButton"
                    for button in (normal, rapid, instant)
                ))


if __name__ == "__main__":
    unittest.main()
