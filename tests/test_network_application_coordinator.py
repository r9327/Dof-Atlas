from __future__ import annotations

import unittest
from pathlib import Path

from app.network.application_coordinator import NetworkApplicationCoordinator
from app.network.calibration_controller import ProtocolCalibrationControllerStatus
from app.network.controller import NetworkControllerStatus
from app.ui.network_bridge import refresh_visible_encyclopedia_widgets


BUILD = "ab" * 32


class _CalibrationFake:
    def drain_identity_results(self):
        return []

    def __init__(self, poll_status: ProtocolCalibrationControllerStatus) -> None:
        self.is_running = False
        self.poll_status = poll_status
        self.poll_count = 0
        self.stop_count = 0
        self.verified_journal_evidence = None
        self.verified_certificate = None

    def poll(self) -> ProtocolCalibrationControllerStatus:
        self.poll_count += 1
        return self.poll_status

    def status(self) -> ProtocolCalibrationControllerStatus:
        return self.poll_status

    def stop(self) -> bool:
        self.stop_count += 1
        return True


class _RuntimeFake:
    def __init__(self, *, catchup_ready: bool = True) -> None:
        self.is_running = False
        self.last_bootstrap = None
        self.start_count = 0
        self.stop_count = 0
        self.catchup_ready = bool(catchup_ready)

    def start_if_ready(self) -> NetworkControllerStatus:
        self.start_count += 1
        self.is_running = True
        return NetworkControllerStatus(
            True,
            "running",
            build_sha256=BUILD,
            mapping_path=Path("mapping.json"),
            catchup_ready=self.catchup_ready,
        )

    def stop(self) -> bool:
        self.stop_count += 1
        self.is_running = False
        return True

    def drain_results(self, _limit: int):
        return []


class _ReasonRuntimeFake(_RuntimeFake):
    def __init__(self, reason: str, *, catchup_ready: bool = False) -> None:
        super().__init__(catchup_ready=catchup_ready)
        self.reason = reason

    def start_if_ready(self) -> NetworkControllerStatus:
        self.start_count += 1
        return NetworkControllerStatus(
            False,
            self.reason,
            build_sha256=BUILD,
            mapping_path=Path("mapping.json"),
            catchup_ready=self.catchup_ready,
        )


class _AutoCalibrationFake(_CalibrationFake):
    def __init__(self, reason: str = "awaiting_character_identity") -> None:
        super().__init__(
            ProtocolCalibrationControllerStatus(
                running=True,
                reason=reason,
                build_sha256=BUILD,
            )
        )
        self.start_count = 0

    def start(self) -> ProtocolCalibrationControllerStatus:
        self.start_count += 1
        self.is_running = True
        return self.poll_status


class _VisibleChild:
    def __init__(self) -> None:
        self.refresh_count = 0

    def refresh_external_progress(self) -> None:
        self.refresh_count += 1


class _Tabs:
    def __init__(self, current: object) -> None:
        self.current = current

    def currentWidget(self):
        return self.current


class _EncyclopediaFake:
    def __init__(self, character_key: str, child: object) -> None:
        self.current_character_key = character_key
        self.tabs = _Tabs(child)

    def objectName(self) -> str:
        return "EncyclopediaPage"


class _OtherWidget:
    def objectName(self) -> str:
        return "OtherPage"


