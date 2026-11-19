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


class NetworkEventReaderBoundaryTests(unittest.TestCase):
    def test_reader_forwards_progress_verified_identity_and_real_disconnection(self) -> None:
        from unittest.mock import Mock
        from app.network.progress_bridge import EventApplicationResult
        from app.network.runtime import NetworkEventRuntime

        source = Mock()
        bridge = Mock()
        runtime = NetworkEventRuntime(source, bridge)
        events = iter(("rejected", "journal", "identity", "closed"))

        def read_event(_timeout):
            try:
                return next(events)
            except StopIteration:
                runtime._stop_event.set()
                return None

        outputs = {
            "rejected": EventApplicationResult(
                False, True, "quest_completed", "character:1",
            ),
            "journal": EventApplicationResult(
                True, True, "quest_journal_reconciled", "character:1",
            ),
            "identity": EventApplicationResult(
                True, False, "character_identified_with_quest_journal",
                "character:1",
            ),
            "closed": EventApplicationResult(
                True, True, "session_closed", "character:1",
            ),
        }
        source.read_event.side_effect = read_event
        bridge.handle.side_effect = outputs.__getitem__

        runtime._run()

        self.assertEqual(
            runtime.drain_results(),
            [outputs["journal"], outputs["identity"], outputs["closed"]],
        )
        source.stop.assert_called_once_with()
        bridge.reset_sessions.assert_called_once_with()

    def test_reader_drops_result_when_stopped_inside_event_application(self) -> None:
        from unittest.mock import Mock
        from app.network.progress_bridge import EventApplicationResult
        from app.network.runtime import NetworkEventRuntime

        source = Mock()
        bridge = Mock()
        runtime = NetworkEventRuntime(source, bridge)
        source.read_event.return_value = object()

        def stop_during_handle(_event):
            runtime._stop_event.set()
            return EventApplicationResult(True, True, "quest_completed", "character:1")

        bridge.handle.side_effect = stop_during_handle
        runtime._run()

        self.assertEqual(runtime.drain_results(), [])
        source.read_event.assert_called_once()
        source.stop.assert_called_once_with()
        bridge.reset_sessions.assert_called_once_with()


