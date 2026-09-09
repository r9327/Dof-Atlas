from __future__ import annotations

from dataclasses import dataclass


_MAX_VARINT_BYTES = 10
_DEFAULT_MAX_PAYLOAD = 4 * 1024 * 1024
_DEFAULT_MAX_BUFFER = 8 * 1024 * 1024
# Dofus 3.6.10.10 uses ``type.ankama.com/<opcode>``. Keep the historical
# shorter form readable for old offline evidence/tests, but production mappings
# still match the complete exact type URL.
_TYPE_PREFIXES = (b"type.ankama.com/", b"ankama.com/")
_TYPE_BYTES = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-"
)


@dataclass(frozen=True, slots=True)
class FramedProtocolMessage:
    type_url: str
    payload: bytes


class IncompleteVarint(ValueError):
    pass


class InvalidVarint(ValueError):
    pass


def decode_varint(data: bytes | bytearray | memoryview, offset: int = 0) -> tuple[int, int]:
    """Decode one canonical-width protobuf uint64 varint safely."""

    try:
        position = int(offset)
    except (TypeError, ValueError) as exc:
        raise InvalidVarint("protobuf varint offset is invalid") from exc
    if position < 0:
        raise InvalidVarint("protobuf varint offset cannot be negative")

    value = 0
    shift = 0
    for byte_index in range(_MAX_VARINT_BYTES):
        if position >= len(data):
            raise IncompleteVarint("protobuf varint is incomplete")
        current = int(data[position])
        position += 1
        # A protobuf uint64 uses at most one payload bit in byte 10. Accepting
        # larger values would silently parse an integer outside the wire format.
        if byte_index == _MAX_VARINT_BYTES - 1 and current > 0x01:
            raise InvalidVarint("protobuf varint exceeds 64 bits")
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value, position
        shift += 7
    raise InvalidVarint("protobuf varint exceeds 10 bytes")


class ProtobufAnyStreamDecoder:
    """Extract complete Ankama protobuf ``Any`` envelopes from a byte stream.

    This layer deliberately does not interpret message fields. A matching
    Ankama type URL is only framing evidence, never permission to mutate
    progression. The type URL must itself be encoded as ``Any.type_url`` field
    1 and followed by ``Any.value`` field 2; a matching byte sequence embedded
    in arbitrary payload is rejected.
    """

    def __init__(
        self,
        *,
        max_payload_bytes: int = _DEFAULT_MAX_PAYLOAD,
        max_buffer_bytes: int = _DEFAULT_MAX_BUFFER,
        max_type_bytes: int = 512,
    ) -> None:
        self.max_payload_bytes = max(1024, int(max_payload_bytes))
        self.max_buffer_bytes = max(self.max_payload_bytes, int(max_buffer_bytes))
        self.max_type_bytes = max(32, int(max_type_bytes))
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[FramedProtocolMessage]:
        if data:
            self._buffer.extend(data)
        messages: list[FramedProtocolMessage] = []
        consumed = 0

        while True:
            found = self._find_next_type_prefix(consumed)
            if found is None:
                break
            prefix_at, prefix = found

            type_end = prefix_at + len(prefix)
            type_limit = min(len(self._buffer), type_end + self.max_type_bytes)
            while type_end < type_limit and int(self._buffer[type_end]) in _TYPE_BYTES:
                type_end += 1

            if type_end == prefix_at + len(prefix):
                consumed = prefix_at + 1
                continue
            if type_end >= len(self._buffer):
                # Type URL may be split across TCP segments. Retain enough
                # prefix bytes to preserve the Any field-1 tag + uint64 varint
                # length (at most 11 bytes total) for the next read.
                consumed = max(0, prefix_at - (_MAX_VARINT_BYTES + 1))
                break
            if type_end - prefix_at >= self.max_type_bytes:
                consumed = prefix_at + 1
                continue
            if not self._has_any_type_header(prefix_at, type_end):
                consumed = prefix_at + 1
                continue
            if self._buffer[type_end] != 0x12:  # protobuf Any.value field
                consumed = prefix_at + 1
                continue

            try:
                payload_length, payload_at = decode_varint(self._buffer, type_end + 1)
            except IncompleteVarint:
                consumed = max(0, prefix_at - (_MAX_VARINT_BYTES + 1))
                break
            except InvalidVarint:
                consumed = prefix_at + 1
                continue

            if payload_length > self.max_payload_bytes:
                consumed = prefix_at + 1
                continue
            payload_end = payload_at + payload_length
            if payload_end > len(self._buffer):
                consumed = max(0, prefix_at - (_MAX_VARINT_BYTES + 1))
                break

            raw_type = bytes(self._buffer[prefix_at:type_end])
            try:
                type_url = raw_type.decode("ascii", errors="strict")
            except UnicodeDecodeError:
                consumed = prefix_at + 1
                continue
            messages.append(
                FramedProtocolMessage(
                    type_url=type_url,
                    payload=bytes(self._buffer[payload_at:payload_end]),
                )
            )
            consumed = payload_end

        self._compact(consumed)
        return messages

    def _find_next_type_prefix(self, start: int) -> tuple[int, bytes] | None:
        best: tuple[int, bytes] | None = None
        for prefix in _TYPE_PREFIXES:
            prefix_at = self._buffer.find(prefix, start)
            if prefix_at < 0:
                continue
            if best is None or prefix_at < best[0] or (
                prefix_at == best[0] and len(prefix) > len(best[1])
            ):
                best = (prefix_at, prefix)
        return best

    def _has_any_type_header(self, prefix_at: int, type_end: int) -> bool:
        type_length = type_end - prefix_at
        earliest_tag = max(0, prefix_at - (_MAX_VARINT_BYTES + 1))
        for tag_at in range(earliest_tag, prefix_at):
            if self._buffer[tag_at] != 0x0A:  # protobuf Any.type_url field
                continue
            try:
                encoded_length, value_at = decode_varint(self._buffer, tag_at + 1)
            except (IncompleteVarint, InvalidVarint):
                continue
            if value_at == prefix_at and int(encoded_length) == type_length:
                return True
        return False

    def _compact(self, consumed: int) -> None:
        if consumed > 0:
            del self._buffer[:consumed]
        if len(self._buffer) <= self.max_buffer_bytes:
            return
        # Keep enough suffix to detect both a split type prefix and its short
        # protobuf field header on the next segment.
        longest_prefix = max(len(prefix) for prefix in _TYPE_PREFIXES)
        keep = max(longest_prefix + _MAX_VARINT_BYTES, min(self.max_buffer_bytes, 65536))
        del self._buffer[:-keep]


