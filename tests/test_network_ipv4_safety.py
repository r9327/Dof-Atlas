from __future__ import annotations

import socket
import unittest

from app.network.windows_capture import parse_ipv4_tcp_packet


def ipv4_tcp_packet(*, fragmentation: int = 0, payload: bytes = b"hello") -> bytes:
    ip_header_len = 20
    tcp_header_len = 20
    total_len = ip_header_len + tcp_header_len + len(payload)
    ip = bytearray(ip_header_len)
    ip[0] = 0x45
    ip[2:4] = total_len.to_bytes(2, "big")
    ip[6:8] = int(fragmentation).to_bytes(2, "big")
    ip[8] = 64
    ip[9] = 6
    ip[12:16] = socket.inet_aton("203.0.113.10")
    ip[16:20] = socket.inet_aton("192.0.2.4")
    tcp = bytearray(tcp_header_len)
    tcp[0:2] = (5555).to_bytes(2, "big")
    tcp[2:4] = (49152).to_bytes(2, "big")
    tcp[4:8] = (12345).to_bytes(4, "big")
    tcp[12] = 5 << 4
    tcp[13] = 0x18
    return bytes(ip + tcp + payload)


class NetworkIpv4SafetyTests(unittest.TestCase):
    def test_unfragmented_tcp_packet_is_accepted(self) -> None:
        self.assertIsNotNone(parse_ipv4_tcp_packet(ipv4_tcp_packet()))

    def test_more_fragments_flag_is_rejected(self) -> None:
        self.assertIsNone(parse_ipv4_tcp_packet(ipv4_tcp_packet(fragmentation=0x2000)))

    def test_nonzero_fragment_offset_is_rejected(self) -> None:
        self.assertIsNone(parse_ipv4_tcp_packet(ipv4_tcp_packet(fragmentation=0x0001)))

    def test_dont_fragment_flag_is_allowed(self) -> None:
        self.assertIsNotNone(parse_ipv4_tcp_packet(ipv4_tcp_packet(fragmentation=0x4000)))


if __name__ == "__main__":
    unittest.main()
