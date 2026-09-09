from __future__ import annotations

import threading
import unittest

from app.network.progress_bridge import EventApplicationResult
from app.network.runtime import NetworkEventRuntime


class _BlockingEventSource:
    def __init__(self, event: object | None = None) -> None:
        self.event = event
        self.read_started = threading.Event()
        self.release_read = threading.Event()
        self._lock = threading.Lock()
        self._read_active = False
        self.started = False
        self.stop_calls = 0
        self.stop_called_while_reading = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        with self._lock:
            if self._read_active:
                self.stop_called_while_reading = True
            self.stop_calls += 1
        self.started = False

    def read_event(self, timeout: float) -> object | None:
        with self._lock:
            self._read_active = True
        self.read_started.set()
        self.release_read.wait(max(0.0, float(timeout)))
        with self._lock:
            self._read_active = False
        return self.event


class _RecordingBridge:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.reset_calls = 0

    def handle(self, event: object) -> EventApplicationResult:
        self.events.append(event)
        return EventApplicationResult(
            accepted=True,
            changed=True,
            reason="test_changed",
            character_key="slot-1",
        )

    def reset_sessions(self) -> None:
        self.reset_calls += 1


class NetworkRuntimeStopLifecycleTests(unittest.TestCase):
    def test_stop_does_not_pause_source_while_reader_is_receiving(self) -> None:
        source = _BlockingEventSource()
        bridge = _RecordingBridge()
        runtime = NetworkEventRuntime(
            source,  # type: ignore[arg-type]
            bridge,  # type: ignore[arg-type]
            read_timeout=0.05,
        )

        self.assertTrue(runtime.start())
        self.assertTrue(source.read_started.wait(1.0))
        self.assertTrue(runtime.stop(join_timeout=1.0))

        self.assertFalse(source.stop_called_while_reading)
        self.assertGreaterEqual(source.stop_calls, 1)
        self.assertFalse(runtime.is_running)

    def test_event_already_in_flight_is_dropped_after_stop_request(self) -> None:
        final_event = object()
        source = _BlockingEventSource(final_event)
        bridge = _RecordingBridge()
        runtime = NetworkEventRuntime(
            source,  # type: ignore[arg-type]
            bridge,  # type: ignore[arg-type]
            read_timeout=0.25,
        )

        self.assertTrue(runtime.start())
        self.assertTrue(source.read_started.wait(1.0))

        stop_result: list[bool] = []
        stopper = threading.Thread(
            target=lambda: stop_result.append(runtime.stop(join_timeout=1.0)),
            daemon=True,
        )
        stopper.start()
        self.assertTrue(runtime._stop_event.wait(1.0))
        source.release_read.set()
        stopper.join(1.0)

        self.assertEqual(stop_result, [True])
        self.assertEqual(bridge.events, [])
        self.assertIsNone(runtime.get_result_nowait())
        self.assertFalse(source.stop_called_while_reading)
        self.assertFalse(runtime.is_running)


if __name__ == "__main__":
    unittest.main()
