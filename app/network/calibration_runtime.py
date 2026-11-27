from __future__ import annotations

import threading
from dataclasses import replace
from logging import Logger
from queue import Empty, Queue

from app.core.logger import get_runtime_logger
from app.network.capture_ipc import CaptureIpcDisconnected
from app.network.protocol_calibration import (
    CurrentProtocolCalibration,
    ProtocolCalibrationStatus,
)
from app.network.source import CaptureReaderLifecycle, cleanup_capture_reader
from app.network.transport import ProtocolMessageSource


class ProtocolCalibrationRuntime(CaptureReaderLifecycle):
    """Run explicit protocol calibration outside the Qt UI thread."""

    def __init__(
        self,
        source: ProtocolMessageSource,
        calibration: CurrentProtocolCalibration,
        *,
        logger: Logger | None = None,
        read_timeout: float = 0.25,
    ) -> None:
        super().__init__(source, logger or get_runtime_logger(), read_timeout, "calibration_cleanup_failed")
        self.calibration = calibration
        self._statuses: Queue[ProtocolCalibrationStatus] = Queue()
        self._identity_results: Queue = Queue()
        self._latest_status = calibration.status()

    @property
    def latest_status(self) -> ProtocolCalibrationStatus:
        return self._latest_status

    def start(self) -> bool:
        with self._lifecycle_lock:
            if self._stopping or not self._cleanup_ok:
                return False
            if self.is_running:
                return not self._stop_event.is_set()
            self._drain_status_queue()
            self.drain_identity_results()
            self.calibration.reset()
            self._latest_status = self.calibration.status()
            self._statuses.put(self._latest_status)
            self._stop_event.clear()
            self.start_failure_reason = ""
            try:
                self.source.start()
            except Exception as exc:
                self.start_failure_reason = str(
                    getattr(exc, "reason", "")
                    or getattr(self.source, "start_failure_reason", "")
                    or "calibration_start_failed"
                )
                self._stop_event.set()
                self._cleanup_reader()
                self._drain_status_queue()
                self.logger.exception("Protocol calibration source start failed.")
                return False
            thread = threading.Thread(
                target=self._run,
                name="DofusAtlas-NetworkCalibration",
                daemon=True,
            )
            self._thread = thread
            try:
                thread.start()
            except Exception:
                self._thread = None
                self._stop_event.set()
                self._drain_status_queue()
                self._cleanup_reader()
                self.start_failure_reason = "calibration_thread_start_failed"
                self.logger.exception("Protocol calibration thread start failed.")
                return False
            return True

    def _reset_decoder(self) -> None:
        reset = getattr(getattr(self.calibration, "decoder", None), "reset", None)
        if callable(reset):
            reset()

    def _cleanup_reader(self) -> bool:
        self._cleanup_ok = cleanup_capture_reader(
            self.source, self._reset_decoder, self.logger, label="Calibration",
        )
        return self._cleanup_ok

    def get_status_nowait(self) -> ProtocolCalibrationStatus | None:
        try:
            return self._statuses.get_nowait()
        except Empty:
            return None

    def drain_statuses(self, limit: int = 100) -> list[ProtocolCalibrationStatus]:
        rows: list[ProtocolCalibrationStatus] = []
        for _ in range(max(0, int(limit))):
            status = self.get_status_nowait()
            if status is None:
                break
            rows.append(status)
        return rows

    def drain_identity_results(self) -> list:
        results = []
        while True:
            try:
                results.append(self._identity_results.get_nowait())
            except Empty:
                return results

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    item = self.source.read_item(self.read_timeout)
                except CaptureIpcDisconnected:
                    self.logger.exception("Calibration capture helper disconnected; reader stopped.")
                    self._publish(replace(self._latest_status, ready=False, reason="capture_helper_disconnected"))
                    self._stop_event.set()
                    break
                except Exception:
                    if self._stop_event.is_set():
                        break
                    self.logger.exception("Protocol calibration capture read failed; calibration continues.")
                    self._stop_event.wait(min(self.read_timeout, 0.25))
                    continue
                if self._stop_event.is_set():
                    break
                if item is None:
                    continue
                try:
                    status = self.calibration.observe(item)
                except Exception:
                    self.logger.exception("Protocol calibration observation failed; evidence ignored.")
                    continue
                self._publish(status)
                from app.network.progress_bridge import EventApplicationResult

                for event in self.calibration.drain_identity_events():
                    key = f"character:{event.character_id}"
                    self._identity_results.put(EventApplicationResult(
                        True, True, "character_identified", key,
                    ))
                    self.logger.info("Calibration character verified: key=%s", key)
                if status.ready or status.reason == "build_changed":
                    self._stop_event.set()
                    break
        finally:
            if not self._cleanup_reader():
                self.start_failure_reason = self._shutdown_failure_reason

    def _publish(self, status: ProtocolCalibrationStatus) -> None:
        if status == self._latest_status:
            return
        self._latest_status = status
        self._statuses.put(status)

    def _drain_status_queue(self) -> None:
        while True:
            try:
                self._statuses.get_nowait()
            except Empty:
                return


__all__ = ["ProtocolCalibrationRuntime"]
