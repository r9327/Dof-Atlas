from __future__ import annotations

import unittest

from app.network.discovery import ProtocolTargetDiscoveryCollector
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
    return encode_varint((int(field_number) << 3) | 0) + encode_varint(value)


def bytes_field(field_number: int, value: bytes) -> bytes:
    return (
        encode_varint((int(field_number) << 3) | 2)
        + encode_varint(len(value))
        + value
    )


class NetworkDiscoveryTests(unittest.TestCase):
    def message(self, payload: bytes, *, type_url: str = "ankama.com/a", direction: str = "server_to_client"):
        return CapturedProtocolMessage(
            session_id="secret-session",
            type_url=type_url,
            payload=payload,
            direction=direction,
        )

    def test_top_level_positive_int_candidate_contains_no_expected_value(self) -> None:
        collector = ProtocolTargetDiscoveryCollector(expected_positive_ints=(1234,))
        collector.observe(self.message(varint_field(3, 1234)))

        rows = collector.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].type_url, "ankama.com/a")
        self.assertEqual(rows[0].path, (3,))
        self.assertEqual(rows[0].kind, "positive_int")
        self.assertEqual(rows[0].matching_message_count, 1)
        self.assertNotIn("1234", repr(rows[0].to_dict()))
        self.assertNotIn("secret-session", repr(rows[0].to_dict()))

    def test_nested_exact_string_candidate_is_found(self) -> None:
        inner = bytes_field(2, b"Alpha")
        payload = bytes_field(5, inner)
        collector = ProtocolTargetDiscoveryCollector(expected_strings=("Alpha",))
        collector.observe(self.message(payload))

        rows = collector.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].path, (5, 2))
        self.assertEqual(rows[0].kind, "string")
        self.assertNotIn("Alpha", repr(rows[0].to_dict()))

    def test_repeated_value_path_is_not_proposed(self) -> None:
        payload = varint_field(3, 1234) + varint_field(3, 1234)
        collector = ProtocolTargetDiscoveryCollector(expected_positive_ints=(1234,))
        collector.observe(self.message(payload))
        self.assertEqual(collector.snapshot(), ())

    def test_repeated_intermediate_path_is_not_proposed(self) -> None:
        inner = bytes_field(2, b"Alpha")
        payload = bytes_field(5, inner) + bytes_field(5, inner)
        collector = ProtocolTargetDiscoveryCollector(expected_strings=("Alpha",))
        collector.observe(self.message(payload))
        self.assertEqual(collector.snapshot(), ())

    def test_client_to_server_message_is_ignored(self) -> None:
        collector = ProtocolTargetDiscoveryCollector(expected_positive_ints=(1234,))
        collector.observe(
            self.message(varint_field(3, 1234), direction="client_to_server")
        )
        self.assertEqual(collector.snapshot(), ())
        self.assertEqual(collector.observed_message_count, 0)

    def test_malformed_root_payload_is_counted_without_candidate(self) -> None:
        collector = ProtocolTargetDiscoveryCollector(expected_positive_ints=(1234,))
        collector.observe(self.message(b"\x08\x80"))
        self.assertEqual(collector.snapshot(), ())
        self.assertEqual(collector.observed_message_count, 1)
        self.assertEqual(collector.malformed_message_count, 1)

    def test_candidates_are_aggregated_without_payload_retention(self) -> None:
        collector = ProtocolTargetDiscoveryCollector(expected_positive_ints=(1234,))
        message = self.message(varint_field(3, 1234))
        collector.observe(message)
        collector.observe(message)
        rows = collector.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].matching_message_count, 2)
        self.assertFalse(hasattr(rows[0], "payload"))
        self.assertFalse(hasattr(rows[0], "session_id"))

    def test_max_depth_prevents_unbounded_nested_guessing(self) -> None:
        level3 = varint_field(7, 1234)
        level2 = bytes_field(6, level3)
        level1 = bytes_field(5, level2)
        shallow = ProtocolTargetDiscoveryCollector(
            expected_positive_ints=(1234,),
            max_depth=2,
        )
        shallow.observe(self.message(level1))
        self.assertEqual(shallow.snapshot(), ())

        deep = ProtocolTargetDiscoveryCollector(
            expected_positive_ints=(1234,),
            max_depth=3,
        )
        deep.observe(self.message(level1))
        rows = deep.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].path, (5, 6, 7))


if __name__ == "__main__":
    unittest.main()
