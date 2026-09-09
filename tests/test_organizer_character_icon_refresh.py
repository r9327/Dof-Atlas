from __future__ import annotations

import unittest
from unittest.mock import patch

from app.pages import organizer_page
from app.pages.organizer_page import OrganizerPage


class _OrganizerRefreshFake:
    def __init__(self) -> None:
        self.sessions = [{"nom": "Dofus", "hwnd": 100, "pid": 200}]
        self.profiles = {}
        self.render_count = 0
        self.export_count = 0
        self.notify_count = 0
        self.retry_schedule_count = 0

    def session_identity_signature(self):
        return tuple(
            (row.get("nom", ""), int(row.get("hwnd", 0)), int(row.get("pid", 0)))
            for row in self.sessions
        )

    def load_profiles(self):
        return {}

    def build_session_slots(self, sessions):
        return list(sessions)

    def export_client_index(self):
        self.export_count += 1

    def request_sessions_render(self):
        self.render_count += 1

    def notify_sessions_changed(self):
        self.notify_count += 1

    def sync_event_watcher_sessions(self):
        pass

    def begin_release_identity_retries(self):
        pass

    def sessions_have_generic_names(self):
        return bool(self.sessions and self.sessions[0].get("nom") == "Dofus")

    def schedule_next_release_identity_retry(self):
        self.retry_schedule_count += 1

    def isVisible(self):
        return False


class OrganizerCharacterIconRefreshTests(unittest.TestCase):
    def test_window_identity_change_renders_even_while_organizer_is_hidden(self) -> None:
        fake = _OrganizerRefreshFake()
        resolved = [{"nom": "Bob - Pandawa", "hwnd": 100, "pid": 200}]

        with (
            patch.object(organizer_page.os, "name", "nt"),
            patch.object(organizer_page, "scan_unity_sessions", return_value=resolved),
        ):
            OrganizerPage.refresh_sessions_from_window_event(fake)

        self.assertEqual(fake.sessions, resolved)
        self.assertEqual(fake.export_count, 1)
        self.assertEqual(fake.render_count, 1)
        self.assertEqual(fake.notify_count, 1)

    def test_release_identity_retry_renders_resolved_class_while_hidden(self) -> None:
        fake = _OrganizerRefreshFake()
        resolved = [{"nom": "Bob - Pandawa", "hwnd": 100, "pid": 200}]

        with (
            patch.object(organizer_page.os, "name", "nt"),
            patch.object(organizer_page, "scan_unity_sessions", return_value=resolved),
        ):
            OrganizerPage.retry_release_identity(fake)

        self.assertEqual(fake.sessions, resolved)
        self.assertEqual(fake.export_count, 1)
        self.assertEqual(fake.render_count, 1)
        self.assertEqual(fake.notify_count, 1)
        self.assertEqual(fake.retry_schedule_count, 0)


if __name__ == "__main__":
    unittest.main()
