from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from app.network.wire import IncompleteVarint, InvalidVarint, decode_varint


_MAX_PROTOBUF_FIELD_NUMBER = (1 << 29) - 1


class ProtobufDecodeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Fixed32Value:
    raw: bytes


@dataclass(frozen=True, slots=True)
class Fixed64Value:
    raw: bytes


ProtobufValue: TypeAlias = int | bytes | Fixed32Value | Fixed64Value
ProtobufFields: TypeAlias = dict[int, tuple[ProtobufValue, ...]]


def parse_protobuf_fields(payload: bytes, *, max_bytes: int = 4 * 1024 * 1024) -> ProtobufFields:
    """Strictly parse one protobuf payload.

    Unlike diagnostic parsers that return a partial result on malformed data,
    this function fails the entire message. A partial packet must never become a
    reliable progression event.
    """

    if len(payload) > max(1024, int(max_bytes)):
        raise ProtobufDecodeError("protobuf payload exceeds configured limit")
    values: dict[int, list[ProtobufValue]] = {}
    offset = 0
    try:
        while offset < len(payload):
            tag, offset = decode_varint(payload, offset)
            field_number = int(tag) >> 3
            wire_type = int(tag) & 0x07
            if field_number <= 0 or field_number > _MAX_PROTOBUF_FIELD_NUMBER:
                raise ProtobufDecodeError("protobuf field number is outside the valid range")

            if wire_type == 0:
                value, offset = decode_varint(payload, offset)
                values.setdefault(field_number, []).append(int(value))
            elif wire_type == 1:
                end = offset + 8
                if end > len(payload):
                    raise ProtobufDecodeError("truncated fixed64 field")
                values.setdefault(field_number, []).append(Fixed64Value(bytes(payload[offset:end])))
                offset = end
            elif wire_type == 2:
                length, offset = decode_varint(payload, offset)
                end = offset + int(length)
                if end > len(payload):
                    raise ProtobufDecodeError("truncated length-delimited field")
                values.setdefault(field_number, []).append(bytes(payload[offset:end]))
                offset = end
            elif wire_type == 5:
                end = offset + 4
                if end > len(payload):
                    raise ProtobufDecodeError("truncated fixed32 field")
                values.setdefault(field_number, []).append(Fixed32Value(bytes(payload[offset:end])))
                offset = end
            else:
                raise ProtobufDecodeError(f"unsupported protobuf wire type {wire_type}")
    except (IncompleteVarint, InvalidVarint) as exc:
        raise ProtobufDecodeError(str(exc)) from exc
    return {field_number: tuple(rows) for field_number, rows in values.items()}


def resolve_field_path(
    payload: bytes,
    path: tuple[int, ...],
    *,
    expected_kind: str,
) -> int | str | None:
    """Resolve one unambiguous scalar/string field path.

    Mapping rules describe singular semantic values. If any path component is
    repeated, choosing a first/last occurrence would make progression depend on
    an implicit protobuf conflict rule. Reject the message instead.
    """

    if not path:
        return None
    current_payload = bytes(payload)
    for index, field_number in enumerate(path):
        fields = parse_protobuf_fields(current_payload)
        rows = fields.get(int(field_number), ())
        if len(rows) != 1:
            return None
        value = rows[0]
        is_last = index == len(path) - 1
        if not is_last:
            if not isinstance(value, bytes):
                return None
            current_payload = value
            continue
        if expected_kind == "positive_int":
            if not isinstance(value, int) or value <= 0:
                return None
            return int(value)
        if expected_kind == "non_negative_int":
            if not isinstance(value, int) or value < 0:
                return None
            return int(value)
        if expected_kind == "string":
            if not isinstance(value, bytes):
                return None
            try:
                decoded = value.decode("utf-8", errors="strict").strip()
            except UnicodeDecodeError:
                return None
            return decoded or None
        return None
    return None


__all__ = [
    "Fixed32Value",
    "Fixed64Value",
    "ProtobufDecodeError",
    "ProtobufFields",
    "ProtobufValue",
    "parse_protobuf_fields",
    "resolve_field_path",
]
