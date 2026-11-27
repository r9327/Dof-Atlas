from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import blake2s
from logging import Logger
from secrets import token_bytes, token_hex

from app.core.logger import get_runtime_logger
from app.network.character_runtime_state import character_runtime_state
from app.network.contracts import _is_sha256, active_build_matches
from app.network.diagnostics import (
    DEBUG_GATE,
    log_zaap_observation,
    network_debug_enabled,
    network_debug_log,
    zaap_diagnostics_enabled,
)
from app.network.protobuf_fields import ProtobufDecodeError, ProtobufFields, parse_protobuf_fields
from app.network.transport import (
    CapturedProtocolMessage,
    ProtocolMessageSource,
    ProtocolTransportItem,
    TransportSessionClosed,
)


_ANKAMA_TYPE_PREFIX = "type.ankama.com/"
_MAX_TRACKED_SESSIONS = 16
_MAX_REQUESTS_PER_SESSION = 8
_CORRELATION_WINDOW_SECONDS = 2.0
_MAX_DIAGNOSTIC_PROTOBUF_BYTES = 256 * 1024
_MAX_ZAAP_OBSERVATIONS = 256
_MAX_ZAAP_DESTINATIONS = 128
_ZAAP_REVIEW_DIRECTIONS = {
    "type.ankama.com/hjc": "client_to_server",
    "type.ankama.com/hjj": "server_to_client",
    "type.ankama.com/jru": "server_to_client",
    "type.ankama.com/jss": "server_to_client",
    "type.ankama.com/kld": "server_to_client",
    "type.ankama.com/lva": "server_to_client",
}


def _single_scalar(fields: ProtobufFields, tag: int) -> int | None:
    values = fields.get(tag, ())
    if len(values) == 1 and isinstance(values[0], int) and 0 <= values[0] < 2**63:
        return values[0]
    return None


def _destination_field_sample(fields: ProtobufFields, tag: int) -> dict[str, object]:
    # The archived wire notes and extracted schema disagree between tags 3
    # and 4. Read both layouts independently and preserve the wire types.
    values = fields.get(tag, ())
    entries = tuple(value for value in values if isinstance(value, bytes))
    maps: list[int] = []
    for entry in entries[:_MAX_ZAAP_DESTINATIONS]:
        try:
            candidate = _single_scalar(
                parse_protobuf_fields(entry, max_bytes=4096), 5,
            )
        except ProtobufDecodeError:
            candidate = None
        if candidate:
            maps.append(candidate)
    return {
        "value_count": len(values),
        "varint_count": sum(isinstance(value, int) for value in values),
        "embedded_count": len(entries),
        "sample_truncated": len(entries) > _MAX_ZAAP_DESTINATIONS,
        "map_id_candidates": maps,
    }


def _zaap_wire_summary(message: CapturedProtocolMessage) -> dict[str, object]:
    try:
        fields = parse_protobuf_fields(message.payload, max_bytes=_MAX_DIAGNOSTIC_PROTOBUF_BYTES)
    except ProtobufDecodeError:
        return {"malformed": True}
    if message.type_url == "type.ankama.com/hjj":
        return {
            "open_map_candidate": _single_scalar(fields, 2),
            "destination_tag_3": _destination_field_sample(fields, 3),
            "destination_tag_4": _destination_field_sample(fields, 4),
        }
    if message.type_url == "type.ankama.com/hjc":
        return {
            "selection_kind_candidate": _single_scalar(fields, 2),
            "selection_id_candidate": _single_scalar(fields, 3),
        }
    if message.type_url in {"type.ankama.com/kld", "type.ankama.com/lva"}:
        # These messages also occur outside Zaap travel. Keep only the shape
        # needed to compare them with the adjacent list/request/map samples.
        return {"payload_empty": not fields}
    return {"loaded_map_candidate": _single_scalar(fields, 2)}


@dataclass(frozen=True, slots=True)
class ClientRequestMetadata:
    session_id: str
    type_url: str
    opcode: str
    payload_size: int
    payload_fields: tuple[int, ...]
    payload_empty: bool
    malformed: bool
    classification: str
    quest_request_verified: bool = False


@dataclass(frozen=True, slots=True)
class _RecentRequest:
    observed_at: float
    metadata: ClientRequestMetadata


