from __future__ import annotations

import threading
import unittest

from app.network.calibration_runtime import ProtocolCalibrationRuntime
from app.network.protocol_calibration import ProtocolCalibrationStatus


class _BlockingProtocolSource:
    def __init__(self) -> None:
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

    def read_item(self, timeout: float) -> object | None:
        with self._lock:
            self._read_active = True
        self.read_started.set()
        self.release_read.wait(max(0.0, float(timeout)))
        with self._lock:
            self._read_active = False
        return None


class _IdleCalibration:
    def __init__(self) -> None:
        self.reset_calls = 0
        self._status = ProtocolCalibrationStatus(
            ready=False,
            reason="collecting_evidence",
            build_sha256="test-build",
            identified_session_count=0,
            max_distinct_completion_count=0,
        )

    def reset(self) -> None:
        self.reset_calls += 1

    def status(self) -> ProtocolCalibrationStatus:
        return self._status

    def observe(self, item: object) -> ProtocolCalibrationStatus:
        return self._status


class NetworkCalibrationRuntimeStopLifecycleTests(unittest.TestCase):
    def test_stop_does_not_pause_source_while_reader_is_receiving(self) -> None:
        source = _BlockingProtocolSource()
        calibration = _IdleCalibration()
        runtime = ProtocolCalibrationRuntime(
            source,  # type: ignore[arg-type]
            calibration,  # type: ignore[arg-type]
            read_timeout=0.05,
        )

        self.assertTrue(runtime.start())
        self.assertTrue(source.read_started.wait(1.0))
        self.assertTrue(runtime.stop(join_timeout=1.0))

        self.assertFalse(source.stop_called_while_reading)
        self.assertGreaterEqual(source.stop_calls, 1)
        self.assertFalse(runtime.is_running)


if __name__ == "__main__":
    unittest.main()
