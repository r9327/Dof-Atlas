from __future__ import annotations

import unittest
from types import SimpleNamespace
from pathlib import Path

from app.pages.organizer_lazy_page import OrganizerPage


class OrganizerShutdownGuardTests(unittest.TestCase):
    def test_startup_scan_callback_is_owned_by_organizer_lifecycle(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app/pages/organizer_page.py").read_text(encoding="utf-8")
        self.assertIn("self.startup_scan_timer = QTimer(self)", source)
        self.assertIn("self.startup_scan_timer.timeout.connect(self.auto_scan_sessions_on_startup)", source)
        self.assertNotIn("QTimer.singleShot(0, self.auto_scan_sessions_on_startup)", source)

    def test_shutdown_blocks_new_async_scan_request(self) -> None:
        fake_page = SimpleNamespace(_shell_is_shutting_down=lambda: True)

        requested = OrganizerPage._request_session_scan(fake_page, "startup")

        self.assertFalse(requested)

    def test_shutdown_discards_inflight_scan_result_and_pending_restart(self) -> None:
        fake_page = SimpleNamespace(
            _shell_is_shutting_down=lambda: True,
            _scan_in_flight=True,
            _pending_scan_mode="startup",
        )

        OrganizerPage._apply_async_scan_result(
            fake_page,
            {"mode": "startup", "sessions": [{"nom": "ShouldNotApply"}], "error": ""},
        )

        self.assertFalse(fake_page._scan_in_flight)
        self.assertEqual(fake_page._pending_scan_mode, "")


if __name__ == "__main__":
    unittest.main()
