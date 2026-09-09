from __future__ import annotations

import socket
import time
import unittest
from unittest.mock import patch

from app.network import capture_helper
from app.network.npcap_capture import (
    NpcapUnavailableError,
    NpcapWindowsProtocolSource,
    ipv4_packet_from_link_frame,
)


def _ipv4_stub() -> bytes:
    packet = bytearray(40)
    packet[0] = 0x45
    packet[2:4] = (40).to_bytes(2, "big")
    packet[9] = socket.IPPROTO_TCP
    packet[12:16] = socket.inet_aton("192.0.2.1")
    packet[16:20] = socket.inet_aton("198.51.100.2")
    packet[20:22] = (49152).to_bytes(2, "big")
    packet[22:24] = (5555).to_bytes(2, "big")
    packet[32] = 5 << 4
    return bytes(packet)


class _FakeNpcapApi:
    def open_for_local_ipv4(self, local_ip: str):
        raise AssertionError(f"Unexpected adapter open for {local_ip}")


class _FakeNpcapHandle:
    datalink = 1

    def __init__(self, packets: list[bytes]) -> None:
        self.packets = packets
        self.closed = False

    def next_packet(self) -> bytes | None:
        return self.packets.pop(0) if self.packets else None

    def close(self) -> None:
        self.closed = True


class NetworkNpcapCaptureTests(unittest.TestCase):
    def test_ethernet_and_vlan_frames_expose_only_ipv4_payload(self) -> None:
        ipv4 = _ipv4_stub()
        ethernet = (b"\x00" * 12) + b"\x08\x00" + ipv4
        vlan = (b"\x00" * 12) + b"\x81\x00\x00\x01\x08\x00" + ipv4

        self.assertEqual(ipv4_packet_from_link_frame(ethernet, 1), ipv4)
        self.assertEqual(ipv4_packet_from_link_frame(vlan, 1), ipv4)

    def test_non_ipv4_and_truncated_link_frames_are_rejected(self) -> None:
        self.assertIsNone(ipv4_packet_from_link_frame(b"\x00" * 13, 1))
        ipv6 = (b"\x00" * 12) + b"\x86\xdd" + (b"\x60" + b"\x00" * 39)
        self.assertIsNone(ipv4_packet_from_link_frame(ipv6, 1))
        self.assertIsNone(ipv4_packet_from_link_frame(b"\x60" + b"\x00" * 39, 12))

    def test_raw_and_null_frames_are_supported(self) -> None:
        ipv4 = _ipv4_stub()
        null_frame = socket.AF_INET.to_bytes(4, "little") + ipv4

        self.assertEqual(ipv4_packet_from_link_frame(ipv4, 12), ipv4)
        self.assertEqual(ipv4_packet_from_link_frame(null_frame, 0), ipv4)

    def test_npcap_reader_forwards_ipv4_packet_to_existing_pipeline(self) -> None:
        ipv4 = _ipv4_stub()
        handle = _FakeNpcapHandle([(b"\x00" * 12) + b"\x08\x00" + ipv4])
        source = NpcapWindowsProtocolSource(lambda: (), npcap_api=_FakeNpcapApi())
        source._sockets["192.0.2.1"] = handle
        source._started = True
        source._last_flow_refresh = time.monotonic()

        with patch.object(source, "_process_raw_packet") as process_packet:
            self.assertIsNone(source.read_item(0.001))

        process_packet.assert_called_once_with(ipv4)
        self.assertEqual(source.diagnostic_snapshot()["npcap_backend_active"], 1)

    def test_helper_falls_back_when_npcap_is_unavailable(self) -> None:
        fallback = object()
        with (
            patch.object(
                capture_helper,
                "NpcapWindowsProtocolSource",
                side_effect=NpcapUnavailableError("missing"),
            ),
            patch.object(capture_helper, "WindowsRawProtocolSource", return_value=fallback),
        ):
            selected = capture_helper._preferred_capture_source(lambda: (), logger=None)

        self.assertIs(selected, fallback)


if __name__ == "__main__":
    unittest.main()
