from __future__ import annotations

import logging
import queue
import threading
import time
import unittest
from types import SimpleNamespace

from app.network.calibration_runtime import ProtocolCalibrationRuntime
from app.network.runtime import NetworkEventRuntime


class _QueueSource:
    def __init__(self) -> None:
        self.events: queue.Queue[object] = queue.Queue()
        self.started = False
        self.stopped = threading.Event()
        self.stop_calls = 0

    def start(self) -> None:
        self.started = True
        self.stopped.clear()

    def stop(self) -> None:
        self.stop_calls += 1
        self.stopped.set()

    def read_event(self, timeout: float):
        if self.stopped.is_set():
            return None
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None


class _PartiallyFailingSource(_QueueSource):
    def start(self) -> None:
        super().start()
        raise RuntimeError("synthetic source start failure")


class _FailOnceBridge:
    def __init__(self) -> None:
        self.handle_calls = 0
        self.processed: list[object] = []
        self.reset_calls = 0

    def handle(self, event: object):
        self.handle_calls += 1
        if self.handle_calls == 1:
            raise RuntimeError("synthetic service failure")
        self.processed.append(event)
        return SimpleNamespace(changed=True)

    def reset_sessions(self) -> None:
        self.reset_calls += 1


class _PassiveBridge:
    def __init__(self) -> None:
        self.reset_calls = 0

    def handle(self, event: object):
        return SimpleNamespace(changed=False)

    def reset_sessions(self) -> None:
        self.reset_calls += 1


class _Calibration:
    def __init__(self) -> None:
        self._status = SimpleNamespace(ready=False, reason="awaiting")

    def reset(self) -> None:
        return None

    def status(self):
        return self._status


class NetworkRuntimeRobustnessTests(unittest.TestCase):
    @staticmethod
    def _logger() -> logging.Logger:
        logger = logging.getLogger("network-runtime-robustness")
        logger.addHandler(logging.NullHandler())
        return logger

    @staticmethod
    def _wait_until(predicate, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return bool(predicate())

    def test_event_application_failure_does_not_kill_reader(self) -> None:
        source = _QueueSource()
        bridge = _FailOnceBridge()
        source.events.put("failing-event")
        source.events.put("next-event")
        runtime = NetworkEventRuntime(source, bridge, logger=self._logger(), read_timeout=0.05)

        self.assertTrue(runtime.start())
        self.assertTrue(self._wait_until(lambda: bridge.processed == ["next-event"]))
        self.assertTrue(runtime.is_running)
        self.assertTrue(runtime.stop())

    def test_source_is_cleaned_up_when_start_fails_after_partial_start(self) -> None:
        source = _PartiallyFailingSource()
        bridge = _PassiveBridge()
        runtime = NetworkEventRuntime(source, bridge, logger=self._logger(), read_timeout=0.05)

        self.assertFalse(runtime.start())
        self.assertEqual(runtime.start_failure_reason, "runtime_start_failed")
        self.assertEqual(source.stop_calls, 1)
        self.assertTrue(source.stopped.is_set())
        self.assertFalse(runtime.is_running)

    def test_calibration_source_is_cleaned_up_when_start_fails_after_partial_start(self) -> None:
        source = _PartiallyFailingSource()
        runtime = ProtocolCalibrationRuntime(
            source,
            _Calibration(),
            logger=self._logger(),
            read_timeout=0.05,
        )

        self.assertFalse(runtime.start())
        self.assertEqual(runtime.start_failure_reason, "calibration_start_failed")
        self.assertEqual(source.stop_calls, 1)
        self.assertTrue(source.stopped.is_set())
        self.assertFalse(runtime.is_running)
        self.assertEqual(runtime.drain_statuses(), [])


if __name__ == "__main__":
    unittest.main()
