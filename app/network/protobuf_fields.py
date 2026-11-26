from __future__ import annotations

from collections.abc import Iterator
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


def _iter_packed_positive_varints(payload: bytes, *, limit: int | None = None) -> Iterator[int]:
    offset = 0
    count = 0
    while offset < len(payload):
        if limit is not None and count >= limit:
            raise ProtobufDecodeError("packed ID list exceeds configured limit")
        value, offset = decode_varint(payload, offset)
        if value <= 0:
            raise ProtobufDecodeError("packed IDs must be positive")
        count += 1
        yield int(value)


def decode_packed_positive_varints(payload: bytes, *, limit: int | None = None) -> tuple[int, ...] | None:
    """Decode all positive packed wire IDs, rejecting malformed or excessive lists."""
    try:
        return tuple(_iter_packed_positive_varints(payload, limit=limit))
    except (IncompleteVarint, InvalidVarint, ProtobufDecodeError):
        return None


def historical_quest_entry_id(raw_entry: object, *, finished: bool) -> int | None:
    """The historical QuestsEvent entry shape, shared by discovery and runtime."""
    if not isinstance(raw_entry, bytes):
        return None
    try:
        fields = parse_protobuf_fields(raw_entry)
    except ProtobufDecodeError:
        return None
    if not fields or not set(fields).issubset({1, 2}):
        return None
    quest_rows = fields.get(1, ())
    if len(quest_rows) != 1 or not isinstance(quest_rows[0], int) or quest_rows[0] <= 0:
        return None
    details = fields.get(2, ())
    if finished:
        if len(details) != 1 or not isinstance(details[0], int) or details[0] <= 0:
            return None
    elif len(details) > 1 or any(not isinstance(value, bytes) for value in details):
        return None
    return int(quest_rows[0])


def _iter_historical_reinitialized_ids(rows: tuple[object, ...]) -> Iterator[int]:
    for row in rows:
        if isinstance(row, int):
            if row <= 0:
                raise ProtobufDecodeError("reinitialized IDs must be positive")
            yield int(row)
        elif isinstance(row, bytes):
            yield from _iter_packed_positive_varints(row)
        else:
            raise ProtobufDecodeError("invalid reinitialized ID field")


def historical_reinitialized_ids(rows: tuple[object, ...]) -> tuple[int, ...] | None:
    """Historical repeated/packed IDs, retaining the first occurrence order."""
    try:
        return tuple(dict.fromkeys(_iter_historical_reinitialized_ids(rows)))
    except (IncompleteVarint, InvalidVarint, ProtobufDecodeError):
        return None


def historical_reinitialized_rows_valid(rows: tuple[object, ...]) -> bool:
    """Validate the same wire format without materializing unused IDs."""
    try:
        for _ in _iter_historical_reinitialized_ids(rows):
            pass
    except (IncompleteVarint, InvalidVarint, ProtobufDecodeError):
        return False
    return True


def resolve_repeated_positive_int_path(
    payload: bytes,
    path: tuple[int, ...],
    *,
    limit: int = 8192,
) -> tuple[int, ...] | None:
    """Resolve an explicit repeated message field with a singular ID in each row."""
    root_field, *id_path = path
    rows = parse_protobuf_fields(payload).get(root_field, ())
    if not rows or len(rows) > limit:
        return None
    values: list[int] = []
    for row in rows:
        if not isinstance(row, bytes):
            return None
        value = resolve_field_path(row, tuple(id_path), expected_kind="positive_int")
        if not isinstance(value, int):
            return None
        values.append(value)
    return tuple(dict.fromkeys(values))


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
