from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.network.application_coordinator import NetworkApplicationCoordinator, NetworkApplicationStatus
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
    def __init__(self, character_key: str, child: object, *, visible: bool = True) -> None:
        self.current_character_key = character_key
        self.tabs = _Tabs(child)
        self.visible = visible

    def objectName(self) -> str:
        return "EncyclopediaPage"

    def isVisible(self) -> bool:
        return self.visible


class _OtherWidget:
    def objectName(self) -> str:
        return "OtherPage"


class NetworkApplicationCoordinatorTests(unittest.TestCase):
    def test_stop_during_queue_get_never_executes_pending_capture_command(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())

        def stop_before_return(*, timeout):
            coordinator._stop_event.set()
            return "prepare_capture"

        with (
            patch.object(coordinator._commands, "get", side_effect=stop_before_return),
            patch.object(coordinator, "_handle_command") as handle,
            patch.object(coordinator, "_publish_current"),
            patch.object(coordinator.calibration, "stop", return_value=True),
            patch.object(coordinator.runtime, "stop", return_value=True),
            patch.object(coordinator, "_close_capture_source", return_value=True),
        ):
            coordinator._run()
            handle.assert_not_called()

    def test_restarted_worker_discards_old_privileged_commands(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._commands.put("prepare_capture")
        coordinator._commands.put("start_runtime")
        coordinator._results.put(object())
        coordinator._statuses.put(coordinator.latest_status())
        self.assertTrue(coordinator.has_pending_ui_events())
        with patch(
            "app.network.application_coordinator.threading.Thread"
        ) as create_thread:
            self.assertTrue(coordinator.start_worker())
            create_thread.return_value.start.assert_called_once_with()
            self.assertTrue(coordinator._commands.empty())
            self.assertEqual(coordinator.drain_results(), [])
            self.assertEqual(coordinator.drain_statuses(), [])
            self.assertFalse(coordinator.has_pending_ui_events())
            self.assertFalse(coordinator._stop_event.is_set())

    def test_running_worker_preserves_undelivered_ui_events(self) -> None:
        from unittest.mock import Mock

        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._thread = Mock()
        coordinator._thread.is_alive.return_value = True
        stale = object()
        status = coordinator.latest_status()
        coordinator._results.put(stale)
        coordinator._statuses.put(status)

        self.assertTrue(coordinator.start_worker())
        self.assertEqual(coordinator.drain_results(), [stale])
        self.assertEqual(coordinator.drain_statuses(), [status])

    def test_shutdown_prevents_all_privileged_start_paths(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._stop_event.set()
        with (
            patch.object(coordinator._capture_source, "start") as capture,
            patch.object(coordinator.calibration, "start") as calibration,
            patch.object(coordinator.runtime, "start_if_ready") as runtime,
        ):
            coordinator._handle_command("prepare_capture")
            coordinator._handle_command("start_calibration")
            coordinator._handle_command("start_runtime")
            # The direct helpers also gate calls that raced after dispatch.
            coordinator._prepare_capture()
            coordinator._start_calibration()
            coordinator._start_runtime()
            capture.assert_not_called()
            calibration.assert_not_called()
            runtime.assert_not_called()

    def test_stop_during_capture_preparation_drops_late_ready_status(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        with (
            patch.object(coordinator._capture_source, "start") as start,
            patch.object(coordinator._capture_source, "stop",
                         side_effect=coordinator._stop_event.set) as stop,
            patch.object(coordinator, "_publish_current") as publish,
        ):
            coordinator._prepare_capture()
            start.assert_called_once_with()
            stop.assert_called_once_with()
            publish.assert_not_called()

    def test_stop_during_calibration_start_cannot_rearm_pending(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = _AutoCalibrationFake()
        coordinator.runtime = _RuntimeFake()

        def stop_as_start_returns():
            coordinator._stop_event.set()
            return coordinator.calibration.poll_status

        with (
            patch.object(coordinator.calibration, "start",
                         side_effect=stop_as_start_returns) as start,
            patch.object(coordinator, "_publish_current") as publish,
            patch.object(coordinator, "_start_runtime") as runtime,
        ):
            coordinator._start_calibration()
            start.assert_called_once_with()
            publish.assert_not_called()
            runtime.assert_not_called()
        self.assertFalse(coordinator._calibration_pending)

    def test_stop_between_calibration_status_read_and_flag_write(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = _AutoCalibrationFake()
        coordinator.runtime = _RuntimeFake()

        class _StopOnReason:
            @property
            def reason(self):
                coordinator._stop_event.set()
                return "awaiting_character_identity"

        with patch.object(coordinator.calibration, "start",
                          return_value=_StopOnReason()) as started:
            coordinator._start_calibration()
            started.assert_called_once_with()

        # The first post-start guard ran before the property above caused
        # shutdown; the second one under the state lock must still win.
        self.assertTrue(coordinator._stop_event.is_set())
        self.assertFalse(coordinator._calibration_pending)
        self.assertEqual(coordinator.drain_statuses(), [])

    def test_stop_during_runtime_start_drops_late_status_and_calibration(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.runtime = _ReasonRuntimeFake("mapping_no_exact_match")
        coordinator.calibration = _AutoCalibrationFake()

        def stop_as_start_returns():
            coordinator._stop_event.set()
            return NetworkControllerStatus(False, "mapping_no_exact_match")

        with (
            patch.object(coordinator.runtime, "start_if_ready",
                         side_effect=stop_as_start_returns) as start,
            patch.object(coordinator, "_publish_current") as publish,
            patch.object(coordinator, "_start_calibration") as calibration,
        ):
            coordinator._start_runtime()
            start.assert_called_once_with()
            publish.assert_not_called()
            calibration.assert_not_called()

    def test_stop_during_journal_evidence_drops_terminal_calibration(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = _CalibrationFake(
            ProtocolCalibrationControllerStatus(
                running=False,
                reason="mapping_installed_not_started",
                build_sha256=BUILD,
            )
        )
        coordinator._calibration_pending = True
        with (
            patch.object(coordinator, "_apply_calibration_journal_evidence",
                         side_effect=coordinator._stop_event.set) as journal,
            patch.object(coordinator, "_publish_current") as publish,
            patch.object(coordinator, "_apply_calibration_evidence") as evidence,
            patch.object(coordinator, "_start_runtime") as runtime,
        ):
            coordinator._poll_calibration()
            journal.assert_called_once_with()
            publish.assert_not_called()
            evidence.assert_not_called()
            runtime.assert_not_called()

    def test_stop_blocks_stale_current_and_explicit_status_publication(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        initial = coordinator.latest_status()
        coordinator._stop_event.set()

        with patch("app.network.application_coordinator.record_validation") as recorded:
            coordinator._publish_current("running")
            coordinator._publish_status(NetworkApplicationStatus(True, False, "running"))
            recorded.assert_not_called()

        self.assertIs(coordinator.latest_status(), initial)
        self.assertEqual(coordinator.drain_statuses(), [])

    def test_stop_while_validation_is_recorded_drops_late_status_event(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        with (
            patch("app.network.application_coordinator.record_validation",
                  side_effect=coordinator._stop_event.set),
            patch.object(coordinator.logger, "info") as logged,
        ):
            coordinator._publish_status(NetworkApplicationStatus(True, False, "running"))
            logged.assert_not_called()
        self.assertEqual(coordinator.drain_statuses(), [])

    def test_stop_closes_other_components_when_calibration_stop_raises(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        with (
            patch.object(coordinator.calibration, "stop",
                         side_effect=OSError("calibration stopped badly")),
            patch.object(coordinator.runtime, "stop", return_value=True) as runtime,
            patch.object(coordinator, "_close_capture_source",
                         return_value=True) as capture,
            patch.object(coordinator.logger, "exception"),
        ):
            self.assertFalse(coordinator.stop(join_timeout=0))
            runtime.assert_called_once_with()
            capture.assert_called_once_with()
        self.assertTrue(coordinator._stop_event.is_set())

    def test_worker_finally_closes_capture_even_after_runtime_stop_error(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._stop_event.set()
        with (
            patch.object(coordinator, "_publish_current"),
            patch.object(coordinator.calibration, "stop",
                         return_value=True) as calibration,
            patch.object(coordinator.runtime, "stop",
                         side_effect=OSError("runtime stop failed")) as runtime,
            patch.object(coordinator, "_close_capture_source",
                         return_value=True) as capture,
            patch.object(coordinator.logger, "exception"),
        ):
            coordinator._run()
            calibration.assert_called_once_with()
            runtime.assert_called_once_with()
            capture.assert_called_once_with()

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

    def test_stop_during_calibration_poll_drops_late_identity_results(self) -> None:
        status = ProtocolCalibrationControllerStatus(
            running=False, reason="mapping_installed_not_started",
            build_sha256=BUILD,
        )
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._calibration_pending = True
        before = coordinator._last_calibration

        def late_poll():
            coordinator._stop_event.set()
            return status

        with (
            patch.object(coordinator.calibration, "poll", side_effect=late_poll),
            patch.object(coordinator.calibration, "drain_identity_results") as drain,
            patch.object(coordinator, "_apply_calibration_journal_evidence") as journal,
            patch.object(coordinator, "_start_runtime") as start_runtime,
        ):
            coordinator._poll_calibration()
            drain.assert_not_called()
            journal.assert_not_called()
            start_runtime.assert_not_called()
        self.assertIs(coordinator._last_calibration, before)
        self.assertEqual(coordinator.drain_results(), [])

    def test_stop_during_runtime_result_drain_drops_late_results(self) -> None:
        from types import SimpleNamespace

        coordinator = NetworkApplicationCoordinator(lambda: ())
        first = SimpleNamespace(
            reason="quest_completed", changed=True,
            accepted=True, character_key="slot:1",
        )
        late = SimpleNamespace(
            reason="quest_completed", changed=True,
            accepted=True, character_key="slot:1",
        )

        def arriving_results(_limit):
            yield first
            coordinator._stop_event.set()
            yield late

        with patch.object(coordinator.runtime, "drain_results",
                          side_effect=arriving_results):
            coordinator._drain_runtime_results()
        self.assertEqual(coordinator.drain_results(), [first])
        self.assertTrue(coordinator._stop_event.is_set())

    def test_shutdown_blocks_calibration_evidence_bridge_creation(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._stop_event.set()
        with patch.object(
            coordinator, "_bridge_for_calibration",
            side_effect=AssertionError("stale evidence must not touch progress"),
        ) as bridge:
            coordinator._apply_calibration_journal_evidence()
            coordinator._apply_one_calibration_journal_evidence(object())
            coordinator._apply_calibration_evidence()
            bridge.assert_not_called()
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

    def test_hidden_encyclopedia_defers_refresh_until_visible(self) -> None:
        hidden_child = _VisibleChild()
        shown_child = _VisibleChild()
        hidden = _EncyclopediaFake("character:1", hidden_child, visible=False)
        shown = _EncyclopediaFake("character:1", shown_child, visible=True)

        self.assertEqual(
            refresh_visible_encyclopedia_widgets(
                (hidden, shown), "character:1",
            ),
            1,
        )
        self.assertEqual(hidden_child.refresh_count, 0)
        self.assertEqual(shown_child.refresh_count, 1)
        hidden.visible = True
        self.assertEqual(
            refresh_visible_encyclopedia_widgets((hidden,), "character:1"),
            1,
        )
        self.assertEqual(hidden_child.refresh_count, 1)

    def test_deleted_encyclopedia_during_visibility_check_is_skipped(self) -> None:
        class _DeletedEncyclopedia(_EncyclopediaFake):
            def isVisible(self) -> bool:
                raise RuntimeError("Internal C++ object already deleted")

        child = _VisibleChild()
        self.assertEqual(
            refresh_visible_encyclopedia_widgets(
                (_DeletedEncyclopedia("character:1", child),), "character:1",
            ),
            0,
        )
        self.assertEqual(child.refresh_count, 0)


if __name__ == "__main__":
    unittest.main()