class NetworkDeferredJournalIdentityTests(unittest.TestCase):
    def test_deferred_journal_identity_reports_only_real_progress_mutations(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock

        from app.network.events import CharacterIdentifiedEvent, QuestJournalSnapshotEvent
        from app.network.progress_bridge import (
            EventApplicationResult, NetworkProgressBridge,
        )

        for journal_changed in (False, True):
            with self.subTest(journal_changed=journal_changed):
                resolver = Mock()
                resolver.resolve_for_session.return_value = SimpleNamespace(
                    character_key="character:17", label="Witsis",
                )
                bridge = NetworkProgressBridge(
                    quest_catalog=Mock(),
                    quest_progress_service=Mock(),
                    achievement_progress_service=Mock(),
                    achievement_provider=Mock(),
                    character_resolver=resolver,
                )
                pending = QuestJournalSnapshotEvent(
                    session_id="session:17", event_id="idr:1",
                    reliable=True, finished_quest_ids=(),
                )
                bridge._pending_quest_journals["session:17"] = pending
                with patch.object(
                    bridge, "_apply_quest_journal_snapshot",
                    return_value=EventApplicationResult(
                        True, journal_changed, "quest_journal_reconciled",
                        "character:17",
                    ),
                ) as apply:
                    result = bridge.handle(CharacterIdentifiedEvent(
                        session_id="session:17", event_id="kvi-kva:1",
                        reliable=True, character_name="Witsis",
                        character_id=17,
                    ))
                    apply.assert_called_once_with("session:17", pending)

                self.assertTrue(result.accepted)
                self.assertEqual(result.reason, "character_identified_with_quest_journal")
                self.assertEqual(result.character_key, "character:17")
                self.assertEqual(result.changed, journal_changed)

                # The coordinator must still forward the activation for an
                # unchanged journal, but the Qt side will not repaint progress.
                coordinator = NetworkApplicationCoordinator(lambda: ())
                with patch.object(coordinator.runtime, "drain_results", return_value=[result]):
                    coordinator._drain_runtime_results()
                self.assertEqual(coordinator.drain_results(), [result])


class NetworkApplicationCoordinatorTests(unittest.TestCase):
    def test_cold_network_activation_only_queues_worker_command(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        with patch.object(coordinator, "start_worker", return_value=True):
            self.assertTrue(coordinator.request_start_compact_runtime())
        self.assertEqual(coordinator._commands.get_nowait(), "start_compact_runtime")
        self.assertFalse(coordinator._context_ready)

    def test_cold_network_context_is_loaded_only_on_coordinator_worker(self) -> None:
        from unittest.mock import Mock
        from app.quest_catalog import QuestCatalog

        coordinator = NetworkApplicationCoordinator(lambda: ())
        catalog = QuestCatalog([])
        with (
            patch("app.quest_catalog_details.load_network_catalog", return_value=catalog) as loader,
            patch("app.modules.encyclopedia.providers.AchievementProvider", return_value=Mock()) as achievements,
            patch("app.modules.encyclopedia.providers.GuideProvider", return_value=Mock()) as guides,
            patch.object(coordinator, "configure_context") as configure,
        ):
            coordinator._handle_command("start_compact_runtime")
            loader.assert_called_once_with()
            achievements.assert_called_once_with()
            guides.assert_called_once_with()
            configure.assert_called_once()
            self.assertIs(configure.call_args.kwargs["quest_catalog"], catalog)

    def test_compact_bootstrap_honors_shutdown_and_existing_context(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._stop_event.set()
        with patch("app.quest_catalog_details.load_network_catalog") as loader:
            coordinator._handle_command("start_compact_runtime")
            loader.assert_not_called()
        coordinator._stop_event.clear()
        coordinator._context_ready = True
        with (
            patch.object(coordinator, "_start_runtime") as start,
            patch("app.quest_catalog_details.load_network_catalog") as loader,
        ):
            coordinator._handle_command("start_compact_runtime")
            start.assert_called_once_with()
            loader.assert_not_called()

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

    def test_explicit_shutdown_prevents_privileged_restart_and_commands(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._context_ready = True
        with (
            patch.object(coordinator.calibration, "stop", return_value=True),
            patch.object(coordinator.runtime, "stop", return_value=True),
            patch.object(coordinator, "_close_capture_source", return_value=True),
        ):
            self.assertTrue(coordinator.stop(join_timeout=0))

        with (
            patch("app.network.application_coordinator.threading.Thread") as worker,
            patch.object(coordinator._capture_source, "start") as capture,
        ):
            self.assertFalse(coordinator.start_worker())
            self.assertFalse(coordinator.request_prepare_capture())
            self.assertFalse(coordinator.request_start_calibration())
            self.assertFalse(coordinator.request_start_verified_runtime())
            worker.assert_not_called()
            capture.assert_not_called()

        self.assertTrue(coordinator._shutdown_requested)
        self.assertTrue(coordinator._stop_event.is_set())
        self.assertTrue(coordinator._commands.empty())

    def test_shutdown_during_start_worker_does_not_queue_privileged_command(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        with (
            patch.object(coordinator.calibration, "stop", return_value=True),
            patch.object(coordinator.runtime, "stop", return_value=True),
            patch.object(coordinator, "_close_capture_source", return_value=True),
        ):
            def shutdown_during_start() -> bool:
                coordinator.stop(join_timeout=0)
                return True

            with patch.object(
                coordinator, "start_worker", side_effect=shutdown_during_start,
            ):
                self.assertFalse(coordinator.request_prepare_capture())

        self.assertTrue(coordinator._commands.empty())
        self.assertTrue(coordinator._shutdown_requested)

    def test_late_catalog_configuration_cannot_rearm_closed_coordinator(self) -> None:
        from app.quest_catalog import QuestCatalog

        coordinator = NetworkApplicationCoordinator(lambda: ())
        with (
            patch.object(coordinator.calibration, "stop", return_value=True),
            patch.object(coordinator.runtime, "stop", return_value=True),
            patch.object(coordinator, "_close_capture_source", return_value=True),
        ):
            self.assertTrue(coordinator.stop(join_timeout=0))

        with (
            patch.object(coordinator.calibration, "configure_context") as calibration,
            patch.object(coordinator.runtime, "configure_context") as runtime,
            patch.object(coordinator, "start_worker") as worker,
        ):
            coordinator.configure_context(
                quest_catalog=QuestCatalog([]),
                achievement_provider=object(),
            )
            calibration.assert_not_called()
            runtime.assert_not_called()
            worker.assert_not_called()
        self.assertFalse(coordinator._context_ready)
        self.assertTrue(coordinator._shutdown_requested)

    def test_worker_restarts_after_interrupted_worker_without_explicit_stop(self) -> None:
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator._stop_event.set()  # Worker died, not user-requested stop.
        with patch(
            "app.network.application_coordinator.threading.Thread",
        ) as thread:
            self.assertTrue(coordinator.start_worker())
            thread.return_value.start.assert_called_once_with()
        self.assertFalse(coordinator._stop_event.is_set())
        self.assertFalse(coordinator._shutdown_requested)

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

    def test_runtime_routes_progress_without_reactivating_unchanged_character(self) -> None:
        from types import SimpleNamespace

        coordinator = NetworkApplicationCoordinator(lambda: ())
        def event(reason, *, changed=False, accepted=True, key="character:1"):
            return SimpleNamespace(
                reason=reason, changed=changed,
                accepted=accepted, character_key=key,
            )

        # Identity routing reports changed=True in the business bridge,
        # but that does not mean any quest progress was persisted.
        identified = event("character_identified", changed=True)
        applied_journal = event("quest_journal_applied", changed=True)
        updated_objective = event("quest_objective_completed", changed=True)
        reconciled = event("character_identified_with_quest_journal", changed=True)
        close = event("session_closed", changed=True)
        rows = (
            event("character_unchanged"),
            event("quest_journal_no_change"),
            event("session_closed", changed=False),
            event("session_closed", changed=True, accepted=False),
            close,
            identified,
            applied_journal,
            updated_objective,
            reconciled,
            event("character_identified", accepted=False),
            # A rejected decoder/application outcome must never be forwarded
            # as progress even when a buggy adapter sets changed=True.
            event("quest_completed", changed=True, accepted=False),
        )
        with patch.object(coordinator.runtime, "drain_results", return_value=rows):
            coordinator._drain_runtime_results()

        self.assertEqual(
            coordinator.drain_results(),
            [close, identified, applied_journal, updated_objective, reconciled],
        )

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
