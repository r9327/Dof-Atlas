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

    def test_organizer_renders_exactly_eight_non_clipped_slots_without_internal_scroll_area(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.assertEqual(page.session_slot_count(), 8)
                self.assertEqual(len(page.session_slot_widgets), 8)
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

    def test_normal_rapid_speed_is_horizontal_and_legacy_modes_remain_accessible(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.organizer_page(Path(temporary)) as page:
                self.app.processEvents()
                normal = page.script_speed_normal
                rapid = page.script_speed_fast
                classic = page.script_speed_legacy
                instant = page.script_speed_instant
                self.assertEqual(normal.parent(), rapid.parent())
                self.assertEqual(classic.parent(), instant.parent())
                self.assertEqual(normal.y(), rapid.y())
                self.assertLess(normal.x(), rapid.x())
                self.assertEqual(classic.y(), instant.y())
                self.assertLess(classic.x(), instant.x())
                self.assertGreater(classic.y(), normal.y())
                for button in (normal, rapid, classic, instant):
                    self.assertTrue(button.isVisible())
                from app.constants import KEY_SCRIPT_SPEED, KEY_SCRIPT_SPEED_SCHEMA
                for value, selected in (
                    ("normal", normal), ("rapide", rapid),
                    ("classique", classic), ("instantane", instant),
                ):
                    page.profiles[KEY_SCRIPT_SPEED] = value
                    page.profiles[KEY_SCRIPT_SPEED_SCHEMA] = 2
                    page.update_script_speed_buttons()
                    for button in (normal, rapid, classic, instant):
                        self.assertEqual(
                            button.objectName(),
                            "segmentedButtonActive" if button is selected
                            else "segmentedButton",
                        )



if __name__ == "__main__":
    unittest.main()
