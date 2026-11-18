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

    def _new_network_bridge(self, coordinator):
        from unittest.mock import patch
        from app.ui.network_bridge import NetworkUiBridge

        coordinator.latest_status.return_value = self._status()
        with patch(
            "app.network.application_coordinator.NetworkApplicationCoordinator",
            return_value=coordinator,
        ):
            bridge = NetworkUiBridge()
        bridge._timer.stop()
        return bridge

    def test_network_bridge_stop_from_status_signal_drops_old_results(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock

        coordinator = Mock()
        coordinator.has_pending_ui_events.return_value = True
        coordinator.drain_statuses.return_value = [
            self._status(running=True, reason="running")
        ]
        coordinator.drain_results.return_value = [
            SimpleNamespace(
                accepted=True, changed=True,
                character_key="character:1", reason="character_activated",
            )
        ]
        coordinator.stop.return_value = True
        bridge = self._new_network_bridge(coordinator)
        activations = []
        bridge.characterActivated.connect(activations.append)
        bridge.statusChanged.connect(
            lambda status: bridge.stop() if status.running else None
        )
        try:
            bridge._poll()
            self.assertEqual(bridge.last_status.reason, "stopped")
            coordinator.drain_results.assert_not_called()
            self.assertEqual(activations, [])
            self.assertFalse(bridge._progress_timer.isActive())
        finally:
            bridge.stop()
            bridge.deleteLater()
            self.app.processEvents()

    def test_network_bridge_stop_from_activation_signal_drops_progress(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        coordinator = Mock()
        coordinator.has_pending_ui_events.return_value = True
        coordinator.drain_statuses.return_value = []
        coordinator.drain_results.return_value = [
            SimpleNamespace(
                accepted=True, changed=True,
                character_key="character:1", reason="character_activated",
            )
        ]
        coordinator.stop.return_value = True
        bridge = self._new_network_bridge(coordinator)
        activations = []
        progression = []
        bridge.characterActivated.connect(
            lambda key: (activations.append(key), bridge.stop())
        )
        bridge.progressChanged.connect(progression.append)
        try:
            with patch("app.ui.network_bridge.record_validation"):
                bridge._poll()
            self.assertEqual(activations, ["character:1"])
            self.assertEqual(progression, [])
            self.assertEqual(bridge._pending_progress_characters, set())
            self.assertFalse(bridge._progress_timer.isActive())
        finally:
            bridge.stop()
            bridge.deleteLater()
            self.app.processEvents()

    def test_network_bridge_stop_from_progress_signal_drops_next_character(self) -> None:
        from unittest.mock import Mock

        coordinator = Mock()
        coordinator.stop.return_value = True
        bridge = self._new_network_bridge(coordinator)
        received = []
        bridge._pending_progress_characters.update(
            {"character:1", "character:2"}
        )
        bridge.progressChanged.connect(
            lambda key: (received.append(key), bridge.stop())
        )
        try:
            bridge._emit_pending_progress()
            self.assertEqual(received, ["character:1"])
            self.assertEqual(bridge._pending_progress_characters, set())
        finally:
            bridge.stop()
            bridge.deleteLater()
            self.app.processEvents()

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
