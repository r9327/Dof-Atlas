from __future__ import annotations

import threading
from logging import Logger
from queue import Empty, Queue

from app.core.logger import get_runtime_logger
from app.network.capture_ipc import CaptureIpcDisconnected
from app.network.progress_bridge import EventApplicationResult, NetworkProgressBridge
from app.network.source import NetworkEventSource


class NetworkEventRuntime:
    """Read normalized network events outside the Qt UI thread."""

    def __init__(
        self,
        source: NetworkEventSource,
        bridge: NetworkProgressBridge,
        *,
        logger: Logger | None = None,
        read_timeout: float = 0.25,
    ) -> None:
        self.source = source
        self.bridge = bridge
        self.logger = logger or get_runtime_logger()
        self.read_timeout = max(0.05, float(read_timeout))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._results: Queue[EventApplicationResult] = Queue()
        self.start_failure_reason = ""
        self._lifecycle_lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def start(self) -> bool:
        with self._lifecycle_lock:
            if self.is_running:
                return True
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self.start_failure_reason = ""
            try:
                self.source.start()
            except Exception as exc:
                raw_source = getattr(self.source, "source", None)
                self.start_failure_reason = str(
                    getattr(exc, "reason", "")
                    or getattr(self.source, "start_failure_reason", "")
                    or getattr(raw_source, "start_failure_reason", "")
                    or "runtime_start_failed"
                )
                try:
                    self.source.stop()
                except Exception:
                    self.logger.exception("Network source cleanup after start failure failed.")
                self.logger.exception("Network source start failed.")
                return False
            thread = threading.Thread(
                target=self._run,
                name="DofusAtlas-NetworkEvents",
                daemon=True,
            )
            self._thread = thread
            try:
                thread.start()
            except Exception:
                self._thread = None
                self._stop_event.set()
                try:
                    self.source.stop()
                except Exception:
                    self.logger.exception("Network source cleanup after thread start failure failed.")
                self.bridge.reset_sessions()
                self.start_failure_reason = "runtime_thread_start_failed"
                self.logger.exception("Network event reader thread start failed.")
                return False
            return True

    def stop(self, join_timeout: float = 2.0) -> bool:
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread

        # Do not pause the shared elevated source while the reader may still be
        # inside read_event(). Otherwise the reader and the control handshake
        # can race on the same IPC receive stream and the reader may consume the
        # ``paused`` ACK. read_event is timeout-bounded, so the normal path lets
        # the reader leave first; its finally block then pauses the source from
        # the only thread still receiving from it.
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, float(join_timeout)))

        stopped = thread is None or not thread.is_alive()
        if not stopped:
            # Defensive fallback for a source that violates the bounded read
            # contract: force source shutdown to unblock it, then give the
            # reader one short final opportunity to terminate.
            try:
                self.source.stop()
            except Exception:
                self.logger.exception("Network source forced stop failed.")
            if thread is not threading.current_thread():
                thread.join(max(0.05, min(self.read_timeout * 2.0, 0.5)))
            stopped = not thread.is_alive()
        elif thread is None:
            # There is no reader finally block to own cleanup in this state.
            try:
                self.source.stop()
            except Exception:
                self.logger.exception("Network source stop failed without reader.")

        with self._lifecycle_lock:
            if stopped and self._thread is thread:
                self._thread = None
            if stopped:
                self.bridge.reset_sessions()
        if not stopped:
            self.logger.error("Network event reader did not stop within timeout.")
        return stopped

    def get_result_nowait(self) -> EventApplicationResult | None:
        try:
            return self._results.get_nowait()
        except Empty:
            return None

    def drain_results(self, limit: int = 100) -> list[EventApplicationResult]:
        rows: list[EventApplicationResult] = []
        for _ in range(max(0, int(limit))):
            result = self.get_result_nowait()
            if result is None:
                break
            rows.append(result)
        return rows

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    event = self.source.read_event(self.read_timeout)
                except CaptureIpcDisconnected:
                    self.start_failure_reason = "capture_helper_disconnected"
                    self.logger.exception("Network capture helper disconnected; reader stopped.")
                    self._stop_event.set()
                    break
                except Exception:
                    if self._stop_event.is_set():
                        break
                    self.logger.exception("Network source read/decode failed; reader remains active.")
                    self._stop_event.wait(min(self.read_timeout, 0.25))
                    continue
                if event is None:
                    if self._stop_event.is_set():
                        break
                    continue
                # Once stop is requested, an event returned by an in-flight
                # read belongs to the outgoing runtime boundary. Do not allow it
                # to mutate progression after the runtime has been stopped.
                if self._stop_event.is_set():
                    break
                try:
                    result = self.bridge.handle(event)
                except Exception:
                    if self._stop_event.is_set():
                        break
                    self.logger.exception("Network event application failed; reader remains active.")
                    continue
                if result.changed or (
                    result.accepted and result.character_key
                    and result.reason.startswith("character_")
                ):
                    self._results.put(result)
        finally:
            try:
                self.source.stop()
            except Exception:
                self.logger.exception("Network source final stop failed.")
            self.bridge.reset_sessions()


__all__ = ["NetworkEventRuntime"]
