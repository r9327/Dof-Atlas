from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import socket
import struct
from dataclasses import dataclass
from typing import Iterable


_AF_INET = 2
_TCP_TABLE_OWNER_PID_ALL = 5
_NO_ERROR = 0
_ERROR_INSUFFICIENT_BUFFER = 122
_MIB_TCP_STATE_ESTAB = 5


@dataclass(frozen=True, slots=True)
class WindowsTcpFlow:
    pid: int
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int

    @property
    def key(self) -> tuple[int, str, int, str, int]:
        return (
            self.pid,
            self.local_ip,
            self.local_port,
            self.remote_ip,
            self.remote_port,
        )


class _MibTcpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("dwState", ctypes.wintypes.DWORD),
        ("dwLocalAddr", ctypes.wintypes.DWORD),
        ("dwLocalPort", ctypes.wintypes.DWORD),
        ("dwRemoteAddr", ctypes.wintypes.DWORD),
        ("dwRemotePort", ctypes.wintypes.DWORD),
        ("dwOwningPid", ctypes.wintypes.DWORD),
    ]


def established_tcp_flows_for_pids(pids: Iterable[int]) -> tuple[WindowsTcpFlow, ...]:
    """Return established IPv4 TCP flows owned by the supplied processes.

    The Windows table is queried directly through iphlpapi so the network layer
    does not need psutil or another runtime dependency. Invalid caller entries
    are ignored rather than turning a transient window/PID refresh into a reader
    failure.
    """

    wanted: set[int] = set()
    candidates = () if pids is None else pids
    try:
        iterator = iter(candidates)
    except TypeError:
        iterator = iter(())
    for raw_pid in iterator:
        try:
            pid = int(raw_pid)
        except (TypeError, ValueError, OverflowError):
            continue
        if pid > 0:
            wanted.add(pid)
    if os.name != "nt" or not wanted:
        return ()

    iphlpapi = ctypes.WinDLL("iphlpapi.dll")
    get_table = iphlpapi.GetExtendedTcpTable
    get_table.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.DWORD),
        ctypes.wintypes.BOOL,
        ctypes.wintypes.ULONG,
        ctypes.c_int,
        ctypes.wintypes.ULONG,
    ]
    get_table.restype = ctypes.wintypes.DWORD

    size = ctypes.wintypes.DWORD(0)
    status = int(
        get_table(
            None,
            ctypes.byref(size),
            False,
            _AF_INET,
            _TCP_TABLE_OWNER_PID_ALL,
            0,
        )
    )
    if status not in (_ERROR_INSUFFICIENT_BUFFER, _NO_ERROR) or size.value <= 0:
        return ()

    buffer = ctypes.create_string_buffer(int(size.value))
    status = int(
        get_table(
            ctypes.byref(buffer),
            ctypes.byref(size),
            False,
            _AF_INET,
            _TCP_TABLE_OWNER_PID_ALL,
            0,
        )
    )
    if status != _NO_ERROR:
        return ()

    count = int(ctypes.cast(buffer, ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value)
    row_size = ctypes.sizeof(_MibTcpRowOwnerPid)
    row_offset = ctypes.sizeof(ctypes.wintypes.DWORD)
    flows: list[WindowsTcpFlow] = []
    for index in range(count):
        offset = row_offset + (index * row_size)
        if offset + row_size > int(size.value):
            break
        row = _MibTcpRowOwnerPid.from_buffer_copy(buffer.raw, offset)
        pid = int(row.dwOwningPid)
        if pid not in wanted or int(row.dwState) != _MIB_TCP_STATE_ESTAB:
            continue
        local_ip = _ipv4_from_dword(row.dwLocalAddr)
        remote_ip = _ipv4_from_dword(row.dwRemoteAddr)
        local_port = _port_from_dword(row.dwLocalPort)
        remote_port = _port_from_dword(row.dwRemotePort)
        if not local_ip or not remote_ip or local_port <= 0 or remote_port <= 0:
            continue
        flows.append(
            WindowsTcpFlow(
                pid=pid,
                local_ip=local_ip,
                local_port=local_port,
                remote_ip=remote_ip,
                remote_port=remote_port,
            )
        )
    return tuple(flows)


def _ipv4_from_dword(value: int) -> str:
    try:
        return socket.inet_ntoa(struct.pack("<L", int(value) & 0xFFFFFFFF))
    except (OSError, struct.error, TypeError, ValueError, OverflowError):
        return ""


def _port_from_dword(value: int) -> int:
    try:
        return int(socket.ntohs(int(value) & 0xFFFF))
    except (OSError, OverflowError, TypeError, ValueError):
        return 0


__all__ = ["WindowsTcpFlow", "established_tcp_flows_for_pids"]
