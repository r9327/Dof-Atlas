from __future__ import annotations

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


__all__ = ["NetworkEventSource", "cleanup_capture_reader"]
