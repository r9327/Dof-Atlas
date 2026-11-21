from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.network.application_coordinator import NetworkApplicationStatus
from app.pages.home_page import HomePage


class HomeNetworkIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
