from __future__ import annotations

import time
from dataclasses import dataclass
from logging import Logger
from typing import Protocol, TypeAlias, runtime_checkable

from app.core.logger import get_runtime_logger
from app.network.events import BusinessNetworkEvent, SessionClosedEvent
from app.network.normalizer import DecodedClientMessage, ProtocolEventNormalizer


@dataclass(frozen=True, slots=True)
class CapturedProtocolMessage:
    session_id: str
    type_url: str
    payload: bytes
    direction: str = "server_to_client"


@dataclass(frozen=True, slots=True)
class TransportSessionClosed:
    session_id: str


ProtocolTransportItem: TypeAlias = CapturedProtocolMessage | TransportSessionClosed


@runtime_checkable
class ProtocolMessageSource(Protocol):
    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def read_item(self, timeout: float) -> ProtocolTransportItem | None:
        ...


@runtime_checkable
class ProtocolMessageDecoder(Protocol):
    """Version-specific semantic decoder.

    Returning ``verified=True`` is a strong contract: the decoder must know the
    exact protocol mapping it is using and must have validated the message type
    and required fields. Shape-based guesses are not acceptable.
    """

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        ...


class DecodedNetworkEventSource:
    """Adapt raw protocol transport to the normalized NetworkEventSource API."""

    def __init__(
        self,
        source: ProtocolMessageSource,
        decoder: ProtocolMessageDecoder,
        *,
        normalizer: ProtocolEventNormalizer | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.source = source
        self.decoder = decoder
        self.normalizer = normalizer or ProtocolEventNormalizer()
        self.logger = logger or get_runtime_logger()

    def start(self) -> None:
        self._reset_decoder()
        self.source.start()

    def stop(self) -> None:
        try:
            self.source.stop()
        finally:
            self._reset_decoder()

    def read_event(self, timeout: float) -> BusinessNetworkEvent | None:
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0.0:
                return None
            item = self.source.read_item(remaining)
            if item is None:
                return None
            if isinstance(item, TransportSessionClosed):
                self._notify_session_closed(item.session_id)
                return SessionClosedEvent(
                    session_id=item.session_id,
                    event_id="transport:session_closed",
                    reliable=True,
                )
            try:
                decoded = self.decoder.decode(item)
            except Exception:
                self.logger.exception(
                    "Network protocol decoder failed: session=%s type=%s",
                    item.session_id,
                    item.type_url,
                )
                continue
            if decoded is None:
                continue
            # Client -> server capture exists only for bounded diagnostics and
            # request/response correlation.  Even if a future decoder forgets
            # its own direction check, an outbound packet must never enter the
            # normalizer (and therefore can never reach progression bridges).
            if item.direction != "server_to_client":
                continue
            event = self.normalizer.normalize(decoded)
            if event is not None:
                return event

    def _notify_session_closed(self, session_id: str) -> None:
        hook = getattr(self.decoder, "session_closed", None)
        if not callable(hook):
            return
        try:
            hook(session_id)
        except Exception:
            self.logger.exception(
                "Network protocol decoder session cleanup failed: session=%s",
                session_id,
            )

    def _reset_decoder(self) -> None:
        hook = getattr(self.decoder, "reset", None)
        if not callable(hook):
            return
        try:
            hook()
        except Exception:
            self.logger.exception("Network protocol decoder reset failed.")


__all__ = [
    "CapturedProtocolMessage",
    "DecodedNetworkEventSource",
    "ProtocolMessageDecoder",
    "ProtocolMessageSource",
    "ProtocolTransportItem",
    "TransportSessionClosed",
]
