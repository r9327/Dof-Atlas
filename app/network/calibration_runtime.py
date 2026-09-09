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
from app.network.transport import ProtocolMessageSource


class ProtocolCalibrationRuntime:
    """Run explicit protocol calibration outside the Qt UI thread."""

    def __init__(
        self,
        source: ProtocolMessageSource,
        calibration: CurrentProtocolCalibration,
        *,
        logger: Logger | None = None,
        read_timeout: float = 0.25,
    ) -> None:
        self.source = source
        self.calibration = calibration
        self.logger = logger or get_runtime_logger()
        self.read_timeout = max(0.05, float(read_timeout))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._statuses: Queue[ProtocolCalibrationStatus] = Queue()
        self._identity_results: Queue = Queue()
        self._latest_status = calibration.status()
        self.start_failure_reason = ""
        self._lifecycle_lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    @property
    def latest_status(self) -> ProtocolCalibrationStatus:
        return self._latest_status

    def start(self) -> bool:
        with self._lifecycle_lock:
            if self.is_running:
                return True
            if self._thread is not None and self._thread.is_alive():
                return False
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
                try:
                    self.source.stop()
                except Exception:
                    self.logger.exception("Protocol calibration source cleanup after start failure failed.")
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
                try:
                    self.source.stop()
                except Exception:
                    self.logger.exception("Protocol calibration source cleanup failed.")
                self.start_failure_reason = "calibration_thread_start_failed"
                self.logger.exception("Protocol calibration thread start failed.")
                return False
            return True

    def stop(self, join_timeout: float = 2.0) -> bool:
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread

        # Keep the shared capture control channel serialized with the reader.
        # Calling source.stop() while read_item() is still receiving can race on
        # the same IPC stream and let the reader consume the ``paused`` ACK as
        # if it were protocol data. The normal path therefore lets the bounded
        # reader leave first; its finally block owns the source pause.
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, float(join_timeout)))

        stopped = thread is None or not thread.is_alive()
        if not stopped:
            # Defensive fallback for a source that violates the bounded-read
            # contract: force source shutdown to unblock it, then give the
            # reader one short final opportunity to terminate.
            try:
                self.source.stop()
            except Exception:
                self.logger.exception("Protocol calibration source forced stop failed.")
            if thread is not threading.current_thread():
                thread.join(max(0.05, min(self.read_timeout * 2.0, 0.5)))
            stopped = not thread.is_alive()
        elif thread is None:
            # There is no reader finally block to own cleanup in this state.
            try:
                self.source.stop()
            except Exception:
                self.logger.exception("Protocol calibration source stop failed without reader.")

        with self._lifecycle_lock:
            if stopped and self._thread is thread:
                self._thread = None
        if not stopped:
            self.logger.error("Protocol calibration reader did not stop within timeout.")
        return stopped

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
            try:
                self.source.stop()
            except Exception:
                self.logger.exception("Protocol calibration source final stop failed.")
            reset = getattr(getattr(self.calibration, "decoder", None), "reset", None)
            if callable(reset):
                reset()

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