class NetworkApplicationCoordinatorTests(unittest.TestCase):
    def test_calibration_and_runtime_share_one_privileged_capture_helper(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        self.assertIs(
            coordinator.calibration.protocol_source,
            coordinator.runtime.protocol_source,
        )
        self.assertIs(
            coordinator.calibration.protocol_source,
            coordinator._capture_source,
        )

    def test_early_capture_preparation_starts_then_pauses_reusable_helper(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())

        class _Capture:
            start_failure_reason = ""

            def __init__(self) -> None:
                self.calls: list[str] = []

            def start(self) -> None:
                self.calls.append("start")

            def stop(self) -> None:
                self.calls.append("stop")

        capture = _Capture()
        coordinator._capture_source = capture
        coordinator.calibration = _CalibrationFake(
            ProtocolCalibrationControllerStatus(False, "waiting_context")
        )
        coordinator.runtime = _RuntimeFake()

        coordinator._prepare_capture()

        self.assertEqual(capture.calls, ["start", "stop"])
        self.assertEqual(coordinator.latest_status().reason, "capture_ready_waiting_context")

    def test_new_exact_build_starts_safe_live_calibration_automatically(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.runtime = _ReasonRuntimeFake("mapping_no_exact_match")
        coordinator.calibration = _AutoCalibrationFake()

        coordinator._start_runtime()

        self.assertEqual(coordinator.runtime.start_count, 1)
        self.assertEqual(coordinator.calibration.start_count, 1)
        self.assertTrue(coordinator._calibration_pending)
        self.assertEqual(coordinator.latest_status().reason, "awaiting_character_identity")

    def test_stale_legacy_mapping_missing_safe_completion_auto_calibrates(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.runtime = _ReasonRuntimeFake(
            "mapping_missing_required_events",
            catchup_ready=True,
        )
        coordinator.calibration = _AutoCalibrationFake()

        coordinator._start_runtime()

        self.assertEqual(coordinator.runtime.start_count, 1)
        self.assertEqual(coordinator.calibration.start_count, 1)
        self.assertTrue(coordinator._calibration_pending)
        self.assertEqual(coordinator.latest_status().reason, "awaiting_character_identity")

    def test_noncanonical_current_mapping_enters_safe_calibration(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.runtime = _ReasonRuntimeFake("mapping_current_profile_noncanonical")
        coordinator.calibration = _AutoCalibrationFake()

        coordinator._start_runtime()

        self.assertEqual(coordinator.runtime.start_count, 1)
        self.assertEqual(coordinator.calibration.start_count, 1)
        self.assertTrue(coordinator._calibration_pending)

    def test_live_only_mapping_stays_running_without_idr_catchup_calibration(self) -> None:
        runtime = _RuntimeFake(catchup_ready=False)
        calibration = _AutoCalibrationFake(reason="awaiting_quest_journal")
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.runtime = runtime
        coordinator.calibration = calibration

        coordinator._start_runtime()

        self.assertEqual(runtime.start_count, 1)
        self.assertEqual(runtime.stop_count, 0)
        self.assertTrue(runtime.is_running)
        self.assertEqual(calibration.start_count, 0)
        self.assertFalse(coordinator._calibration_pending)
        self.assertEqual(coordinator.latest_status().reason, "running")

    def test_non_certificate_like_journal_evidence_is_ignored(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        calibration = _CalibrationFake(
            ProtocolCalibrationControllerStatus(
                False,
                "calibrating",
                build_sha256=BUILD,
            )
        )
        calibration.verified_journal_evidence = type(
            "Evidence",
            (),
            {"session_id": "s1", "journal_observation_count": 1},
        )()
        coordinator.calibration = calibration
        coordinator._bridge_for_calibration = lambda: self.fail(
            "unverified evidence must never request a business bridge"
        )

        coordinator._apply_calibration_journal_evidence()

        self.assertEqual(coordinator.drain_results(), [])

    def test_terminal_calibration_is_polled_after_reader_already_stopped(self) -> None:
        terminal = ProtocolCalibrationControllerStatus(
            running=False,
            reason="mapping_installed_not_started",
            build_sha256=BUILD,
            distinct_completion_count=2,
            installed=True,
            mapping_path=Path("mapping.json"),
        )
        calibration = _CalibrationFake(terminal)
        runtime = _RuntimeFake(catchup_ready=True)
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = calibration
        coordinator.runtime = runtime
        coordinator._calibration_pending = True

        coordinator._poll_calibration()

        self.assertEqual(calibration.poll_count, 1)
        self.assertFalse(coordinator._calibration_pending)
        self.assertEqual(runtime.start_count, 1)
        self.assertTrue(runtime.is_running)
        self.assertEqual(coordinator.latest_status().reason, "running")

    def test_intermediate_calibration_remains_pending_without_starting_runtime(self) -> None:
        intermediate = ProtocolCalibrationControllerStatus(
            running=True,
            reason="awaiting_quest_journal",
            build_sha256=BUILD,
            distinct_completion_count=1,
            quest_journal_observation_count=0,
        )
        calibration = _CalibrationFake(intermediate)
        calibration.is_running = True
        runtime = _RuntimeFake()
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = calibration
        coordinator.runtime = runtime
        coordinator._calibration_pending = True

        coordinator._poll_calibration()

        self.assertTrue(coordinator._calibration_pending)
        self.assertEqual(runtime.start_count, 0)
        self.assertTrue(coordinator.latest_status().calibrating)
        self.assertEqual(coordinator.latest_status().distinct_completion_count, 1)
        self.assertEqual(coordinator.latest_status().reason, "awaiting_quest_journal")

    def test_visible_encyclopedia_refreshes_only_matching_character(self) -> None:
        selected = _VisibleChild()
        other_character = _VisibleChild()
        widgets = [
            _OtherWidget(),
            _EncyclopediaFake("slot:1", selected),
            _EncyclopediaFake("slot:2", other_character),
        ]

        refreshed = refresh_visible_encyclopedia_widgets(widgets, "slot:1")

        self.assertEqual(refreshed, 1)
        self.assertEqual(selected.refresh_count, 1)
        self.assertEqual(other_character.refresh_count, 0)

    def test_visible_encyclopedia_ignores_child_without_refresh_contract(self) -> None:
        refreshed = refresh_visible_encyclopedia_widgets(
            [_EncyclopediaFake("slot:1", object())],
            "slot:1",
        )
        self.assertEqual(refreshed, 0)


if __name__ == "__main__":
    unittest.main()
