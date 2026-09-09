from __future__ import annotations

import ctypes
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from app.network.transport import ProtocolTransportItem
from app.network.windows_capture import WindowsRawProtocolSource


_PCAP_ERRBUF_SIZE = 256
_PCAP_NETMASK_UNKNOWN = 0xFFFFFFFF
_DLT_NULL = 0
_DLT_EN10MB = 1
_DLT_RAW = 12
_ETHERTYPE_IPV4 = 0x0800
_VLAN_ETHERTYPES = {0x8100, 0x88A8, 0x9100}
_MAX_PACKETS_PER_HANDLE_PASS = 256


class NpcapUnavailableError(RuntimeError):
    pass


class NpcapCaptureError(RuntimeError):
    pass


class _Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _PcapPacketHeader(ctypes.Structure):
    _fields_ = [
        ("ts", _Timeval),
        ("caplen", ctypes.c_uint32),
        ("len", ctypes.c_uint32),
    ]


class _PcapAddress(ctypes.Structure):
    pass


class _PcapInterface(ctypes.Structure):
    pass


_PcapAddress._fields_ = [
    ("next", ctypes.POINTER(_PcapAddress)),
    ("addr", ctypes.c_void_p),
    ("netmask", ctypes.c_void_p),
    ("broadaddr", ctypes.c_void_p),
    ("dstaddr", ctypes.c_void_p),
]

_PcapInterface._fields_ = [
    ("next", ctypes.POINTER(_PcapInterface)),
    ("name", ctypes.c_char_p),
    ("description", ctypes.c_char_p),
    ("addresses", ctypes.POINTER(_PcapAddress)),
    ("flags", ctypes.c_uint32),
]


class _Sockaddr(ctypes.Structure):
    _fields_ = [("family", ctypes.c_ushort), ("data", ctypes.c_ubyte * 14)]


class _SockaddrIn(ctypes.Structure):
    _fields_ = [
        ("family", ctypes.c_ushort),
        ("port", ctypes.c_ushort),
        ("address", ctypes.c_ubyte * 4),
        ("zero", ctypes.c_ubyte * 8),
    ]


class _BpfProgram(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("instructions", ctypes.c_void_p)]


@dataclass(frozen=True, slots=True)
class _NpcapDevice:
    name: str
    description: str
    ipv4_addresses: tuple[str, ...]


