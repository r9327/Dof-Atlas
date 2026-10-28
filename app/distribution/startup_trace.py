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
        fields["process_cpu_ms"] = round(time.process_time_ns() / 1_000_000, 3)
        rss = _windows_rss_bytes()
        if rss is not None:
            fields["process_rss_bytes"] = rss
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
