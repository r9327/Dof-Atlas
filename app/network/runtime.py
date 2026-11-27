from __future__ import annotations

import threading
from logging import Logger
from queue import Empty, Queue

from app.core.logger import get_runtime_logger
from app.network.capture_ipc import CaptureIpcDisconnected
from app.network.progress_bridge import EventApplicationResult, NetworkProgressBridge
from app.network.source import CaptureReaderLifecycle, NetworkEventSource, cleanup_capture_reader


class NetworkEventRuntime(CaptureReaderLifecycle):
    """Read normalized network events outside the Qt UI thread."""

    def __init__(
        self,
        source: NetworkEventSource,
        bridge: NetworkProgressBridge,
        *,
        logger: Logger | None = None,
        read_timeout: float = 0.25,
    ) -> None:
        super().__init__(source, logger or get_runtime_logger(), read_timeout, "runtime_cleanup_failed")
        self.bridge = bridge
        self._results: Queue[EventApplicationResult] = Queue()

    def start(self) -> bool:
        with self._lifecycle_lock:
            if self._stopping or not self._cleanup_ok:
                return False
            if self.is_running:
                return not self._stop_event.is_set()
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
                self._stop_event.set()
                self._cleanup_reader()
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
                self._cleanup_reader()
                self.start_failure_reason = "runtime_thread_start_failed"
                self.logger.exception("Network event reader thread start failed.")
                return False
            return True

    def _cleanup_reader(self) -> bool:
        self._cleanup_ok = cleanup_capture_reader(
            self.source, self.bridge.reset_sessions, self.logger, label="Network",
        )
        return self._cleanup_ok

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
                # stop() can arrive while the bridge is applying an event.
                # Never leak its result across the outgoing reader boundary.
                if self._stop_event.is_set():
                    break
                reason = str(result.reason or "")
                activates_character = reason in {
                    "character_identified",
                    "character_identified_with_quest_journal",
                }
                # Session closure is not quest progress, but the shell
                # must learn that a connected-client snapshot changed.
                # Retain it as a distinct event all the way to the Qt bridge;
                # never reinterpret it as an activation or progress mutation.
                connection_changed = reason == "session_closed" and bool(result.changed)
                progress_changed = bool(
                    result.changed and reason not in {
                        "character_identified", "session_closed",
                    }
                )
                if (result.accepted and result.character_key
                        and (progress_changed or activates_character or connection_changed)):
                    self._results.put(result)
        finally:
            if not self._cleanup_reader():
                self.start_failure_reason = self._shutdown_failure_reason


__all__ = ["NetworkEventRuntime"]
