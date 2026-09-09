from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from app.network.transport import CapturedProtocolMessage, TransportSessionClosed
from app.network.windows_capture import ParsedIpv4TcpPacket, WindowsRawProtocolSource, _TrackedFlow, parse_ipv4_tcp_packet
from app.network.windows_tcp import WindowsTcpFlow
from app.network.wire import InvalidVarint, ProtobufAnyStreamDecoder, TcpStreamReassembler, decode_varint


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


def any_envelope(type_url: str, payload: bytes) -> bytes:
    encoded_type = type_url.encode("ascii")
    return b"\x0a" + encode_varint(len(encoded_type)) + encoded_type + b"\x12" + encode_varint(len(payload)) + payload


def any_envelope_header(type_url: str, payload_length: int) -> bytes:
    encoded_type = type_url.encode("ascii")
    return (
        b"\x0a"
        + encode_varint(len(encoded_type))
        + encoded_type
        + b"\x12"
        + encode_varint(payload_length)
    )


def ipv4_tcp_packet(
    *,
    source_ip: str,
    destination_ip: str,
    source_port: int,
    destination_port: int,
    sequence: int,
    flags: int = 0x18,
    payload: bytes = b"",
) -> bytes:
    ip_header_len = 20
    tcp_header_len = 20
    total_len = ip_header_len + tcp_header_len + len(payload)
    ip = bytearray(ip_header_len)
    ip[0] = 0x45
    ip[2:4] = total_len.to_bytes(2, "big")
    ip[8] = 64
    ip[9] = 6
    ip[12:16] = socket.inet_aton(source_ip)
    ip[16:20] = socket.inet_aton(destination_ip)
    tcp = bytearray(tcp_header_len)
    tcp[0:2] = int(source_port).to_bytes(2, "big")
    tcp[2:4] = int(destination_port).to_bytes(2, "big")
    tcp[4:8] = (int(sequence) & 0xFFFFFFFF).to_bytes(4, "big")
    tcp[12] = 5 << 4
    tcp[13] = int(flags) & 0xFF
    return bytes(ip + tcp + payload)


