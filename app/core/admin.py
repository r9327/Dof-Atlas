from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from dataclasses import dataclass
from logging import Logger
from typing import Iterable

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20


@dataclass(frozen=True)
class AdminAudit:
    current_admin: bool
    elevated_handles: tuple[int, ...]
    unknown_handles: tuple[int, ...]

    @property
    def ok(self) -> bool:
        return self.current_admin or not self.elevated_handles


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", ctypes.wintypes.DWORD)]


def current_process_is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def process_id_for_window(hwnd: int) -> int:
    if os.name != "nt" or not hwnd:
        return 0
    process_id = ctypes.wintypes.DWORD(0)
    try:
        ctypes.windll.user32.GetWindowThreadProcessId(ctypes.wintypes.HWND(int(hwnd)), ctypes.byref(process_id))
        return int(process_id.value)
    except Exception:
        return 0


def process_is_elevated(pid: int) -> bool | None:
    if os.name != "nt" or pid <= 0:
        return None
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not process:
        return None
    token = ctypes.wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return None
        elevation = TOKEN_ELEVATION()
        returned = ctypes.wintypes.DWORD(0)
        if not advapi32.GetTokenInformation(
            token,
            TOKEN_ELEVATION_CLASS,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(returned),
        ):
            return None
        return bool(elevation.TokenIsElevated)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


def audit_client_admin_rights(handles: Iterable[int], logger: Logger) -> AdminAudit:
    current_admin = current_process_is_admin()
    elevated: list[int] = []
    unknown: list[int] = []
    for raw_handle in handles:
        try:
            hwnd = int(raw_handle)
        except (TypeError, ValueError):
            continue
        if hwnd <= 0:
            continue
        pid = process_id_for_window(hwnd)
        elevated_state = process_is_elevated(pid)
        if elevated_state is True:
            elevated.append(hwnd)
        elif elevated_state is None:
            unknown.append(hwnd)
    audit = AdminAudit(
        current_admin=current_admin,
        elevated_handles=tuple(elevated),
        unknown_handles=tuple(unknown),
    )
    if not audit.ok:
        logger.warning(
            "Droits insuffisants: Atlas non admin mais fenetres Dofus admin detectees handles=%s",
            list(audit.elevated_handles),
        )
    if audit.unknown_handles:
        logger.debug("Droits processus inconnus pour handles=%s", list(audit.unknown_handles))
    return audit

