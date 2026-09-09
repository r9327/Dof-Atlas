from __future__ import annotations

from typing import Protocol, runtime_checkable

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


__all__ = ["NetworkEventSource"]
