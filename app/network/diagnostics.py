from __future__ import annotations

import json
import os
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Logger
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from app.network.protobuf_fields import (
    Fixed32Value,
    Fixed64Value,
    ProtobufDecodeError,
    parse_protobuf_fields,
)

if TYPE_CHECKING:
    from app.network.transport import CapturedProtocolMessage

_NETWORK_DEBUG_ENV = "ATLAS_NETWORK_DEBUG"
_NETWORK_DEBUG_DEEP_ENV = "ATLAS_NETWORK_DEBUG_DEEP"
_MAX_DEBUG_SEQUENCE = 4096
_MAX_DEBUG_TEXT = 512
_MAX_DEEP_SCALAR_FIELDS = 32
_MAX_DEEP_SCALARS_PER_FIELD = 8


@dataclass(frozen=True, slots=True)
class ProtocolTypeDiagnostic:
    type_url: str
    message_count: int
    total_payload_bytes: int
    min_payload_bytes: int
    max_payload_bytes: int
    top_level_shapes: tuple[tuple[str, int], ...]
    malformed_payload_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_url": self.type_url,
            "message_count": self.message_count,
            "total_payload_bytes": self.total_payload_bytes,
            "min_payload_bytes": self.min_payload_bytes,
            "max_payload_bytes": self.max_payload_bytes,
            "top_level_shapes": [
                {"shape": shape, "count": count}
                for shape, count in self.top_level_shapes
            ],
            "malformed_payload_count": self.malformed_payload_count,
        }


@dataclass(slots=True)
class _MutableTypeDiagnostic:
    message_count: int = 0
    total_payload_bytes: int = 0
    min_payload_bytes: int = 0
    max_payload_bytes: int = 0
    shapes: Counter[str] | None = None
    malformed_payload_count: int = 0


