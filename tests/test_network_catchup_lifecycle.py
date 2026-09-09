from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock, patch

from app.network.application_coordinator import NetworkApplicationCoordinator
from app.network.bootstrap import NetworkBootstrapResult
from app.network.controller import (
    NetworkControllerStatus,
    NetworkRuntimeContext,
    NetworkRuntimeController,
)


class _FakeRuntime:
    def __init__(self) -> None:
        self.is_running = False
        self.start_calls = 0
        self.stop_calls = 0
        self.start_failure_reason = ""

    def start(self) -> bool:
        self.start_calls += 1
        self.is_running = True
        return True

    def stop(self) -> bool:
        self.stop_calls += 1
        self.is_running = False
        return True

    def drain_results(self, _limit: int = 100) -> list[object]:
        return []


class _FakeRuntimeController:
    def __init__(self, status: NetworkControllerStatus) -> None:
        self.status = status
        self.start_calls = 0
        self.is_running = bool(status.running)

    def start_if_ready(self) -> NetworkControllerStatus:
        self.start_calls += 1
        return self.status


class _FakeCalibrationController:
    is_running = False


class NetworkCatchupLifecycleTests(unittest.TestCase):
    def _controller(self) -> NetworkRuntimeController:
        controller = NetworkRuntimeController(lambda: ())
        # start_if_ready only forwards these values into the patched bootstrap;
        # bypass configure_context here so this lifecycle test does not need a
        # real quest catalog fixture.
        controller._context = NetworkRuntimeContext(
            quest_catalog=object(),  # type: ignore[arg-type]
            achievement_provider=object(),
        )
        return controller

    def test_live_only_mapping_starts_verified_runtime_without_idr_catchup(self) -> None:
        controller = self._controller()
        candidate = _FakeRuntime()
        bootstrap = NetworkBootstrapResult(
            runtime=candidate,  # type: ignore[arg-type]
            reason="ready",
            build_sha256="a" * 64,
            catchup_ready=False,
        )

        with patch(
            "app.network.bootstrap.build_windows_network_runtime",
            return_value=bootstrap,
        ):
            status = controller.start_if_ready()

        self.assertTrue(status.running)
        self.assertFalse(status.catchup_ready)
        self.assertEqual(status.reason, "running")
        self.assertEqual(candidate.start_calls, 1)
        self.assertEqual(candidate.stop_calls, 0)
        self.assertTrue(controller.is_running)

    def test_full_mapping_still_starts_verified_runtime(self) -> None:
        controller = self._controller()
        candidate = _FakeRuntime()
        bootstrap = NetworkBootstrapResult(
            runtime=candidate,  # type: ignore[arg-type]
            reason="ready",
            build_sha256="b" * 64,
            catchup_ready=True,
        )

        with patch(
            "app.network.bootstrap.build_windows_network_runtime",
            return_value=bootstrap,
        ):
            status = controller.start_if_ready()

        self.assertTrue(status.running)
        self.assertTrue(status.catchup_ready)
        self.assertEqual(status.reason, "running")
        self.assertEqual(candidate.start_calls, 1)
        self.assertEqual(candidate.stop_calls, 0)

    def test_coordinator_keeps_live_only_runtime_without_reentering_calibration(self) -> None:
        coordinator = NetworkApplicationCoordinator.__new__(NetworkApplicationCoordinator)
        coordinator._operation_lock = threading.RLock()
        coordinator._lock = threading.RLock()
        coordinator._calibration_pending = False
        coordinator._next_runtime_retry_at = 0.0
        coordinator.runtime = _FakeRuntimeController(
            NetworkControllerStatus(
                running=True,
                reason="running",
                build_sha256="c" * 64,
                catchup_ready=False,
            )
        )
        coordinator.calibration = _FakeCalibrationController()
        coordinator._publish_current = Mock()
        coordinator._start_calibration = Mock()

        coordinator._start_runtime()

        self.assertEqual(coordinator.runtime.start_calls, 1)
        coordinator._publish_current.assert_called_once_with("running")
        coordinator._start_calibration.assert_not_called()


if __name__ == "__main__":
    unittest.main()
