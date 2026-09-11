from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

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


if __name__ == "__main__":
    unittest.main()