class _NpcapLibrary:
    def __init__(self, library: Any, dll_directory: Any = None) -> None:
        self._library = library
        self._dll_directory = dll_directory
        self._configure_functions()

    @classmethod
    def load(cls) -> _NpcapLibrary:
        if os.name != "nt":
            raise NpcapUnavailableError("Npcap is only available on Windows")
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        candidates = (
            system_root / "System32" / "Npcap" / "wpcap.dll",
            system_root / "System32" / "wpcap.dll",
        )
        failures: list[str] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            dll_directory = None
            try:
                add_dll_directory = getattr(os, "add_dll_directory", None)
                if callable(add_dll_directory):
                    dll_directory = add_dll_directory(str(candidate.parent))
                return cls(ctypes.WinDLL(str(candidate)), dll_directory)
            except (OSError, AttributeError) as exc:
                failures.append(f"{candidate}: {exc}")
                if dll_directory is not None:
                    dll_directory.close()
        detail = "; ".join(failures) if failures else "wpcap.dll not found"
        raise NpcapUnavailableError(detail)

    def _configure_functions(self) -> None:
        library = self._library
        library.pcap_findalldevs.argtypes = [
            ctypes.POINTER(ctypes.POINTER(_PcapInterface)),
            ctypes.c_char_p,
        ]
        library.pcap_findalldevs.restype = ctypes.c_int
        library.pcap_freealldevs.argtypes = [ctypes.POINTER(_PcapInterface)]
        library.pcap_freealldevs.restype = None
        library.pcap_open_live.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
        ]
        library.pcap_open_live.restype = ctypes.c_void_p
        library.pcap_close.argtypes = [ctypes.c_void_p]
        library.pcap_close.restype = None
        library.pcap_setnonblock.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        library.pcap_setnonblock.restype = ctypes.c_int
        library.pcap_datalink.argtypes = [ctypes.c_void_p]
        library.pcap_datalink.restype = ctypes.c_int
        library.pcap_compile.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_BpfProgram),
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_uint32,
        ]
        library.pcap_compile.restype = ctypes.c_int
        library.pcap_setfilter.argtypes = [ctypes.c_void_p, ctypes.POINTER(_BpfProgram)]
        library.pcap_setfilter.restype = ctypes.c_int
        library.pcap_freecode.argtypes = [ctypes.POINTER(_BpfProgram)]
        library.pcap_freecode.restype = None
        library.pcap_next_ex.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(_PcapPacketHeader)),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]
        library.pcap_next_ex.restype = ctypes.c_int
        library.pcap_geterr.argtypes = [ctypes.c_void_p]
        library.pcap_geterr.restype = ctypes.c_char_p

    def devices(self) -> tuple[_NpcapDevice, ...]:
        first = ctypes.POINTER(_PcapInterface)()
        error_buffer = ctypes.create_string_buffer(_PCAP_ERRBUF_SIZE)
        if int(self._library.pcap_findalldevs(ctypes.byref(first), error_buffer)) != 0:
            raise NpcapCaptureError(_decode_error(error_buffer.value))
        devices: list[_NpcapDevice] = []
        try:
            current = first
            while bool(current):
                interface = current.contents
                name = _decode_error(interface.name)
                if name:
                    devices.append(
                        _NpcapDevice(
                            name=name,
                            description=_decode_error(interface.description),
                            ipv4_addresses=_ipv4_addresses(interface.addresses),
                        )
                    )
                current = interface.next
        finally:
            if bool(first):
                self._library.pcap_freealldevs(first)
        return tuple(devices)

    def open_for_local_ipv4(self, local_ip: str) -> _NpcapCaptureHandle:
        device = next(
            (candidate for candidate in self.devices() if local_ip in candidate.ipv4_addresses),
            None,
        )
        if device is None:
            raise NpcapCaptureError(f"No Npcap adapter owns local IPv4 address {local_ip}")

        error_buffer = ctypes.create_string_buffer(_PCAP_ERRBUF_SIZE)
        handle = self._library.pcap_open_live(
            device.name.encode("utf-8"),
            65535,
            0,
            1,
            error_buffer,
        )
        if not handle:
            raise NpcapCaptureError(_decode_error(error_buffer.value))
        try:
            if int(self._library.pcap_setnonblock(handle, 1, error_buffer)) != 0:
                raise NpcapCaptureError(_decode_error(error_buffer.value))
            program = _BpfProgram()
            if int(
                self._library.pcap_compile(
                    handle,
                    ctypes.byref(program),
                    b"tcp",
                    1,
                    _PCAP_NETMASK_UNKNOWN,
                )
            ) != 0:
                raise NpcapCaptureError(self.error_for(handle))
            try:
                if int(self._library.pcap_setfilter(handle, ctypes.byref(program))) != 0:
                    raise NpcapCaptureError(self.error_for(handle))
            finally:
                self._library.pcap_freecode(ctypes.byref(program))
            datalink = int(self._library.pcap_datalink(handle))
            if datalink not in {_DLT_NULL, _DLT_EN10MB, _DLT_RAW}:
                raise NpcapCaptureError(f"Unsupported Npcap data-link type: {datalink}")
            return _NpcapCaptureHandle(self, handle, datalink)
        except Exception:
            self._library.pcap_close(handle)
            raise

    def next_packet(self, handle: int) -> bytes | None:
        header = ctypes.POINTER(_PcapPacketHeader)()
        packet = ctypes.POINTER(ctypes.c_ubyte)()
        result = int(
            self._library.pcap_next_ex(handle, ctypes.byref(header), ctypes.byref(packet))
        )
        if result == 0 or result == -2:
            return None
        if result < 0:
            raise NpcapCaptureError(self.error_for(handle))
        if not bool(header) or not bool(packet):
            raise NpcapCaptureError("Npcap returned an invalid packet")
        return ctypes.string_at(packet, int(header.contents.caplen))

    def close(self, handle: int) -> None:
        self._library.pcap_close(handle)

    def error_for(self, handle: int) -> str:
        return _decode_error(self._library.pcap_geterr(handle)) or "Npcap capture failed"


class _NpcapCaptureHandle:
    def __init__(self, api: Any, handle: int, datalink: int) -> None:
        self.api = api
        self.handle = handle
        self.datalink = int(datalink)
        self._closed = False

    def next_packet(self) -> bytes | None:
        if self._closed:
            return None
        return self.api.next_packet(self.handle)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.api.close(self.handle)


