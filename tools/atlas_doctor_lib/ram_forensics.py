"""Opt-in Doctor Python heap profiler for real Atlas Qt navigation.

tracemalloc only observes *tracked Python allocations*. It cannot apportion
PySide6/C++/Qt allocations, DLL images, GPU buffers or shared working sets.
Keep this mode separate from ordinary timing and memory certification.
"""
from __future__ import annotations

import ctypes
import os
import tracemalloc
from pathlib import Path
from typing import Any

MAX_CHECKPOINTS = 12
TOP_SITES = 18
MB = 1024 * 1024


def private_windows_memory() -> dict[str, object]:
    """Read process private committed bytes without claiming they are RSS."""
    if os.name != "nt":
        return {"status": "UNAVAILABLE", "reason": "WINDOWS_ONLY"}
    try:
        from ctypes import wintypes

        class MemoryCountersEx(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(MemoryCountersEx), wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = MemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return {"status": "UNAVAILABLE", "reason": "GET_PROCESS_MEMORY_INFO_FAILED"}
        return {
            "status": "OBSERVED",
            "private_commit_mib": round(counters.PrivateUsage / MB, 3),
            "working_set_mib": round(counters.WorkingSetSize / MB, 3),
        }
    except (OSError, AttributeError, ValueError, TypeError) as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__}


def _source_name(path: str, root: Path) -> str:
    try:
        located = Path(path).resolve(strict=False)
        relative = located.relative_to(root.resolve(strict=False))
        return relative.as_posix()
    except (OSError, ValueError):
        # Exclude untrusted local paths from diagnostic artifacts.
        return "<stdlib-or-third-party>"


class RamForensics:
    """Small, separate-run Python retained-allocation checkpoints for Doctor."""

    def __init__(self, root: Path, *, max_checkpoints: int = MAX_CHECKPOINTS):
        self.root = Path(root)
        self.max_checkpoints = max(1, min(MAX_CHECKPOINTS, int(max_checkpoints)))
        self.entries: list[dict[str, Any]] = []
        self._previous = None
        self._initial = None
        self._active = False

    def start(self) -> None:
        if tracemalloc.is_tracing():
            raise RuntimeError("TRACEMALLOC_ALREADY_ACTIVE")
        tracemalloc.start(8)
        self._active = True

    def capture(self, label: str) -> None:
        if not self._active or len(self.entries) >= self.max_checkpoints:
            return
        # This is intentionally AFTER the official RSS checkpoint.
        snapshot = tracemalloc.take_snapshot()
        current, peak = tracemalloc.get_traced_memory()
        rows: list[dict[str, Any]] = []
        by_file: dict[str, list[int]] = {}
        if self._previous is not None:
            for diff in snapshot.compare_to(self._previous, "filename"):
                file = _source_name(diff.traceback[0].filename, self.root)
                if file == "<stdlib-or-third-party>":
                    continue
                amount = by_file.setdefault(file, [0, 0])
                amount[0] += int(diff.size_diff)
                amount[1] += int(diff.count_diff)
            rows = [
                {"source": name, "delta_mib": round(sizes[0] / MB, 4),
                 "delta_blocks": sizes[1]}
                for name, sizes in sorted(
                    by_file.items(), key=lambda item: (-item[1][0], item[0])
                )[:TOP_SITES]
            ]
        absolute: list[dict[str, Any]] = []
        for item in snapshot.statistics("filename"):
            source = _source_name(item.traceback[0].filename, self.root)
            if source == "<stdlib-or-third-party>":
                continue
            absolute.append({
                "source": source,
                "traced_mib": round(item.size / MB, 4),
                "blocks": item.count,
            })
        absolute.sort(key=lambda item: (-item["traced_mib"], item["source"]))
        # Location is allocation site, not the object's actual owner.
        # Tool harness allocations must not be presented as app memory.
        top_lines: list[dict[str, Any]] = []
        for statistic in snapshot.statistics("lineno"):
            frame = statistic.traceback[0]
            source = _source_name(frame.filename, self.root)
            if source == "<stdlib-or-third-party>":
                continue
            top_lines.append({
                "source": source,
                "line": int(frame.lineno),
                "traced_mib": round(statistic.size / MB, 4),
                "blocks": statistic.count,
                "is_benchmark_harness": source.startswith("tools/"),
            })
        top_lines.sort(key=lambda item: (-item["traced_mib"], item["source"], item["line"]))
        app_traced_mib = round(sum(
            row["traced_mib"] for row in absolute
            if row["source"].startswith("app/") or row["source"] == "main.py"
        ), 4)
        harness_traced_mib = round(sum(
            row["traced_mib"] for row in absolute
            if row["source"].startswith("tools/")
        ), 4)
        entry: dict[str, Any] = {
            "label": str(label),
            "tracked_python_heap_mib": round(current / MB, 3),
            "tracked_python_peak_mib": round(peak / MB, 3),
            "tracked_python_blocks": len(snapshot.traces),
            "top_increased_sources_since_previous_checkpoint": rows,
            "top_traced_sources_now": absolute[:TOP_SITES],
            "top_traced_lines_now": top_lines[:TOP_SITES],
            "app_source_traced_mib": app_traced_mib,
            "benchmark_harness_traced_mib": harness_traced_mib,
            "windows_process": private_windows_memory(),
        }
        self.entries.append(entry)
        if self._initial is None:
            self._initial = snapshot
        self._previous = snapshot

    def finish(self) -> dict[str, Any]:
        self._active = False
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        if not self.entries:
            return {"status": "BLOCKED", "reason": "NO_PYTHON_HEAP_CHECKPOINTS"}
        first, last = self.entries[0], self.entries[-1]
        return {
            "status": "PARTIAL_PYTHON_ONLY",
            "method": "tracemalloc_explicit_opt_in_not_native_heap",
            "checkpoints": self.entries,
            "python_heap_delta_mib": round(
                last["tracked_python_heap_mib"] - first["tracked_python_heap_mib"], 3
            ),
            "limits": [
                "Python allocation traces include profiling overhead and instrumentation",
                "Tools/benchmark allocations are diagnostic overhead, not Atlas production allocations",
                "Source locations show allocation sites, not retained owner references",
                "Qt/C++ native allocations, pixmap buffers and GPU are not included",
                "Working Set and private commit are distinct measurements, not additive",
                "No timings from this profiled run are accepted as speed regressions",
                "Positive Python delta alone does not prove a leak or ownership",
            ],
        }


__all__ = ["RamForensics", "private_windows_memory"]