def client_request_metadata(message: CapturedProtocolMessage) -> ClientRequestMetadata:
    """Describe one outbound Any without assigning a business meaning.

    In particular, an empty protobuf payload is only an *unclassified empty
    request*. Dofus has multiple empty request messages, so this function never
    labels one as QuestsRequest from shape alone.
    """

    payload = bytes(message.payload)
    fields: tuple[int, ...] = ()
    malformed = False
    try:
        decoded = parse_protobuf_fields(
            payload,
            max_bytes=_MAX_DIAGNOSTIC_PROTOBUF_BYTES,
        )
        fields = tuple(sorted(int(field_number) for field_number in decoded))
    except ProtobufDecodeError:
        malformed = True

    empty = len(payload) == 0
    return ClientRequestMetadata(
        session_id=str(message.session_id or ""),
        type_url=str(message.type_url or ""),
        opcode=str(message.type_url or "").rsplit("/", 1)[-1],
        payload_size=len(payload),
        payload_fields=fields,
        payload_empty=empty,
        malformed=malformed,
        classification=(
            "unclassified_empty_request"
            if empty
            else "unclassified_client_message"
        ),
        quest_request_verified=False,
    )


class PassiveRequestResponseDiagnostics:
    """Bounded, metadata-only diagnostics for passive C2S -> S2C correlation.

    Normal debug logs outbound Any metadata with throttling. Deep debug keeps at
    most a few seconds of metadata (never packet bytes) so the nearest following
    server Any can be correlated in time. Correlation is diagnostic only and can
    never authorize a decoder or progression mutation.
    """

    def __init__(
        self, *, logger: Logger | None = None, phase: str = "runtime",
        build_sha256: str = "", active_build_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.logger = logger or get_runtime_logger()
        self.phase = str(phase or "runtime")
        self._recent: OrderedDict[str, deque[_RecentRequest]] = OrderedDict()
        self._build_sha256 = build_sha256.casefold() if _is_sha256(build_sha256) else ""
        self._active_build_provider = active_build_provider
        self._zaap_sessions: dict[str, str] = {}
        self._zaap_identity_salt = b""
        self._zaap_observation_count = 0

    def observe(self, message: CapturedProtocolMessage) -> None:
        self._observe_zaap(message)
        if not network_debug_enabled():
            return
        type_url = str(message.type_url or "")
        if not type_url.startswith(_ANKAMA_TYPE_PREFIX):
            return
        direction = str(message.direction or "").strip().casefold()
        if direction == "client_to_server":
            self._observe_client(message)
        elif direction == "server_to_client" and network_debug_enabled(deep=True):
            self._observe_server(message)

    def session_closed(self, session_id: str) -> None:
        session = str(session_id or "")
        self._recent.pop(session, None)
        alias = self._zaap_sessions.pop(session, None)
        if alias is not None and self._zaap_observation_count < _MAX_ZAAP_OBSERVATIONS:
            self._zaap_observation_count += 1
            log_zaap_observation(
                self.logger,
                phase=self.phase, build_sha256=self._build_sha256,
                sequence=self._zaap_observation_count, session_alias=alias,
                classification="transport_session_closed",
            )

    def clear(self) -> None:
        self._recent.clear()
        self._zaap_sessions.clear()
        self._zaap_identity_salt = b""
        self._zaap_observation_count = 0

    def _observe_zaap(self, message: CapturedProtocolMessage) -> None:
        if (
            not zaap_diagnostics_enabled()
            or not message.session_id
            or _ZAAP_REVIEW_DIRECTIONS.get(message.type_url) != message.direction
            or self._zaap_observation_count >= _MAX_ZAAP_OBSERVATIONS
            or not self._build_sha256
            or self._active_build_provider is None
            or not active_build_matches(self._active_build_provider, self._build_sha256)
        ):
            return
        alias = self._zaap_sessions.get(message.session_id)
        if alias is None:
            alias = self._zaap_sessions[message.session_id] = token_hex(8)
        if not self._zaap_identity_salt:
            self._zaap_identity_salt = token_bytes(16)
        profile = character_runtime_state().snapshot_for_session(message.session_id)
        character_alias = None if profile is None else blake2s(
            profile.character_key.encode("utf-8"), key=self._zaap_identity_salt, digest_size=8,
        ).hexdigest()
        self._zaap_observation_count += 1
        log_zaap_observation(
            self.logger,
            phase=self.phase, build_sha256=self._build_sha256,
            sequence=self._zaap_observation_count, session_alias=alias,
            last_verified_character_alias=character_alias, classification="wire_sample_unverified",
            message_type=message.type_url, direction=message.direction,
            **_zaap_wire_summary(message),
        )

    def _observe_client(self, message: CapturedProtocolMessage) -> None:
        metadata = client_request_metadata(message)
        key = f"client-request:{metadata.type_url}"
        if DEBUG_GATE.should_log(key, first=3, every=200):
            network_debug_log(
                self.logger,
                "[NETWORK][CLIENT_REQUEST]",
                phase=self.phase,
                session=metadata.session_id,
                message_type=metadata.type_url,
                opcode=metadata.opcode,
                direction="client_to_server",
                payload_size=metadata.payload_size,
                payload_fields=metadata.payload_fields,
                payload_empty=metadata.payload_empty,
                malformed=metadata.malformed,
                classification=metadata.classification,
                quest_request_verified=False,
                occurrence=DEBUG_GATE.count(key),
                diagnostic_hint=(
                    "Empty payload is not enough to identify QuestsRequest; "
                    "use controlled temporal correlation with the following server response."
                    if metadata.payload_empty
                    else "Outbound message is diagnostics-only and has no business semantics."
                ),
            )

        if not network_debug_enabled(deep=True):
            return
        session = metadata.session_id
        if not session:
            return
        self._trim_sessions(session)
        queue = self._recent.setdefault(
            session,
            deque(maxlen=_MAX_REQUESTS_PER_SESSION),
        )
        self._recent.move_to_end(session)
        now = time.monotonic()
        self._expire(queue, now)
        queue.append(_RecentRequest(now, metadata))

    def _observe_server(self, message: CapturedProtocolMessage) -> None:
        session = str(message.session_id or "")
        queue = self._recent.get(session)
        if not queue:
            return
        now = time.monotonic()
        self._expire(queue, now)
        if not queue:
            self._recent.pop(session, None)
            return

        request = queue[-1]
        response_fields: tuple[int, ...] = ()
        response_malformed = False
        try:
            parsed = parse_protobuf_fields(
                bytes(message.payload),
                max_bytes=_MAX_DIAGNOSTIC_PROTOBUF_BYTES,
            )
            response_fields = tuple(sorted(int(field_number) for field_number in parsed))
        except ProtobufDecodeError:
            response_malformed = True

        response_type = str(message.type_url or "")
        key = f"request-response:{request.metadata.type_url}:{response_type}"
        if not DEBUG_GATE.should_log(key, first=3, every=100):
            return
        network_debug_log(
            self.logger,
            "[NETWORK][REQUEST_RESPONSE_CORRELATION]",
            phase=self.phase,
            session=session,
            request_type=request.metadata.type_url,
            request_opcode=request.metadata.opcode,
            request_payload_size=request.metadata.payload_size,
            request_payload_empty=request.metadata.payload_empty,
            response_type=response_type,
            response_opcode=response_type.rsplit("/", 1)[-1],
            response_payload_size=len(message.payload),
            response_payload_fields=response_fields,
            response_malformed=response_malformed,
            age_ms=max(0, int((now - request.observed_at) * 1000)),
            classification="temporal_only_unverified",
            quest_request_verified=False,
            quest_event_verified=False,
            occurrence=DEBUG_GATE.count(key),
        )

    def _trim_sessions(self, current_session: str) -> None:
        if current_session in self._recent:
            return
        while len(self._recent) >= _MAX_TRACKED_SESSIONS:
            self._recent.popitem(last=False)

    @staticmethod
    def _expire(queue: deque[_RecentRequest], now: float) -> None:
        while queue and now - queue[0].observed_at > _CORRELATION_WINDOW_SECONDS:
            queue.popleft()


class DiagnosticProtocolMessageSource:
    """Observe protocol transport passively without changing source semantics."""

    def __init__(
        self,
        delegate: ProtocolMessageSource,
        *,
        logger: Logger | None = None,
        phase: str = "runtime",
        build_sha256: str = "",
        active_build_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.delegate = delegate
        self.diagnostics = PassiveRequestResponseDiagnostics(
            logger=logger, phase=phase, build_sha256=build_sha256,
            active_build_provider=active_build_provider,
        )

    def start(self) -> None:
        self.diagnostics.clear()
        self.delegate.start()

    def stop(self) -> None:
        try:
            self.delegate.stop()
        finally:
            self.diagnostics.clear()

    def read_item(self, timeout: float) -> ProtocolTransportItem | None:
        item = self.delegate.read_item(timeout)
        if isinstance(item, CapturedProtocolMessage):
            self.diagnostics.observe(item)
        elif isinstance(item, TransportSessionClosed):
            self.diagnostics.session_closed(item.session_id)
        return item


__all__ = [
    "ClientRequestMetadata",
    "DiagnosticProtocolMessageSource",
    "PassiveRequestResponseDiagnostics",
    "client_request_metadata",
]
