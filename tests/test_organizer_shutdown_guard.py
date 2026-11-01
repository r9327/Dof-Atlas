from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.pages.organizer_page import OrganizerPage


class OrganizerShutdownGuardTests(unittest.TestCase):
    def test_startup_scan_callback_is_owned_by_organizer_lifecycle(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/pages/organizer_page.py").read_text(encoding="utf-8")
        self.assertIn("self.startup_scan_timer = QTimer(self)", source)
        self.assertIn("self.startup_scan_timer.timeout.connect(self.auto_scan_sessions_on_startup)", source)
        self.assertNotIn("QTimer.singleShot(0, self.auto_scan_sessions_on_startup)", source)

    def test_destroyed_signal_owns_watcher_shutdown(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/pages/organizer_page.py").read_text(encoding="utf-8")
        self.assertIn("self.destroyed.connect(self.stop_session_event_watcher)", source)

    def test_shutdown_stops_owned_timers_and_native_watcher(self) -> None:
        stopped: list[str] = []
        fake_page = SimpleNamespace(
            window_event_refresh_timer=SimpleNamespace(stop=lambda: stopped.append("window")),
            release_retry_timer=SimpleNamespace(stop=lambda: stopped.append("release")),
            session_event_watcher=SimpleNamespace(stop=lambda: stopped.append("watcher")),
        )

        OrganizerPage.stop_session_event_watcher(fake_page)

        self.assertEqual(stopped, ["window", "release", "watcher"])

    def test_offscreen_page_does_not_schedule_native_startup_scan(self) -> None:
        import json
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        import app.pages.organizer_page as organizer
        import app.pages.organizer.character_sessions as sessions

        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "client_profiles.json"
            index_json = root / "client_index.json"
            index_ini = root / "client_index.ini"
            profile.write_text("{}", encoding="utf-8")
            index_json.write_text(json.dumps({"clients": []}), encoding="utf-8")
            with (
                patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}),
                patch.object(organizer, "PROFILE_FILE", profile),
                patch.object(organizer, "CLIENT_INDEX_JSON", index_json),
                patch.object(organizer, "CLIENT_INDEX_INI", index_ini),
                patch.object(sessions, "PROFILE_FILE", profile),
                patch.object(sessions, "CLIENT_INDEX_JSON", index_json),
                patch.object(sessions, "CLIENT_INDEX_INI", index_ini),
                patch.object(organizer, "scan_unity_sessions",
                             side_effect=AssertionError("native scan ran in Qt test")),
                patch.object(organizer.UnityWindowEventWatcher, "start",
                             side_effect=AssertionError("native watcher started")),
            ):
                page = OrganizerPage(lambda _text: None, lambda: None)
                try:
                    self.assertFalse(page.startup_scan_timer.isActive())
                    QApplication.instance().processEvents()
                finally:
                    page.stop_session_event_watcher()
                    page.deleteLater()
                    QCoreApplication.sendPostedEvents(page, QEvent.DeferredDelete)


    def test_late_runtime_badge_callback_ignores_deleted_qt_owner(self) -> None:
        QApplication.instance() or QApplication([])
        page = OrganizerPage(lambda _text: None, lambda: None)
        page.deleteLater()
        QCoreApplication.sendPostedEvents(page, QEvent.DeferredDelete)

        page.set_runtime_active(True)


if __name__ == "__main__":
    unittest.main()
