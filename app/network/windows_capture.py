from __future__ import annotations

import os
import queue
import select
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from logging import Logger
from typing import Any, Callable, Iterable

from app.core.admin import current_process_is_admin, process_id_for_window
from app.core.logger import get_runtime_logger
from app.network.transport import CapturedProtocolMessage, ProtocolTransportItem, TransportSessionClosed
from app.network.windows_tcp import WindowsTcpFlow, established_tcp_flows_for_pids
from app.network.wire import ProtobufAnyStreamDecoder, TcpStreamReassembler


_TCP_PROTOCOL = 6
_TCP_FLAG_FIN = 0x01
_TCP_FLAG_RST = 0x04
_IPV4_MORE_FRAGMENTS = 0x2000
_IPV4_FRAGMENT_OFFSET_MASK = 0x1FFF
_PENDING_PACKET_MAX_AGE_SECONDS = 3.0
_PENDING_PACKET_MAX_COUNT = 512
_PENDING_PACKET_MAX_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ParsedIpv4TcpPacket:
    source_ip: str
    destination_ip: str
    source_port: int
    destination_port: int
    sequence: int
    flags: int
    payload: bytes


@dataclass(slots=True)
class _TrackedFlow:
    flow: WindowsTcpFlow
    session_id: str
    server_reassembler: TcpStreamReassembler
    server_decoder: ProtobufAnyStreamDecoder
    client_reassembler: TcpStreamReassembler
    client_decoder: ProtobufAnyStreamDecoder


@dataclass(frozen=True, slots=True)
class _PendingPacket:
    observed_at: float
    packet: ParsedIpv4TcpPacket


