from __future__ import annotations

import logging
import threading
import unittest
from unittest.mock import patch

from app.network.runtime import NetworkEventRuntime


class FakeSource:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0

    def start(self) -> None:
        self.start_count += 1

    def stop(self) -> None:
        self.stop_count += 1

    def read_event(self, timeout: float):
        del timeout
        return None


class ReasonedFailingSource(FakeSource):
    start_failure_reason = "capture_elevation_cancelled"

    def start(self) -> None:
        self.start_count += 1
        error = RuntimeError("synthetic capture denial")
        error.reason = self.start_failure_reason
        raise error


class FakeBridge:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset_sessions(self) -> None:
        self.reset_count += 1

    def handle(self, event):
        raise AssertionError(f"unexpected event: {event!r}")


class LateEventSource(FakeSource):
    def __init__(self) -> None:
        super().__init__()
        self.read_started = threading.Event()
        self.release = threading.Event()

    def stop(self) -> None:
        super().stop()
        self.release.set()

    def read_event(self, timeout: float):
        del timeout
        self.read_started.set()
        self.release.wait(1.0)
        return object()


class RecordingBridge(FakeBridge):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def handle(self, event):
        self.events.append(event)


class FailingThread:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def is_alive(self) -> bool:
        return False

    def start(self) -> None:
        raise RuntimeError("synthetic thread start failure")


class NetworkRuntimeLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger(f"network-runtime-lifecycle-{id(self)}")
        self.logger.addHandler(logging.NullHandler())

    def test_thread_start_failure_closes_source_and_resets_sessions(self) -> None:
        source = FakeSource()
        bridge = FakeBridge()
        runtime = NetworkEventRuntime(source, bridge, logger=self.logger)

        with patch("app.network.runtime.threading.Thread", FailingThread):
            self.assertFalse(runtime.start())

        self.assertEqual(source.start_count, 1)
        self.assertEqual(source.stop_count, 1)
        self.assertEqual(bridge.reset_count, 1)
        self.assertFalse(runtime.is_running)

    def test_capture_start_reason_remains_actionable(self) -> None:
        runtime = NetworkEventRuntime(
            ReasonedFailingSource(),
            FakeBridge(),
            logger=self.logger,
        )
        self.assertFalse(runtime.start())
        self.assertEqual(runtime.start_failure_reason, "capture_elevation_cancelled")

    def test_terminal_cleanup_always_stops_source_and_resets_sessions(self) -> None:
        source = FakeSource()
        bridge = FakeBridge()
        runtime = NetworkEventRuntime(source, bridge, logger=self.logger)
        runtime._stop_event.set()

        runtime._run()

        self.assertEqual(source.stop_count, 1)
        self.assertEqual(bridge.reset_count, 1)

    def test_event_returned_during_stop_is_not_applied(self) -> None:
        source = LateEventSource()
        bridge = RecordingBridge()
        runtime = NetworkEventRuntime(source, bridge, logger=self.logger)

        self.assertTrue(runtime.start())
        self.assertTrue(source.read_started.wait(1.0))
        self.assertTrue(runtime.stop())

        self.assertEqual(bridge.events, [])


if __name__ == "__main__":
    unittest.main()
