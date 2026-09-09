from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import CLIENT_INDEX_INI, CLIENT_INDEX_JSON
from app.pages import organizer_page
from app.pages.organizer_lazy_page import OrganizerPage as LazyOrganizerPage
from app.pages.organizer_page import OrganizerPage


def _profiles() -> dict[str, object]:
    return dict(organizer_page.default_profiles())


def _build_page() -> OrganizerPage:
    return OrganizerPage(
        lambda _text: None,
        lambda *_args: None,
        lambda: None,
        lambda _entries: None,
        lambda _text: None,
        lambda *_args: None,
        sessions_changed_callback=lambda: None,
    )


def _isolated_organizer_patches():
    return (
        patch.object(organizer_page, "read_json", return_value=_profiles()),
        patch.object(organizer_page, "write_json", return_value=None),
        patch.object(organizer_page, "write_text_atomic", return_value=None),
        patch.object(organizer_page.UnityWindowEventWatcher, "start", return_value=False),
        patch.object(OrganizerPage, "auto_scan_sessions_on_startup", return_value=None),
    )


def test_concrete_organizer_module_exposes_lazy_page() -> None:
    # The concrete module is the canonical import surface. The package no longer
    # mutates or re-exports page classes during import.
    assert OrganizerPage is LazyOrganizerPage
    assert organizer_page.OrganizerPage is LazyOrganizerPage


def test_hidden_organizer_defers_session_rows_and_shadows_until_first_show() -> None:
    app = QApplication.instance() or QApplication([])
    patches = _isolated_organizer_patches()
    for active_patch in patches:
        active_patch.start()
    try:
        page = _build_page()

        assert page.isVisible() is False
        assert page._sessions_render_dirty is True
        assert page.session_slot_widgets == []
        assert page.macro_panel.graphicsEffect() is None
        assert page.quick_actions_panel.graphicsEffect() is None
        assert page._pending_shadow_frames

        page.show()
        app.processEvents()

        assert page._sessions_render_dirty is False
        assert len(page.session_slot_widgets) == 8
        assert page.macro_panel.graphicsEffect() is not None
        assert page.quick_actions_panel.graphicsEffect() is not None
        assert page._pending_shadow_frames == []

        page.close()
        page.deleteLater()
        app.processEvents()
    finally:
        for active_patch in reversed(patches):
            active_patch.stop()


def test_hidden_session_refresh_marks_render_dirty_without_rebuilding_rows() -> None:
    app = QApplication.instance() or QApplication([])
    patches = _isolated_organizer_patches()
    for active_patch in patches:
        active_patch.start()
    try:
        page = _build_page()
        page.show()
        app.processEvents()
        assert len(page.session_slot_widgets) == 8

        page.hide()
        app.processEvents()
        previous_widgets = list(page.session_slot_widgets)

        page.sessions[0] = {"nom": "Testeur - Pandawa", "hwnd": 101, "pid": 202}
        page.render_sessions()

        assert page._sessions_render_dirty is True
        assert page.session_slot_widgets == previous_widgets

        page.show()
        app.processEvents()

        assert page._sessions_render_dirty is False
        assert len(page.session_slot_widgets) == 8
        assert page.session_slot_widgets != previous_widgets

        page.close()
        page.deleteLater()
        app.processEvents()
    finally:
        for active_patch in reversed(patches):
            active_patch.stop()


def test_identical_client_index_export_does_not_write_twice() -> None:
    app = QApplication.instance() or QApplication([])
    with (
        patch.object(organizer_page, "read_json", return_value=_profiles()),
        patch.object(organizer_page, "write_json", return_value=None) as write_json,
        patch.object(organizer_page, "write_text_atomic", return_value=None) as write_text,
        patch.object(organizer_page.UnityWindowEventWatcher, "start", return_value=False),
        patch.object(OrganizerPage, "auto_scan_sessions_on_startup", return_value=None),
    ):
        page = _build_page()

        initial_json_writes = sum(
            1 for call in write_json.call_args_list if call.args and call.args[0] == CLIENT_INDEX_JSON
        )
        initial_ini_writes = sum(
            1 for call in write_text.call_args_list if call.args and call.args[0] == CLIENT_INDEX_INI
        )
        assert initial_json_writes == 1
        assert initial_ini_writes == 1

        page.export_client_index()
        assert sum(
            1 for call in write_json.call_args_list if call.args and call.args[0] == CLIENT_INDEX_JSON
        ) == initial_json_writes
        assert sum(
            1 for call in write_text.call_args_list if call.args and call.args[0] == CLIENT_INDEX_INI
        ) == initial_ini_writes

        page.sessions[0] = {"nom": "Testeur - Pandawa", "hwnd": 101, "pid": 202}
        page.export_client_index()
        assert sum(
            1 for call in write_json.call_args_list if call.args and call.args[0] == CLIENT_INDEX_JSON
        ) == initial_json_writes + 1
        assert sum(
            1 for call in write_text.call_args_list if call.args and call.args[0] == CLIENT_INDEX_INI
        ) == initial_ini_writes + 1

        page.deleteLater()
        app.processEvents()


def test_reload_after_async_scan_reuses_sessions_without_second_win32_scan() -> None:
    app = QApplication.instance() or QApplication([])
    patches = _isolated_organizer_patches()
    for active_patch in patches:
        active_patch.start()
    try:
        page = _build_page()
        page.sessions = page.build_session_slots(
            [{"nom": "Testeur - Pandawa", "hwnd": 101, "pid": 202}]
        )
        page._reuse_scanned_sessions_once = True

        with patch.object(
            organizer_page,
            "scan_unity_sessions",
            side_effect=AssertionError("redundant Win32 scan"),
        ):
            assert page.refresh_sessions_and_export(render=False) is True

        assert page._reuse_scanned_sessions_once is False
        page.deleteLater()
        app.processEvents()
    finally:
        for active_patch in reversed(patches):
            active_patch.stop()


def test_scan_requests_are_coalesced_while_worker_is_active() -> None:
    app = QApplication.instance() or QApplication([])
    patches = _isolated_organizer_patches()
    for active_patch in patches:
        active_patch.start()
    try:
        page = _build_page()
        page._scan_in_flight = True

        with patch.object(os, "name", "nt"):
            assert page._request_session_scan("release_retry") is True
            assert page._pending_scan_mode == "release_retry"
            assert page._request_session_scan("window_event") is True
            assert page._pending_scan_mode == "window_event"
            assert page._request_session_scan("manual") is True
            assert page._pending_scan_mode == "manual"
            # Lower-priority noise must not downgrade the pending manual scan.
            assert page._request_session_scan("release_retry") is True
            assert page._pending_scan_mode == "manual"

        page.deleteLater()
        app.processEvents()
    finally:
        for active_patch in reversed(patches):
            active_patch.stop()
