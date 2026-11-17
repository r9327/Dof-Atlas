from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.network.application_coordinator import NetworkApplicationStatus
from app.pages.home_page import HomePage


class NetworkHomeStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _status(**changes) -> NetworkApplicationStatus:
        values = {
            "running": False,
            "calibrating": False,
            "reason": "context_ready",
            "distinct_completion_count": 0,
            "quest_journal_observation_count": 0,
            "quest_journal_verified_count": 0,
            "snapshot_candidate_count": 0,
            "snapshot_candidate_type_url": "",
            "catchup_ready": False,
        }
        values.update(changes)
        return NetworkApplicationStatus(**values)

    def test_running_state_is_reduced_to_one_clean_active_label(self) -> None:
        live_only = HomePage._network_summary(
            self._status(running=True, reason="running", catchup_ready=False)
        )
        full = HomePage._network_summary(
            self._status(running=True, reason="running", catchup_ready=True)
        )

        self.assertEqual(live_only, ("Actif", "active"))
        self.assertEqual(full, ("Actif", "active"))

    def test_running_worker_with_explicit_failure_never_looks_active(self) -> None:
        for reason in (
            "runtime_stop_failed_before_calibration",
            "coordinator_error",
            "capture_helper_start_failed",
            "build_changed",
            "capture_elevation_cancelled",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    HomePage._network_summary(
                        self._status(running=True, reason=reason)
                    ),
                    ("Attention requise", "error"),
                )
        self.assertEqual(
            HomePage._network_summary(self._status(running=True, reason="running")),
            ("Actif", "active"),
        )

    def test_calibration_details_are_reduced_to_connection_state(self) -> None:
        for reason in (
            "awaiting_character_identity",
            "awaiting_quest_journal",
            "awaiting_distinct_quest_completions",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    HomePage._network_summary(
                        self._status(calibrating=True, reason=reason)
                    ),
                    ("Connexion…", "pending"),
                )

    def test_waiting_and_error_states_remain_short_but_distinct(self) -> None:
        for reason in ("waiting_context", "stopped"):
            with self.subTest(reason=reason):
                self.assertEqual(
                    HomePage._network_summary(self._status(reason=reason)),
                    ("Hors ligne", "idle"),
                )
        for reason in ("no_window_handles", "build_fingerprint_unavailable"):
            with self.subTest(reason=reason):
                self.assertEqual(
                    HomePage._network_summary(self._status(reason=reason)),
                    ("En attente de Dofus", "idle"),
                )
        self.assertEqual(
            HomePage._network_summary(
                self._status(reason="capture_elevation_cancelled")
            ),
            ("Attention requise", "error"),
        )
        self.assertEqual(
            HomePage._network_summary(self._status(reason="stop_failed")),
            ("Attention requise", "error"),
        )

    def test_home_keeps_only_mini_status_above_almanax(self) -> None:
        page = HomePage()
        right_layout = page.right_column.layout()

        self.assertIs(right_layout.itemAt(0).widget(), page.network_card)
        self.assertIs(right_layout.itemAt(1).widget(), page.almanax_card)
        self.assertFalse(hasattr(page, "network_calibration_hint"))
        self.assertFalse(hasattr(page, "network_calibrate_button"))
        self.assertEqual(page.network_status.text(), "Hors ligne")
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX
        geometry = UNITY_MODULE_GEOMETRY_PX["home"]
        self.assertEqual(page.left_column.layout().spacing(), geometry["left_column_spacing"])
        self.assertEqual(right_layout.spacing(), geometry["right_column_spacing"])
        for tracking in page.tracking_rows.values():
            self.assertEqual(tracking.layout().spacing(), geometry["tracking_spacing"])
            self.assertEqual(tracking.bar.minimumWidth(), geometry["tracking_bar_min_width"])
            self.assertEqual(tracking.value.minimumWidth(), geometry["tracking_value_min_width"])
        self.assertEqual(page.character_card.layout().spacing(), geometry["card_gutter"])
        self.assertEqual(page.network_card.layout().spacing(), geometry["network_card_spacing"])
        margins = page.network_card.layout().contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            geometry["network_card_margins"],
        )

        page.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
