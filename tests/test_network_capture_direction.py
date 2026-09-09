from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace

from app.network.elevated_capture import ElevatedWindowsProtocolSource
from app.network.transport import CapturedProtocolMessage
from app.network.windows_capture import ParsedIpv4TcpPacket, WindowsRawProtocolSource, _TrackedFlow
from app.network.windows_tcp import WindowsTcpFlow


class _RecordingReassembler:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bytes]] = []

    def feed(self, sequence: int, payload: bytes) -> bytes:
        self.calls.append((int(sequence), bytes(payload)))
        return bytes(payload)


class _RecordingDecoder:
    def __init__(self, type_url: str) -> None:
        self.type_url = type_url
        self.calls: list[bytes] = []

    def feed(self, payload: bytes) -> list[SimpleNamespace]:
        data = bytes(payload)
        self.calls.append(data)
        return [SimpleNamespace(type_url=self.type_url, payload=data)]


class NetworkCaptureDirectionTests(unittest.TestCase):
    def _source_with_flow(self):
        source = WindowsRawProtocolSource(lambda: ())
        flow = WindowsTcpFlow(
            pid=4242,
            local_ip="10.0.0.5",
            local_port=50123,
            remote_ip="34.120.10.20",
            remote_port=443,
        )
        server_reassembler = _RecordingReassembler()
        client_reassembler = _RecordingReassembler()
        server_decoder = _RecordingDecoder("type.ankama.com/server")
        client_decoder = _RecordingDecoder("type.ankama.com/client")
        source._flows[flow.key] = _TrackedFlow(
            flow=flow,
            session_id="tcp:4242:1",
            server_reassembler=server_reassembler,  # type: ignore[arg-type]
            server_decoder=server_decoder,  # type: ignore[arg-type]
            client_reassembler=client_reassembler,  # type: ignore[arg-type]
            client_decoder=client_decoder,  # type: ignore[arg-type]
        )
        return (
            source,
            flow,
            server_reassembler,
            client_reassembler,
            server_decoder,
            client_decoder,
        )

    def test_tracked_flow_keeps_server_and_client_tcp_sequences_independent(self) -> None:
        (
            source,
            flow,
            server_reassembler,
            client_reassembler,
            server_decoder,
            client_decoder,
        ) = self._source_with_flow()

        source._handle_packet(
            ParsedIpv4TcpPacket(
                source_ip=flow.remote_ip,
                destination_ip=flow.local_ip,
                source_port=flow.remote_port,
                destination_port=flow.local_port,
                sequence=100,
                flags=0,
                payload=b"server-payload",
            )
        )
        source._handle_packet(
            ParsedIpv4TcpPacket(
                source_ip=flow.local_ip,
                destination_ip=flow.remote_ip,
                source_port=flow.local_port,
                destination_port=flow.remote_port,
                sequence=100,
                flags=0,
                payload=b"client-payload",
            )
        )

        server_item = source._get_queued_item()
        client_item = source._get_queued_item()
        self.assertIsInstance(server_item, CapturedProtocolMessage)
        self.assertIsInstance(client_item, CapturedProtocolMessage)
        assert isinstance(server_item, CapturedProtocolMessage)
        assert isinstance(client_item, CapturedProtocolMessage)
        self.assertEqual(server_item.direction, "server_to_client")
        self.assertEqual(client_item.direction, "client_to_server")
        self.assertEqual(server_item.type_url, "type.ankama.com/server")
        self.assertEqual(client_item.type_url, "type.ankama.com/client")
        self.assertEqual(server_reassembler.calls, [(100, b"server-payload")])
        self.assertEqual(client_reassembler.calls, [(100, b"client-payload")])
        self.assertEqual(server_decoder.calls, [b"server-payload"])
        self.assertEqual(client_decoder.calls, [b"client-payload"])

    def test_elevated_ipc_preserves_client_direction(self) -> None:
        item = ElevatedWindowsProtocolSource._transport_item_from_frame(
            {
                "kind": "message",
                "session_id": "tcp:4242:1",
                "type_url": "type.ankama.com/request",
                "payload": base64.b64encode(b"\x08\x01").decode("ascii"),
                "direction": "client_to_server",
            }
        )
        self.assertIsInstance(item, CapturedProtocolMessage)
        assert isinstance(item, CapturedProtocolMessage)
        self.assertEqual(item.direction, "client_to_server")
        self.assertEqual(item.payload, b"\x08\x01")

    def test_elevated_ipc_defaults_old_frames_to_server_direction(self) -> None:
        item = ElevatedWindowsProtocolSource._transport_item_from_frame(
            {
                "kind": "message",
                "session_id": "tcp:4242:1",
                "type_url": "type.ankama.com/event",
                "payload": base64.b64encode(b"\x08\x02").decode("ascii"),
            }
        )
        self.assertIsInstance(item, CapturedProtocolMessage)
        assert isinstance(item, CapturedProtocolMessage)
        self.assertEqual(item.direction, "server_to_client")

    def test_elevated_ipc_rejects_unknown_direction(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "capture_helper_invalid_direction"):
            ElevatedWindowsProtocolSource._transport_item_from_frame(
                {
                    "kind": "message",
                    "session_id": "tcp:4242:1",
                    "type_url": "type.ankama.com/event",
                    "payload": base64.b64encode(b"\x08\x03").decode("ascii"),
                    "direction": "sideways",
                }
            )


if __name__ == "__main__":
    unittest.main()
