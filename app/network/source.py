from __future__ import annotations

import threading
from typing import Callable, Protocol, runtime_checkable

from app.network.events import BusinessNetworkEvent


@runtime_checkable
class NetworkEventSource(Protocol):
    """Local source contract for a version-matched DOFUS decoder/capture.

    Implementations must remain local, make ``stop()`` idempotent and unblock a
    pending ``read_event`` promptly. The source is responsible for only marking
    events reliable after protocol-level validation.

    ``session_id`` values emitted by a source must identify one connection
    lifetime, not merely an account or process name. Reusing a session id after
    reconnect would make event-id deduplication ambiguous. A verified disconnect
    should emit ``SessionClosedEvent`` before that connection identity is retired.
    """

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def read_event(self, timeout: float) -> BusinessNetworkEvent | None:
        ...


def cleanup_capture_reader(source, reset: Callable[[], None], logger, *, label: str) -> bool:
    """Attempt both shutdown operations; never certify cleanup on an exception."""
    stopped = True
    try:
        if source.stop() is False:
            logger.error("%s source refused shutdown.", label)
            stopped = False
    except Exception:
        logger.exception("%s source shutdown failed.", label)
        stopped = False
    try:
        reset()
    except Exception:
        logger.exception("%s volatile state reset failed.", label)
        stopped = False
    return stopped


class CaptureReaderLifecycle:
    """Shared thread shutdown for the event and calibration readers."""

    def __init__(self, source, logger, read_timeout: float, shutdown_failure_reason: str) -> None:
        self.source = source
        self.logger = logger
        self.read_timeout = max(0.05, float(read_timeout))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.start_failure_reason = ""
        self._lifecycle_lock = threading.RLock()
        self._stopping = False
        self._cleanup_ok = True
        self._shutdown_failure_reason = shutdown_failure_reason

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def _cleanup_reader(self) -> bool:
        raise NotImplementedError

    def stop(self, join_timeout: float = 2.0) -> bool:
        with self._lifecycle_lock:
            if self._stopping:
                return False
            self._stopping = True
            self._stop_event.set()
            thread = self._thread

        try:
            # The normal reader finally owns the source pause. Sending a pause
            # while it receives would race on the elevated IPC control channel.
            if thread is not None and thread is not threading.current_thread():
                thread.join(max(0.0, float(join_timeout)))

            stopped = thread is None or not thread.is_alive()
            if not stopped:
                # Force a misbehaving source to unblock, then wait briefly for
                # the reader's own final cleanup to attest the actual outcome.
                try:
                    self.source.stop()
                except Exception:
                    self.logger.exception("Capture source forced stop failed.")
                if thread is not threading.current_thread():
                    thread.join(max(0.05, min(self.read_timeout * 2.0, 0.5)))
                stopped = not thread.is_alive()
            elif thread is None:
                self._cleanup_reader()

            with self._lifecycle_lock:
                if stopped and self._thread is thread:
                    self._thread = None
                cleanup_ok = self._cleanup_ok
            if not stopped:
                self.logger.error("Capture reader did not stop within timeout.")
            if not stopped or not cleanup_ok:
                self.start_failure_reason = self._shutdown_failure_reason
                return False
            return True
        finally:
            with self._lifecycle_lock:
                self._stopping = False


__all__ = ["CaptureReaderLifecycle", "NetworkEventSource", "cleanup_capture_reader"]