class NetworkWireTests(unittest.TestCase):
    def test_decode_varint(self) -> None:
        encoded = encode_varint(300)
        value, offset = decode_varint(encoded)
        self.assertEqual(value, 300)
        self.assertEqual(offset, len(encoded))

    def test_decode_varint_accepts_max_uint64(self) -> None:
        encoded = (b"\xff" * 9) + b"\x01"
        value, offset = decode_varint(encoded)
        self.assertEqual(value, (1 << 64) - 1)
        self.assertEqual(offset, 10)

    def test_decode_varint_rejects_uint64_overflow_and_negative_offset(self) -> None:
        with self.assertRaises(InvalidVarint):
            decode_varint((b"\xff" * 9) + b"\x02")
        with self.assertRaises(InvalidVarint):
            decode_varint(b"\x01", -1)

    def test_current_dofus_type_url_split_across_reads_is_emitted_once(self) -> None:
        decoder = ProtobufAnyStreamDecoder()
        frame = any_envelope("type.ankama.com/abc", b"payload")
        split_at = len(frame) - 3
        self.assertEqual(decoder.feed(frame[:split_at]), [])
        messages = decoder.feed(frame[split_at:])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].type_url, "type.ankama.com/abc")
        self.assertEqual(messages[0].payload, b"payload")
        self.assertEqual(decoder.feed(b""), [])

    def test_legacy_ankama_type_url_remains_readable_for_offline_evidence(self) -> None:
        decoder = ProtobufAnyStreamDecoder()
        frame = any_envelope("ankama.com/abc", b"payload")
        messages = decoder.feed(frame)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].type_url, "ankama.com/abc")

    def test_protobuf_any_type_field_header_may_be_split_across_reads(self) -> None:
        decoder = ProtobufAnyStreamDecoder()
        frame = any_envelope("type.ankama.com/split", b"payload")
        prefix_at = frame.index(b"type.ankama.com/")
        self.assertEqual(decoder.feed(frame[:prefix_at]), [])
        messages = decoder.feed(frame[prefix_at:])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].type_url, "type.ankama.com/split")
        self.assertEqual(messages[0].payload, b"payload")

    def test_incomplete_or_oversized_valid_any_frame_is_not_fabricated(self) -> None:
        decoder = ProtobufAnyStreamDecoder(max_payload_bytes=1024)
        incomplete = any_envelope_header("type.ankama.com/abc", 20) + b"short"
        self.assertEqual(decoder.feed(incomplete), [])
        decoder.reset()
        oversized = any_envelope_header("type.ankama.com/abc", 2048)
        self.assertEqual(decoder.feed(oversized), [])

    def test_embedded_type_url_without_any_type_field_header_is_rejected(self) -> None:
        decoder = ProtobufAnyStreamDecoder()
        fake = b"noise:" + b"type.ankama.com/abc" + b"\x12" + encode_varint(4) + b"data"
        self.assertEqual(decoder.feed(fake), [])

    def test_wrong_any_type_length_is_rejected(self) -> None:
        decoder = ProtobufAnyStreamDecoder()
        type_url = b"type.ankama.com/abc"
        malformed = b"\x0a" + encode_varint(len(type_url) + 1) + type_url + b"\x12\x04data"
        self.assertEqual(decoder.feed(malformed), [])

    def test_tcp_reassembler_handles_out_of_order_and_duplicate_segments(self) -> None:
        reassembler = TcpStreamReassembler()
        self.assertEqual(reassembler.feed(1000, b"abc"), b"abc")
        self.assertEqual(reassembler.feed(1006, b"ghi"), b"")
        self.assertEqual(reassembler.feed(1003, b"def"), b"defghi")
        self.assertEqual(reassembler.feed(1000, b"abc"), b"")

    def test_tcp_reassembler_handles_sequence_wrap(self) -> None:
        reassembler = TcpStreamReassembler()
        self.assertEqual(reassembler.feed(0xFFFFFFFE, b"ab"), b"ab")
        self.assertEqual(reassembler.feed(0, b"cd"), b"cd")

    def test_ipv4_tcp_parser_extracts_only_application_payload(self) -> None:
        raw = ipv4_tcp_packet(
            source_ip="203.0.113.10",
            destination_ip="192.0.2.4",
            source_port=5555,
            destination_port=49152,
            sequence=12345,
            payload=b"hello",
        )
        packet = parse_ipv4_tcp_packet(raw)
        self.assertIsNotNone(packet)
        self.assertEqual(packet.source_ip, "203.0.113.10")
        self.assertEqual(packet.destination_ip, "192.0.2.4")
        self.assertEqual(packet.source_port, 5555)
        self.assertEqual(packet.destination_port, 49152)
        self.assertEqual(packet.sequence, 12345)
        self.assertEqual(packet.payload, b"hello")

    def test_ipv4_tcp_parser_rejects_non_tcp_and_truncated_packets(self) -> None:
        self.assertIsNone(parse_ipv4_tcp_packet(b"\x45" + (b"\x00" * 10)))
        udp_like = bytearray(
            ipv4_tcp_packet(
                source_ip="203.0.113.10",
                destination_ip="192.0.2.4",
                source_port=5555,
                destination_port=49152,
                sequence=1,
            )
        )
        udp_like[9] = 17
        self.assertIsNone(parse_ipv4_tcp_packet(bytes(udp_like)))

    def test_fin_packet_payload_is_emitted_before_session_close(self) -> None:
        source = WindowsRawProtocolSource(lambda: ())
        flow = WindowsTcpFlow(
            pid=42,
            local_ip="192.0.2.4",
            local_port=49152,
            remote_ip="203.0.113.10",
            remote_port=5555,
        )
        source._flows[flow.key] = _TrackedFlow(
            flow=flow,
            session_id="tcp:42:1",
            server_reassembler=TcpStreamReassembler(),
            server_decoder=ProtobufAnyStreamDecoder(),
            client_reassembler=TcpStreamReassembler(),
            client_decoder=ProtobufAnyStreamDecoder(),
        )
        frame = any_envelope("type.ankama.com/final", b"done")
        source._handle_packet(
            ParsedIpv4TcpPacket(
                source_ip=flow.remote_ip,
                destination_ip=flow.local_ip,
                source_port=flow.remote_port,
                destination_port=flow.local_port,
                sequence=1000,
                flags=0x11,
                payload=frame,
            )
        )

        first = source._get_queued_item()
        second = source._get_queued_item()
        self.assertIsInstance(first, CapturedProtocolMessage)
        self.assertEqual(first.type_url, "type.ankama.com/final")
        self.assertEqual(first.payload, b"done")
        self.assertIsInstance(second, TransportSessionClosed)
        self.assertEqual(second.session_id, "tcp:42:1")
        self.assertNotIn(flow.key, source._flows)

    def test_capture_diagnostics_count_each_raw_processing_stage(self) -> None:
        source = WindowsRawProtocolSource(lambda: ())
        flow = WindowsTcpFlow(
            pid=42,
            local_ip="192.0.2.4",
            local_port=49152,
            remote_ip="203.0.113.10",
            remote_port=5555,
        )
        source._flows[flow.key] = _TrackedFlow(
            flow=flow,
            session_id="tcp:42:1",
            server_reassembler=TcpStreamReassembler(),
            server_decoder=ProtobufAnyStreamDecoder(),
            client_reassembler=TcpStreamReassembler(),
            client_decoder=ProtobufAnyStreamDecoder(),
        )
        frame = any_envelope("type.ankama.com/diagnostic", b"payload")

        source._process_raw_packet(
            ipv4_tcp_packet(
                source_ip=flow.remote_ip,
                destination_ip=flow.local_ip,
                source_port=flow.remote_port,
                destination_port=flow.local_port,
                sequence=1000,
                payload=frame,
            )
        )

        diagnostic = source.diagnostic_snapshot()
        self.assertEqual(diagnostic["raw_packet_count"], 1)
        self.assertEqual(diagnostic["parsed_tcp_packet_count"], 1)
        self.assertEqual(diagnostic["matched_packet_count"], 1)
        self.assertEqual(diagnostic["matched_payload_bytes"], len(frame))
        self.assertEqual(diagnostic["reassembled_payload_bytes"], len(frame))
        self.assertEqual(diagnostic["framed_message_count"], 1)
        self.assertEqual(diagnostic["server_to_client_matched_packet_count"], 1)
        self.assertEqual(
            diagnostic["server_to_client_matched_payload_bytes"], len(frame)
        )
        self.assertEqual(
            diagnostic["server_to_client_reassembled_payload_bytes"], len(frame)
        )
        self.assertEqual(diagnostic["server_to_client_framed_message_count"], 1)
        self.assertEqual(diagnostic["client_to_server_matched_packet_count"], 0)
        self.assertEqual(diagnostic["client_to_server_matched_payload_bytes"], 0)
        self.assertEqual(diagnostic["client_to_server_reassembled_payload_bytes"], 0)
        self.assertEqual(diagnostic["client_to_server_framed_message_count"], 0)

        outbound_frame = any_envelope("type.ankama.com/outbound", b"request")
        source._process_raw_packet(
            ipv4_tcp_packet(
                source_ip=flow.local_ip,
                destination_ip=flow.remote_ip,
                source_port=flow.local_port,
                destination_port=flow.remote_port,
                sequence=2000,
                payload=outbound_frame,
            )
        )

        diagnostic = source.diagnostic_snapshot()
        self.assertEqual(diagnostic["client_to_server_matched_packet_count"], 1)
        self.assertEqual(
            diagnostic["client_to_server_matched_payload_bytes"], len(outbound_frame)
        )
        self.assertEqual(
            diagnostic["client_to_server_reassembled_payload_bytes"],
            len(outbound_frame),
        )
        self.assertEqual(diagnostic["client_to_server_framed_message_count"], 1)

    def test_packets_arriving_before_owner_table_flow_are_replayed(self) -> None:
        source = WindowsRawProtocolSource(lambda: (9001,), flow_refresh_seconds=0.25)
        flow = WindowsTcpFlow(
            pid=42,
            local_ip="192.0.2.4",
            local_port=49152,
            remote_ip="203.0.113.10",
            remote_port=5555,
        )
        frame = any_envelope("type.ankama.com/kva", b"selected-character")
        source._process_raw_packet(
            ipv4_tcp_packet(
                source_ip=flow.remote_ip,
                destination_ip=flow.local_ip,
                source_port=flow.remote_port,
                destination_port=flow.local_port,
                sequence=1000,
                payload=frame,
            )
        )
        self.assertEqual(source.diagnostic_snapshot()["pending_packet_count"], 1)

        with (
            patch("app.network.windows_capture.process_id_for_window", return_value=42),
            patch(
                "app.network.windows_capture.established_tcp_flows_for_pids",
                return_value=(flow,),
            ),
            patch.object(source, "_open_capture_socket", return_value=None),
        ):
            source._refresh_flows(force=True)

        message = source._get_queued_item()
        self.assertIsInstance(message, CapturedProtocolMessage)
        self.assertEqual(message.type_url, "type.ankama.com/kva")
        self.assertEqual(message.payload, b"selected-character")
        diagnostic = source.diagnostic_snapshot()
        self.assertEqual(diagnostic["pending_packet_count"], 0)
        self.assertEqual(diagnostic["replayed_packet_count"], 1)



if __name__ == "__main__":
    unittest.main()