class NpcapWindowsProtocolSource(WindowsRawProtocolSource):
    """Npcap-backed reader that reuses Atlas' strict Dofus flow pipeline."""

    def __init__(
        self,
        window_handles_provider: Callable[[], Iterable[int]],
        *,
        logger=None,
        flow_refresh_seconds: float = 1.0,
        npcap_api: Any = None,
    ) -> None:
        super().__init__(
            window_handles_provider,
            logger=logger,
            flow_refresh_seconds=flow_refresh_seconds,
        )
        self._npcap_api = npcap_api if npcap_api is not None else _NpcapLibrary.load()

    def read_item(self, timeout: float) -> ProtocolTransportItem | None:
        deadline = time.monotonic() + max(0.0, float(timeout))
        while not self._stop_event.is_set():
            queued = self._get_queued_item()
            if queued is not None:
                return queued

            self._refresh_flows()
            with self._state_lock:
                handles = tuple(self._sockets.values())

            processed_packet = False
            for capture_handle in handles:
                for _index in range(_MAX_PACKETS_PER_HANDLE_PASS):
                    frame = capture_handle.next_packet()
                    if frame is None:
                        break
                    processed_packet = True
                    ipv4_packet = ipv4_packet_from_link_frame(frame, capture_handle.datalink)
                    if ipv4_packet is not None:
                        self._process_raw_packet(ipv4_packet)
                    queued = self._get_queued_item()
                    if queued is not None:
                        return queued

            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return None
            if not processed_packet:
                self._stop_event.wait(min(0.005, remaining))
        return None

    def diagnostic_snapshot(self) -> dict[str, int]:
        snapshot = super().diagnostic_snapshot()
        snapshot["npcap_backend_active"] = 1
        return snapshot

    def _open_capture_socket(self, local_ip: str) -> _NpcapCaptureHandle | None:
        try:
            handle = self._npcap_api.open_for_local_ipv4(local_ip)
        except NpcapCaptureError:
            self.logger.exception("Npcap could not open the Dofus network interface.")
            return None
        self.logger.info("Npcap network capture active for one local interface.")
        return handle

    @staticmethod
    def _close_capture_socket(capture_socket: _NpcapCaptureHandle) -> None:
        capture_socket.close()


def ipv4_packet_from_link_frame(frame: bytes, datalink: int) -> bytes | None:
    if datalink == _DLT_RAW:
        return bytes(frame) if frame and frame[0] >> 4 == 4 else None
    if datalink == _DLT_NULL:
        if len(frame) < 5:
            return None
        family = int.from_bytes(frame[:4], "little")
        if family != socket.AF_INET:
            family = int.from_bytes(frame[:4], "big")
        payload = frame[4:]
        return bytes(payload) if family == socket.AF_INET and payload[0] >> 4 == 4 else None
    if datalink != _DLT_EN10MB or len(frame) < 14:
        return None

    offset = 14
    ether_type = int.from_bytes(frame[12:14], "big")
    while ether_type in _VLAN_ETHERTYPES:
        if len(frame) < offset + 4:
            return None
        ether_type = int.from_bytes(frame[offset + 2 : offset + 4], "big")
        offset += 4
    if ether_type != _ETHERTYPE_IPV4 or len(frame) <= offset:
        return None
    payload = frame[offset:]
    return bytes(payload) if payload[0] >> 4 == 4 else None


def _ipv4_addresses(address: ctypes.POINTER(_PcapAddress)) -> tuple[str, ...]:
    found: list[str] = []
    current = address
    while bool(current):
        raw_address = current.contents.addr
        if raw_address:
            family = ctypes.cast(raw_address, ctypes.POINTER(_Sockaddr)).contents.family
            if int(family) == socket.AF_INET:
                sockaddr = ctypes.cast(raw_address, ctypes.POINTER(_SockaddrIn)).contents
                value = socket.inet_ntoa(bytes(sockaddr.address))
                if value not in found:
                    found.append(value)
        current = current.contents.next
    return tuple(found)


def _decode_error(value: bytes | None) -> str:
    if not value:
        return ""
    return bytes(value).decode("utf-8", errors="replace")


__all__ = [
    "NpcapCaptureError",
    "NpcapUnavailableError",
    "NpcapWindowsProtocolSource",
    "ipv4_packet_from_link_frame",
]