class WindowsRawProtocolSource:
    """Passive, local-only IPv4 DOFUS transport for Windows.

    The source uses Windows' built-in SIO_RCVALL capture and the OS TCP owner
    table. It never injects packets and it never stores raw traffic. Only
    in-memory payloads belonging to the supplied Unity window PIDs are
    reassembled, then reduced to protobuf type URL + payload messages.

    Server-to-client and client-to-server streams have independent TCP
    reassemblers/Any decoders. The outbound stream is observation-only: business
    decoders still require reviewed server-to-client messages before progression
    can change. Keeping both directions lets diagnostics prove exact current-build
    request/response aliases even when Atlas attaches to an already-running game.

    Captured messages are *not* trusted business events. A version-matched
    ProtocolMessageDecoder must validate them before progression can change.
    """

    def __init__(
        self,
        window_handles_provider: Callable[[], Iterable[int]],
        *,
        logger: Logger | None = None,
        flow_refresh_seconds: float = 1.0,
    ) -> None:
        self.window_handles_provider = window_handles_provider
        self.logger = logger or get_runtime_logger()
        self.flow_refresh_seconds = max(0.25, float(flow_refresh_seconds))
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._items: queue.Queue[ProtocolTransportItem] = queue.Queue()
        self._sockets: dict[str, Any] = {}
        self._flows: dict[tuple[int, str, int, str, int], _TrackedFlow] = {}
        self._pending_packets: deque[_PendingPacket] = deque()
        self._pending_packet_bytes = 0
        self._replayed_packet_count = 0
        self._raw_packet_count = 0
        self._parsed_tcp_packet_count = 0
        self._matched_packet_count = 0
        self._matched_payload_bytes = 0
        self._reassembled_payload_bytes = 0
        self._framed_message_count = 0
        self._server_to_client_matched_packet_count = 0
        self._server_to_client_matched_payload_bytes = 0
        self._server_to_client_reassembled_payload_bytes = 0
        self._server_to_client_framed_message_count = 0
        self._client_to_server_matched_packet_count = 0
        self._client_to_server_matched_payload_bytes = 0
        self._client_to_server_reassembled_payload_bytes = 0
        self._client_to_server_framed_message_count = 0
        self._session_counter = 0
        self._last_flow_refresh = 0.0
        self._started = False

    @property
    def is_started(self) -> bool:
        with self._state_lock:
            return self._started

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows raw network capture is only available on Windows")
        if not current_process_is_admin():
            raise PermissionError("Windows raw network capture requires administrator privileges")
        with self._state_lock:
            if self._started:
                return
            self._drain_item_queue_unlocked()
            self._reset_diagnostics_unlocked()
            self._stop_event.clear()
            self._started = True
            self._last_flow_refresh = 0.0
        try:
            self._refresh_flows(force=True)
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        self._stop_event.set()
        with self._state_lock:
            sockets = tuple(self._sockets.values())
            self._sockets.clear()
            self._flows.clear()
            self._pending_packets.clear()
            self._pending_packet_bytes = 0
            self._drain_item_queue_unlocked()
            self._started = False
        for capture_socket in sockets:
            self._close_capture_socket(capture_socket)

    def read_item(self, timeout: float) -> ProtocolTransportItem | None:
        deadline = time.monotonic() + max(0.0, float(timeout))
        while not self._stop_event.is_set():
            queued = self._get_queued_item()
            if queued is not None:
                return queued

            self._refresh_flows()
            queued = self._get_queued_item()
            if queued is not None:
                return queued

            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return None
            with self._state_lock:
                sockets = tuple(self._sockets.values())
            if not sockets:
                self._stop_event.wait(min(0.1, remaining))
                continue

            try:
                readable, _, _ = select.select(sockets, (), (), min(0.2, remaining))
            except (OSError, ValueError):
                if self._stop_event.is_set():
                    return None
                self.logger.exception("Windows raw capture select failed.")
                self._stop_event.wait(min(0.1, remaining))
                continue

            for capture_socket in readable:
                try:
                    raw_packet, _ = capture_socket.recvfrom(65535)
                except (BlockingIOError, TimeoutError):
                    continue
                except OSError:
                    if not self._stop_event.is_set():
                        self.logger.exception("Windows raw capture receive failed.")
                    continue
                self._process_raw_packet(raw_packet)
                queued = self._get_queued_item()
                if queued is not None:
                    return queued
        return None

    def _refresh_flows(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_flow_refresh < self.flow_refresh_seconds:
            return

        handles: list[int] = []
        try:
            for raw_handle in self.window_handles_provider() or ():
                try:
                    handle = int(raw_handle)
                except (TypeError, ValueError, OverflowError):
                    continue
                if handle > 0:
                    handles.append(handle)
        except Exception:
            self.logger.exception("Network window handle provider failed.")
            return

        pids = {process_id_for_window(handle) for handle in handles}
        pids.discard(0)
        try:
            current_flows = established_tcp_flows_for_pids(pids)
        except Exception:
            self.logger.exception("Windows TCP owner table lookup failed.")
            return
        self._last_flow_refresh = now
        current_by_key = {flow.key: flow for flow in current_flows}
        added_flow = False

        with self._state_lock:
            previous_keys = set(self._flows)
            current_keys = set(current_by_key)
            for flow_key in current_keys - previous_keys:
                flow = current_by_key[flow_key]
                added_flow = True
                self._session_counter += 1
                session_id = f"tcp:{flow.pid}:{self._session_counter}"
                self._flows[flow_key] = _TrackedFlow(
                    flow=flow,
                    session_id=session_id,
                    server_reassembler=TcpStreamReassembler(),
                    server_decoder=ProtobufAnyStreamDecoder(),
                    client_reassembler=TcpStreamReassembler(),
                    client_decoder=ProtobufAnyStreamDecoder(),
                )
            for flow_key in previous_keys - current_keys:
                tracked = self._flows.pop(flow_key, None)
                if tracked is not None:
                    self._items.put(TransportSessionClosed(session_id=tracked.session_id))

            needed_local_ips = {tracked.flow.local_ip for tracked in self._flows.values()}
            for local_ip in needed_local_ips - set(self._sockets):
                capture_socket = self._open_capture_socket(local_ip)
                if capture_socket is not None:
                    self._sockets[local_ip] = capture_socket
            unused_ips = set(self._sockets) - needed_local_ips
            closing = [self._sockets.pop(local_ip) for local_ip in unused_ips]

        for capture_socket in closing:
            self._close_capture_socket(capture_socket)
        if added_flow:
            self._replay_pending_packets()

    def _process_raw_packet(self, raw_packet: bytes) -> None:
        with self._state_lock:
            self._raw_packet_count += 1
        packet = parse_ipv4_tcp_packet(raw_packet)
        if packet is None:
            return
        with self._state_lock:
            self._parsed_tcp_packet_count += 1
        if not self._handle_packet(packet) and packet.payload:
            self._remember_pending_packet(packet)

    def _remember_pending_packet(self, packet: ParsedIpv4TcpPacket) -> None:
        """Retain a tiny in-memory window while Windows publishes a new PID flow.

        The TCP owner table can lag behind the first packets of a freshly opened
        Dofus connection. Those first packets contain the selected-character and
        quest-journal messages, so dropping them disables tracking after an
        in-client character switch. Packets remain volatile, short-lived and
        bounded; they are replayed only through a subsequently verified PID flow.
        """

        now = time.monotonic()
        with self._state_lock:
            self._expire_pending_packets_unlocked(now)
            size = len(packet.payload)
            if size > _PENDING_PACKET_MAX_BYTES:
                return
            while self._pending_packets and (
                len(self._pending_packets) >= _PENDING_PACKET_MAX_COUNT
                or self._pending_packet_bytes + size > _PENDING_PACKET_MAX_BYTES
            ):
                removed = self._pending_packets.popleft()
                self._pending_packet_bytes -= len(removed.packet.payload)
            self._pending_packets.append(_PendingPacket(now, packet))
            self._pending_packet_bytes += size

    def _replay_pending_packets(self) -> None:
        now = time.monotonic()
        with self._state_lock:
            self._expire_pending_packets_unlocked(now)
            pending = tuple(self._pending_packets)
            self._pending_packets.clear()
            self._pending_packet_bytes = 0

        unmatched: list[_PendingPacket] = []
        replayed = 0
        for row in pending:
            if self._handle_packet(row.packet):
                replayed += 1
            else:
                unmatched.append(row)

        with self._state_lock:
            self._replayed_packet_count += replayed
            for row in unmatched:
                size = len(row.packet.payload)
                if (
                    len(self._pending_packets) >= _PENDING_PACKET_MAX_COUNT
                    or self._pending_packet_bytes + size > _PENDING_PACKET_MAX_BYTES
                ):
                    break
                self._pending_packets.append(row)
                self._pending_packet_bytes += size

    def _expire_pending_packets_unlocked(self, now: float) -> None:
        cutoff = float(now) - _PENDING_PACKET_MAX_AGE_SECONDS
        while self._pending_packets and self._pending_packets[0].observed_at < cutoff:
            removed = self._pending_packets.popleft()
            self._pending_packet_bytes -= len(removed.packet.payload)

    def _handle_packet(self, packet: ParsedIpv4TcpPacket) -> bool:
        with self._state_lock:
            matched_key: tuple[int, str, int, str, int] | None = None
            matched: _TrackedFlow | None = None
            direction = ""
            reassembler: TcpStreamReassembler | None = None
            decoder: ProtobufAnyStreamDecoder | None = None
            for flow_key, tracked in self._flows.items():
                flow = tracked.flow
                if (
                    packet.source_ip == flow.remote_ip
                    and packet.source_port == flow.remote_port
                    and packet.destination_ip == flow.local_ip
                    and packet.destination_port == flow.local_port
                ):
                    matched_key = flow_key
                    matched = tracked
                    direction = "server_to_client"
                    reassembler = tracked.server_reassembler
                    decoder = tracked.server_decoder
                    break
                if (
                    packet.source_ip == flow.local_ip
                    and packet.source_port == flow.local_port
                    and packet.destination_ip == flow.remote_ip
                    and packet.destination_port == flow.remote_port
                ):
                    matched_key = flow_key
                    matched = tracked
                    direction = "client_to_server"
                    reassembler = tracked.client_reassembler
                    decoder = tracked.client_decoder
                    break
            if (
                matched is None
                or matched_key is None
                or reassembler is None
                or decoder is None
                or not direction
            ):
                return False

            self._matched_packet_count += 1
            self._matched_payload_bytes += len(packet.payload)
            if direction == "server_to_client":
                self._server_to_client_matched_packet_count += 1
                self._server_to_client_matched_payload_bytes += len(packet.payload)
            else:
                self._client_to_server_matched_packet_count += 1
                self._client_to_server_matched_payload_bytes += len(packet.payload)

            if packet.flags & _TCP_FLAG_RST:
                self._flows.pop(matched_key, None)
                self._items.put(TransportSessionClosed(session_id=matched.session_id))
                return True

            if packet.payload:
                contiguous = reassembler.feed(packet.sequence, packet.payload)
                if contiguous:
                    self._reassembled_payload_bytes += len(contiguous)
                    framed = decoder.feed(contiguous)
                    self._framed_message_count += len(framed)
                    if direction == "server_to_client":
                        self._server_to_client_reassembled_payload_bytes += len(contiguous)
                        self._server_to_client_framed_message_count += len(framed)
                    else:
                        self._client_to_server_reassembled_payload_bytes += len(contiguous)
                        self._client_to_server_framed_message_count += len(framed)
                    for message in framed:
                        self._items.put(
                            CapturedProtocolMessage(
                                session_id=matched.session_id,
                                type_url=message.type_url,
                                payload=message.payload,
                                direction=direction,
                            )
                        )

            if packet.flags & _TCP_FLAG_FIN:
                self._flows.pop(matched_key, None)
                self._items.put(TransportSessionClosed(session_id=matched.session_id))
            return True

    def diagnostic_snapshot(self) -> dict[str, int]:
        """Return bounded counters only; captured packet contents never leave the helper."""

        with self._state_lock:
            return {
                "npcap_backend_active": 0,
                "capture_socket_count": len(self._sockets),
                "tracked_flow_count": len(self._flows),
                "pending_packet_count": len(self._pending_packets),
                "pending_packet_bytes": self._pending_packet_bytes,
                "replayed_packet_count": self._replayed_packet_count,
                "raw_packet_count": self._raw_packet_count,
                "parsed_tcp_packet_count": self._parsed_tcp_packet_count,
                "matched_packet_count": self._matched_packet_count,
                "matched_payload_bytes": self._matched_payload_bytes,
                "reassembled_payload_bytes": self._reassembled_payload_bytes,
                "framed_message_count": self._framed_message_count,
                "server_to_client_matched_packet_count": (
                    self._server_to_client_matched_packet_count
                ),
                "server_to_client_matched_payload_bytes": (
                    self._server_to_client_matched_payload_bytes
                ),
                "server_to_client_reassembled_payload_bytes": (
                    self._server_to_client_reassembled_payload_bytes
                ),
                "server_to_client_framed_message_count": (
                    self._server_to_client_framed_message_count
                ),
                "client_to_server_matched_packet_count": (
                    self._client_to_server_matched_packet_count
                ),
                "client_to_server_matched_payload_bytes": (
                    self._client_to_server_matched_payload_bytes
                ),
                "client_to_server_reassembled_payload_bytes": (
                    self._client_to_server_reassembled_payload_bytes
                ),
                "client_to_server_framed_message_count": (
                    self._client_to_server_framed_message_count
                ),
            }

    def _reset_diagnostics_unlocked(self) -> None:
        self._pending_packets.clear()
        self._pending_packet_bytes = 0
        self._replayed_packet_count = 0
        self._raw_packet_count = 0
        self._parsed_tcp_packet_count = 0
        self._matched_packet_count = 0
        self._matched_payload_bytes = 0
        self._reassembled_payload_bytes = 0
        self._framed_message_count = 0
        self._server_to_client_matched_packet_count = 0
        self._server_to_client_matched_payload_bytes = 0
        self._server_to_client_reassembled_payload_bytes = 0
        self._server_to_client_framed_message_count = 0
        self._client_to_server_matched_packet_count = 0
        self._client_to_server_matched_payload_bytes = 0
        self._client_to_server_reassembled_payload_bytes = 0
        self._client_to_server_framed_message_count = 0

    def _open_capture_socket(self, local_ip: str) -> socket.socket | None:
        capture_socket: socket.socket | None = None
        try:
            capture_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
            capture_socket.bind((local_ip, 0))
            capture_socket.setblocking(False)
            sio_rcvall = getattr(socket, "SIO_RCVALL")
            rcvall_iplevel = getattr(socket, "RCVALL_IPLEVEL", None)
            if rcvall_iplevel is None:
                rcvall_iplevel = getattr(socket, "RCVALL_ON")
            capture_socket.ioctl(sio_rcvall, rcvall_iplevel)
            self.logger.info("Windows raw network capture active for one local interface.")
            return capture_socket
        except Exception:
            self.logger.exception("Windows raw network capture could not bind a local interface.")
            if capture_socket is not None:
                try:
                    capture_socket.close()
                except OSError:
                    pass
            return None

    @staticmethod
    def _close_capture_socket(capture_socket: socket.socket) -> None:
        try:
            sio_rcvall = getattr(socket, "SIO_RCVALL", None)
            rcvall_off = getattr(socket, "RCVALL_OFF", None)
            if sio_rcvall is not None and rcvall_off is not None:
                capture_socket.ioctl(sio_rcvall, rcvall_off)
        except OSError:
            pass
        try:
            capture_socket.close()
        except OSError:
            pass

    def _get_queued_item(self) -> ProtocolTransportItem | None:
        try:
            return self._items.get_nowait()
        except queue.Empty:
            return None

    def _drain_item_queue_unlocked(self) -> None:
        while True:
            try:
                self._items.get_nowait()
            except queue.Empty:
                return


def parse_ipv4_tcp_packet(raw: bytes) -> ParsedIpv4TcpPacket | None:
    if len(raw) < 40:
        return None
    version = int(raw[0]) >> 4
    header_length = (int(raw[0]) & 0x0F) * 4
    if version != 4 or header_length < 20 or len(raw) < header_length + 20:
        return None
    if int(raw[9]) != _TCP_PROTOCOL:
        return None

    fragmentation = int.from_bytes(raw[6:8], "big")
    if fragmentation & (_IPV4_MORE_FRAGMENTS | _IPV4_FRAGMENT_OFFSET_MASK):
        return None

    total_length = int.from_bytes(raw[2:4], "big")
    packet_end = len(raw) if total_length <= 0 else min(len(raw), total_length)
    tcp_at = header_length
    tcp_header_length = ((int(raw[tcp_at + 12]) >> 4) & 0x0F) * 4
    if tcp_header_length < 20 or tcp_at + tcp_header_length > packet_end:
        return None

    try:
        source_ip = socket.inet_ntoa(raw[12:16])
        destination_ip = socket.inet_ntoa(raw[16:20])
    except OSError:
        return None
    source_port = int.from_bytes(raw[tcp_at : tcp_at + 2], "big")
    destination_port = int.from_bytes(raw[tcp_at + 2 : tcp_at + 4], "big")
    sequence = int.from_bytes(raw[tcp_at + 4 : tcp_at + 8], "big")
    flags = int(raw[tcp_at + 13])
    payload_at = tcp_at + tcp_header_length
    payload = bytes(raw[payload_at:packet_end]) if payload_at < packet_end else b""
    return ParsedIpv4TcpPacket(
        source_ip=source_ip,
        destination_ip=destination_ip,
        source_port=source_port,
        destination_port=destination_port,
        sequence=sequence,
        flags=flags,
        payload=payload,
    )


__all__ = [
    "ParsedIpv4TcpPacket",
    "WindowsRawProtocolSource",
    "parse_ipv4_tcp_packet",
]
