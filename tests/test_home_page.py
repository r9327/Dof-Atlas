from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.network.application_coordinator import NetworkApplicationStatus
from app.pages.home_page import HomePage, HomeTrackingRow


class HomeNetworkIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_home_tracking_key_preserves_accent_and_hyphen_matching(self) -> None:
        self.assertEqual(HomePage._plain_key("  ÉPÉE – Cawotte  "), "epee – cawotte")
        self.assertEqual(HomePage._plain_key(" Cité d’Astrub - Nord "), "cite d'astrub nord")
        self.assertEqual(HomePage._plain_key(None), "")
        self.assertEqual(HomePage._plain_key("a--b"), "a  b".replace("  ", " "))

    def test_tracking_row_shares_clamped_percent_and_grouped_counts(self) -> None:
        row = HomeTrackingRow("•", "Test")
        try:
            row.set_progress(2, 3)
            self.assertEqual(row.bar.value(), 67)
            self.assertEqual(row.value.text(), "67 %")
            row.set_progress(1234, 2000, show_count=True)
            self.assertEqual(row.bar.value(), 62)
            self.assertEqual(row.value.text(), "1 234 / 2 000")
            row.set_progress(2, 0)
            self.assertEqual(row.bar.value(), 0)
            self.assertEqual(row.value.text(), "0 %")
        finally:
            row.deleteLater()

    def test_waiting_client_then_live_network_updates_same_indicator(self) -> None:
        page = HomePage()
        self.addCleanup(page.deleteLater)
        self.addCleanup(self.app.processEvents)

        page._on_network_status(
            NetworkApplicationStatus(
                running=False, calibrating=False,
                reason="build_fingerprint_unavailable",
            )
        )
        self.assertEqual(page.network_status.text(), "En attente de Dofus")
        self.assertEqual(page.network_indicator.property("state"), "idle")

        page._on_network_status(
            NetworkApplicationStatus(
                running=True, calibrating=False, reason="running",
            )
        )
        self.assertEqual(page.network_status.text(), "Actif")
        self.assertEqual(page.network_indicator.property("state"), "active")


if __name__ == "__main__":
    unittest.main()