class NetworkDebugGate:
    """Small duplicate limiter for very chatty diagnostic paths."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counts: Counter[str] = Counter()

    def should_log(self, key: str, *, first: int = 5, every: int = 100) -> bool:
        normalized = str(key or "<unknown>")
        with self._lock:
            self._counts[normalized] += 1
            count = self._counts[normalized]
        return count <= max(1, first) or (every > 0 and count % every == 0)

    def count(self, key: str) -> int:
        with self._lock:
            return int(self._counts.get(str(key or "<unknown>"), 0))

    def clear(self) -> None:
        with self._lock:
            self._counts.clear()


DEBUG_GATE = NetworkDebugGate()


def network_debug_enabled(*, deep: bool = False) -> bool:
    """Return whether explicit network diagnostics are enabled.

    Normal Atlas runs remain quiet. ``ATLAS_NETWORK_DEBUG_DEEP=1`` implies the
    regular mode and additionally allows bounded raw payload hex for relevant
    messages. The deep switch is intentionally separate because packet payloads
    can be large and may contain user-specific values.
    """

    regular = _env_truthy(os.environ.get(_NETWORK_DEBUG_ENV))
    deep_enabled = _env_truthy(os.environ.get(_NETWORK_DEBUG_DEEP_ENV))
    return deep_enabled if deep else (regular or deep_enabled)


def network_debug_log(logger: Logger, tag: str, /, **fields: Any) -> None:
    """Emit one grep-friendly structured diagnostic line when debug is enabled."""

    if not network_debug_enabled():
        return
    normalized_tag = str(tag or "[NETWORK][DEBUG]").strip()
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }
    for key, value in fields.items():
        payload[str(key)] = _safe_debug_value(value)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    logger.info("%s %s", normalized_tag, serialized)


def protocol_payload_scalar_samples(
    payload: bytes,
    *,
    max_fields: int = _MAX_DEEP_SCALAR_FIELDS,
    max_values_per_field: int = _MAX_DEEP_SCALARS_PER_FIELD,
) -> dict[str, tuple[int, ...]]:
    """Return bounded top-level varint samples without assigning semantics.

    This helper exists only for controlled deep protocol diagnostics. Values are
    intentionally reported as raw protobuf scalar candidates: Atlas must never
    treat a value such as ``200`` as a level, or ``18456`` as achievement
    points, until the surrounding message and field are independently verified.
    """

    try:
        fields = parse_protobuf_fields(payload)
    except ProtobufDecodeError:
        return {}

    output: dict[str, tuple[int, ...]] = {}
    for field_number in sorted(fields)[: max(0, int(max_fields))]:
        values: list[int] = []
        for value in fields[field_number]:
            if isinstance(value, int):
                values.append(int(value))
            if len(values) >= max(0, int(max_values_per_field)):
                break
        if values:
            output[str(int(field_number))] = tuple(values)
    return output


def protocol_payload_summary(payload: bytes) -> dict[str, Any]:
    """Return bounded protobuf metadata without retaining the packet."""

    result: dict[str, Any] = {"payload_bytes": len(payload)}
    try:
        result["top_level_shape"] = _top_level_shape(payload)
        fields = parse_protobuf_fields(payload)
    except ProtobufDecodeError as exc:
        result["malformed"] = True
        result["decode_error"] = type(exc).__name__
        if network_debug_enabled(deep=True):
            result["payload_hex"] = payload[:2048].hex()
            result["payload_truncated"] = len(payload) > 2048
        return result

    result["payload_fields"] = tuple(sorted(int(field_number) for field_number in fields))
    if network_debug_enabled(deep=True):
        result["payload_scalar_samples"] = protocol_payload_scalar_samples(payload)
        result["payload_hex"] = payload[:2048].hex()
        result["payload_truncated"] = len(payload) > 2048
    return result


class ProtocolDiagnosticsCollector:
    """Collect bounded, payload-free metadata for local protocol investigation.

    The collector never retains packet bytes, decoded scalar values, character
    names, IDs, IP addresses, ports or session identifiers. It stores only the
    exact protobuf type URL, aggregate payload sizes and top-level wire *shape*.
    This is sufficient to compare short local captures without creating a packet
    archive or a second source of progression truth.
    """

    def __init__(self, *, max_types: int = 2048, max_shapes_per_type: int = 32) -> None:
        self.max_types = max(32, int(max_types))
        self.max_shapes_per_type = max(4, int(max_shapes_per_type))
        self._lock = threading.RLock()
        self._rows: dict[str, _MutableTypeDiagnostic] = {}
        self._dropped_type_count = 0

    @property
    def dropped_type_count(self) -> int:
        with self._lock:
            return self._dropped_type_count

    def observe(self, message: CapturedProtocolMessage) -> None:
        type_url = str(message.type_url or "").strip()
        if not type_url:
            return
        payload_size = len(message.payload)
        shape: str | None
        malformed = False
        try:
            shape = _top_level_shape(message.payload)
        except ProtobufDecodeError:
            shape = None
            malformed = True

        with self._lock:
            row = self._rows.get(type_url)
            if row is None:
                if len(self._rows) >= self.max_types:
                    self._dropped_type_count += 1
                    return
                row = _MutableTypeDiagnostic(shapes=Counter())
                self._rows[type_url] = row
            row.message_count += 1
            row.total_payload_bytes += payload_size
            if row.message_count == 1:
                row.min_payload_bytes = payload_size
                row.max_payload_bytes = payload_size
            else:
                row.min_payload_bytes = min(row.min_payload_bytes, payload_size)
                row.max_payload_bytes = max(row.max_payload_bytes, payload_size)
            if malformed:
                row.malformed_payload_count += 1
            elif shape is not None:
                assert row.shapes is not None
                if shape in row.shapes or len(row.shapes) < self.max_shapes_per_type:
                    row.shapes[shape] += 1
                else:
                    row.shapes["<other-shapes>"] += 1

    def snapshot(self) -> tuple[ProtocolTypeDiagnostic, ...]:
        with self._lock:
            output: list[ProtocolTypeDiagnostic] = []
            for type_url, row in self._rows.items():
                shapes = row.shapes or Counter()
                output.append(
                    ProtocolTypeDiagnostic(
                        type_url=type_url,
                        message_count=row.message_count,
                        total_payload_bytes=row.total_payload_bytes,
                        min_payload_bytes=row.min_payload_bytes,
                        max_payload_bytes=row.max_payload_bytes,
                        top_level_shapes=tuple(
                            sorted(shapes.items(), key=lambda item: (-item[1], item[0]))
                        ),
                        malformed_payload_count=row.malformed_payload_count,
                    )
                )
        return tuple(sorted(output, key=lambda item: item.type_url))

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._dropped_type_count = 0


def _top_level_shape(payload: bytes) -> str:
    fields = parse_protobuf_fields(payload)
    parts: list[str] = []
    for field_number in sorted(fields):
        values = fields[field_number]
        kinds = Counter(_wire_kind(value) for value in values)
        kind_text = "+".join(
            f"{kind}:{count}" for kind, count in sorted(kinds.items())
        )
        parts.append(f"{field_number}={kind_text}")
    return ",".join(parts) if parts else "<empty>"


def _wire_kind(value: object) -> str:
    if isinstance(value, int):
        return "varint"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, Fixed32Value):
        return "fixed32"
    if isinstance(value, Fixed64Value):
        return "fixed64"
    return "unknown"


def _env_truthy(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _safe_debug_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _MAX_DEBUG_TEXT else value[:_MAX_DEBUG_TEXT] + "…"
    if isinstance(value, bytes):
        if network_debug_enabled(deep=True):
            return {
                "bytes": len(value),
                "hex": value[:2048].hex(),
                "truncated": len(value) > 2048,
            }
        return {"bytes": len(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _safe_debug_value(item)
            for key, item in list(value.items())[:128]
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rows = list(value)
        if len(rows) > _MAX_DEBUG_SEQUENCE:
            return {
                "items": [_safe_debug_value(item) for item in rows[:_MAX_DEBUG_SEQUENCE]],
                "count": len(rows),
                "truncated": True,
            }
        return [_safe_debug_value(item) for item in rows]
    text = repr(value)
    return text if len(text) <= _MAX_DEBUG_TEXT else text[:_MAX_DEBUG_TEXT] + "…"


__all__ = [
    "DEBUG_GATE",
    "NetworkDebugGate",
    "ProtocolDiagnosticsCollector",
    "ProtocolTypeDiagnostic",
    "network_debug_enabled",
    "network_debug_log",
    "protocol_payload_scalar_samples",
    "protocol_payload_summary",
]
