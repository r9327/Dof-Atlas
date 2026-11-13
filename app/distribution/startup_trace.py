"""Opt-in, process-correlated startup checkpoints; never part of app health."""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from pathlib import Path

_PROFILE_FLAG = "DOFUS_ATLAS_STARTUP_PROFILE"
_PROFILE_FILE = "DOFUS_ATLAS_STARTUP_PROFILE_FILE"
_SESSION = "DOFUS_ATLAS_STARTUP_SESSION"
_MAX_LOG_BYTES = 2 * 1024 * 1024


def _windows_rss_bytes() -> int | None:
    """Best-effort current-process working set, only when profiling on Windows."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        info = MemoryCounters()
        info.cb = ctypes.sizeof(info)
        current_process = ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype = ctypes.c_void_p
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        get_info.restype = ctypes.c_int
        if get_info(current_process(), ctypes.byref(info), ctypes.sizeof(info)):
            return int(info.WorkingSetSize)
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return None


def _windows_process_tree_rss() -> tuple[int, int] | None:
    """Sample launcher and live descendants; unavailable is not zero.

    Profiling-only Win32 snapshot, never part of update/health decisions.
    Returns None if any visible descendant cannot be read reliably.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        class MemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.Process32FirstW.restype = wintypes.BOOL
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.Process32NextW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == ctypes.c_void_p(-1).value or not snapshot:
            return None
        parents: dict[int, int] = {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
                return None
            while True:
                parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            kernel.CloseHandle(snapshot)

        tracked = {os.getpid()}
        if os.getpid() not in parents:
            return None
        while True:
            descendants = {pid for pid, parent in parents.items() if parent in tracked}
            if descendants <= tracked:
                break
            tracked.update(descendants)
        total = 0
        for pid in tracked:
            handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
            if not handle:
                return None
            try:
                info = MemoryCounters()
                info.cb = ctypes.sizeof(info)
                if not psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(info), ctypes.sizeof(info),
                ):
                    return None
                total += int(info.WorkingSetSize)
            finally:
                kernel.CloseHandle(handle)
        return total, len(tracked)
    except (AttributeError, OSError, TypeError, ValueError, OverflowError):
        return None


def _windows_process_age_ms() -> float | None:
    """Approximate time already spent in the frozen launcher bootstrap.

    The Windows kernel records process creation before PyInstaller and Python
    imports. Use the same Windows FILETIME clock for both timestamps; a
    missing API or clock discontinuity means no sample, never a zero.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
        kernel.GetSystemTimeAsFileTime.restype = None

        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not kernel.GetProcessTimes(
            kernel.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(exited),
            ctypes.byref(kernel_time), ctypes.byref(user_time),
        ):
            return None
        now = wintypes.FILETIME()
        kernel.GetSystemTimeAsFileTime(ctypes.byref(now))
        as_ticks = lambda stamp: (stamp.dwHighDateTime << 32) | stamp.dwLowDateTime
        age_ms = (as_ticks(now) - as_ticks(created)) / 10_000
        return round(age_ms, 3) if 0 <= age_ms <= 30 * 60 * 1000 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def record_startup_event(event: str, **metrics: int | float) -> None:
    """Append one small JSONL event, or silently skip when profiling is disabled.

    Only numeric metrics are accepted: never log paths, tokens or user data.
    The performance trace is diagnostic and must not affect normal startup.
    """
    if os.environ.get(_PROFILE_FLAG) != "1":
        return
    try:
        session = os.environ.get(_SESSION)
        if not session:
            session = uuid.uuid4().hex
            os.environ[_SESSION] = session
        filename = os.environ.get(_PROFILE_FILE)
        if not filename:
            home = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
            filename = str(Path(home) / "DofusAtlas" / "logs" / "startup_profile.jsonl")
        target = Path(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size >= _MAX_LOG_BYTES:
            return
        fields: dict[str, int | float] = {}
        for key, value in metrics.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            try:
                if math.isfinite(value):
                    fields[key] = value
            except (ValueError, OverflowError):
                continue
        # Only the first launcher checkpoint estimates the native EXE
        # bootstrap before Python. It is not a fabricated double-click time.
        if event == "launcher_entry":
            process_age = _windows_process_age_ms()
            if process_age is not None:
                fields["process_age_ms"] = process_age
        fields["process_cpu_ms"] = round(time.process_time_ns() / 1_000_000, 3)
        rss = _windows_rss_bytes()
        if rss is not None:
            fields["process_rss_bytes"] = rss
        # A process-tree snapshot is expensive: take it only for two measured
        # handoff checkpoints, and never when profiling is off.
        if event in {"app_health_ack", "app_home_ack"}:
            tree = _windows_process_tree_rss()
            if tree is not None:
                fields["process_tree_rss_bytes"] = tree[0]
                fields["process_tree_count"] = tree[1]
        line = json.dumps({"session": session, "event": event, "t_ns": time.perf_counter_ns(),
                           "pid": os.getpid(), **fields}, separators=(",", ":")) + "\n"
        if len(line) > 1024:
            return
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        fd = os.open(target, flags, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except (OSError, ValueError):
        # Profiling must never turn a working app or a rollback into a failure.
        return
