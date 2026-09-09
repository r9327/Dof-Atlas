from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication, QWidget

import app.pages.organizer_page as organizer_module
from app.pages.organizer_page import OrganizerPage


class _RenderHarness:
    def __init__(self, *, visible: bool = False) -> None:
        self.visible = visible
        self._sessions_render_dirty = False
        self.render_calls = 0

    def isVisible(self) -> bool:
        return self.visible

    def render_sessions(self) -> None:
        self.render_calls += 1
        self._sessions_render_dirty = False


class _HiddenIdentityHarness(_RenderHarness):
    def __init__(self) -> None:
        super().__init__(visible=False)
        self.profiles = {"marker": "before"}
        self.sessions = [{"nom": "Dofus", "hwnd": 10, "pid": 100}]
        self.export_calls = 0
        self.notify_calls = 0
        self.watcher_sync_calls = 0
        self.retry_calls = 0

    def request_sessions_render(self) -> None:
        OrganizerPage.request_sessions_render(self)

    def session_identity_signature(self):
        return OrganizerPage.session_identity_signature(self)

    def load_profiles(self):
        return {"marker": "after"}

    def build_session_slots(self, sessions):
        return list(sessions)

    def export_client_index(self) -> None:
        self.export_calls += 1

    def notify_sessions_changed(self) -> None:
        self.notify_calls += 1

    def sync_event_watcher_sessions(self) -> None:
        self.watcher_sync_calls += 1

    def begin_release_identity_retries(self) -> None:
        self.retry_calls += 1


class _LightOrganizerPage(OrganizerPage):
    def __init__(self) -> None:
        QWidget.__init__(self)
        self._sessions_render_dirty = False
        self.render_calls = 0

    def render_sessions(self) -> None:
        self.render_calls += 1
        self._sessions_render_dirty = False


class OrganizerLazySessionsRenderTests(unittest.TestCase):
    def test_hidden_render_request_only_marks_dirty(self) -> None:
        harness = _RenderHarness(visible=False)

        OrganizerPage.request_sessions_render(harness)
        OrganizerPage.request_sessions_render(harness)

        self.assertTrue(harness._sessions_render_dirty)
        self.assertEqual(harness.render_calls, 0)

    def test_visible_render_request_stays_immediate(self) -> None:
        harness = _RenderHarness(visible=True)
        harness._sessions_render_dirty = True

        OrganizerPage.request_sessions_render(harness)

        self.assertFalse(harness._sessions_render_dirty)
        self.assertEqual(harness.render_calls, 1)

    def test_hidden_identity_events_update_state_export_and_notify_then_coalesce_render(self) -> None:
        harness = _HiddenIdentityHarness()
        scans = [
            [{"nom": "Alpha - Huppermage", "hwnd": 10, "pid": 100}],
            [{"nom": "Beta - Huppermage", "hwnd": 10, "pid": 100}],
        ]

        with (
            patch.object(organizer_module, "os", SimpleNamespace(name="nt")),
            patch.object(organizer_module, "scan_unity_sessions", side_effect=scans),
        ):
            OrganizerPage.refresh_sessions_from_window_event(harness)
            OrganizerPage.refresh_sessions_from_window_event(harness)

        self.assertEqual(harness.profiles, {"marker": "after"})
        self.assertEqual(harness.sessions[0]["nom"], "Beta - Huppermage")
        self.assertEqual(harness.export_calls, 2)
        self.assertEqual(harness.notify_calls, 2)
        self.assertEqual(harness.watcher_sync_calls, 2)
        self.assertEqual(harness.retry_calls, 2)
        self.assertEqual(harness.render_calls, 0)
        self.assertTrue(harness._sessions_render_dirty)

        OrganizerPage.flush_sessions_render_if_dirty(harness)
        OrganizerPage.flush_sessions_render_if_dirty(harness)

        self.assertEqual(harness.render_calls, 1)
        self.assertFalse(harness._sessions_render_dirty)

    def test_reload_profiles_hidden_exports_and_marks_visuals_dirty(self) -> None:
        harness = _HiddenIdentityHarness()

        OrganizerPage.reload_profiles_and_export(harness)

        self.assertEqual(harness.profiles, {"marker": "after"})
        self.assertEqual(harness.export_calls, 1)
        self.assertEqual(harness.render_calls, 0)
        self.assertTrue(harness._sessions_render_dirty)

    def test_show_event_flushes_dirty_render_once(self) -> None:
        app = QApplication.instance() or QApplication([])
        page = _LightOrganizerPage()
        try:
            page._sessions_render_dirty = True

            OrganizerPage.showEvent(page, QShowEvent())
            OrganizerPage.showEvent(page, QShowEvent())

            self.assertEqual(page.render_calls, 1)
            self.assertFalse(page._sessions_render_dirty)
        finally:
            page.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