class TcpStreamReassembler:
    """Small bounded TCP payload reassembler for one direction of one flow."""

    def __init__(self, *, max_pending_bytes: int = 2 * 1024 * 1024) -> None:
        self.max_pending_bytes = max(65536, int(max_pending_bytes))
        self._next_sequence: int | None = None
        self._pending: dict[int, bytes] = {}
        self._pending_bytes = 0

    def reset(self) -> None:
        self._next_sequence = None
        self._pending.clear()
        self._pending_bytes = 0

    def feed(self, sequence: int, payload: bytes) -> bytes:
        if not payload:
            return b""
        sequence32 = int(sequence) & 0xFFFFFFFF
        if self._next_sequence is None:
            self._next_sequence = sequence32 + len(payload)
            return bytes(payload)

        sequence_abs = self._unwrap(sequence32, self._next_sequence)
        next_sequence = self._next_sequence
        segment = bytes(payload)

        if sequence_abs < next_sequence:
            overlap = next_sequence - sequence_abs
            if overlap >= len(segment):
                return b""
            segment = segment[overlap:]
            sequence_abs = next_sequence

        if sequence_abs > next_sequence:
            self._remember_pending(sequence_abs, segment)
            return b""

        chunks = [segment]
        self._next_sequence = next_sequence + len(segment)
        chunks.extend(self._drain_contiguous())
        return b"".join(chunks)

    def _drain_contiguous(self) -> list[bytes]:
        chunks: list[bytes] = []
        while self._pending and self._next_sequence is not None:
            candidate_start = min(self._pending)
            candidate = self._pending[candidate_start]
            if candidate_start > self._next_sequence:
                break
            self._pending.pop(candidate_start, None)
            self._pending_bytes -= len(candidate)
            overlap = self._next_sequence - candidate_start
            if overlap >= len(candidate):
                continue
            if overlap > 0:
                candidate = candidate[overlap:]
            chunks.append(candidate)
            self._next_sequence += len(candidate)
        return chunks

    def _remember_pending(self, sequence: int, payload: bytes) -> None:
        existing = self._pending.get(sequence)
        if existing is not None and len(existing) >= len(payload):
            return
        if existing is not None:
            self._pending_bytes -= len(existing)
        self._pending[sequence] = payload
        self._pending_bytes += len(payload)
        if self._pending_bytes <= self.max_pending_bytes:
            return
        # An unbounded gap is not safe to guess through. Reset rather than join
        # unrelated bytes and risk manufacturing a business event.
        self.reset()

    @staticmethod
    def _unwrap(sequence32: int, reference: int) -> int:
        cycle = 1 << 32
        base = reference & ~(cycle - 1)
        candidates = (
            base + sequence32,
            base + sequence32 - cycle,
            base + sequence32 + cycle,
        )
        return min(candidates, key=lambda value: abs(value - reference))


__all__ = [
    "FramedProtocolMessage",
    "IncompleteVarint",
    "InvalidVarint",
    "ProtobufAnyStreamDecoder",
    "TcpStreamReassembler",
    "decode_varint",
]
