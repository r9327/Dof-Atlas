from __future__ import annotations

import json
import unittest

from app.network.diagnostics import ProtocolDiagnosticsCollector
from app.network.transport import CapturedProtocolMessage


def encode_varint(value: int) -> bytes:
    output = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


def varint_field(field_number: int, value: int) -> bytes:
    return encode_varint((field_number << 3) | 0) + encode_varint(value)


def bytes_field(field_number: int, value: bytes) -> bytes:
    return encode_varint((field_number << 3) | 2) + encode_varint(len(value)) + value


class NetworkDiagnosticsTests(unittest.TestCase):
    def test_snapshot_contains_only_aggregate_shape_not_scalar_values(self) -> None:
        collector = ProtocolDiagnosticsCollector()
        secret_scalar = 987654321
        collector.observe(
            CapturedProtocolMessage(
                session_id="sensitive-session-id",
                type_url="ankama.com/abc",
                payload=varint_field(1, secret_scalar) + bytes_field(2, b"private-name"),
            )
        )
        collector.observe(
            CapturedProtocolMessage(
                session_id="another-session",
                type_url="ankama.com/abc",
                payload=varint_field(1, 42) + bytes_field(2, b"other-private-name"),
            )
        )

        snapshot = collector.snapshot()
        self.assertEqual(len(snapshot), 1)
        row = snapshot[0]
        self.assertEqual(row.type_url, "ankama.com/abc")
        self.assertEqual(row.message_count, 2)
        self.assertEqual(row.malformed_payload_count, 0)
        self.assertEqual(row.top_level_shapes, (("1=varint:1,2=bytes:1", 2),))

        serialized = json.dumps(row.to_dict(), sort_keys=True)
        self.assertNotIn(str(secret_scalar), serialized)
        self.assertNotIn("private-name", serialized)
        self.assertNotIn("sensitive-session-id", serialized)

    def test_malformed_payload_is_counted_without_partial_shape(self) -> None:
        collector = ProtocolDiagnosticsCollector()
        collector.observe(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/broken",
                payload=b"\x0a\x10short",
            )
        )
        row = collector.snapshot()[0]
        self.assertEqual(row.message_count, 1)
        self.assertEqual(row.malformed_payload_count, 1)
        self.assertEqual(row.top_level_shapes, ())

    def test_type_and_shape_limits_are_bounded(self) -> None:
        collector = ProtocolDiagnosticsCollector(max_types=32, max_shapes_per_type=4)
        for index in range(40):
            collector.observe(
                CapturedProtocolMessage(
                    session_id=f"session-{index}",
                    type_url=f"ankama.com/type-{index}",
                    payload=varint_field(1, index + 1),
                )
            )
        self.assertEqual(len(collector.snapshot()), 32)
        self.assertEqual(collector.dropped_type_count, 8)

    def test_clear_removes_all_metadata(self) -> None:
        collector = ProtocolDiagnosticsCollector()
        collector.observe(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/abc",
                payload=varint_field(1, 1),
            )
        )
        collector.clear()
        self.assertEqual(collector.snapshot(), ())
        self.assertEqual(collector.dropped_type_count, 0)


if __name__ == "__main__":
    unittest.main()
