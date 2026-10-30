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
        # Filename/lineno attribution only needs the allocation site. One
        # frame avoids collecting unused traceback stacks for every block.
        tracemalloc.start(1)
        self._active = True

    def capture(self, label: str) -> None:
        if not self._active or len(self.entries) >= self.max_checkpoints:
            return
        # This is intentionally AFTER the official RSS checkpoint.
        snapshot = tracemalloc.take_snapshot()
        current, peak = tracemalloc.get_traced_memory()
        # One grouped pass replaces three whole-snapshot sorts: filename,
        # previous-vs-current compare and lineno. Only aggregated numbers
        # survive this call, not multi-MiB Snapshot traceback objects.
        per_file: dict[str, list[int]] = {}
        top_lines: list[dict[str, Any]] = []
        for statistic in snapshot.statistics("lineno"):
            frame = statistic.traceback[0]
            source = _source_name(frame.filename, self.root)
            if source == "<stdlib-or-third-party>":
                continue
            totals = per_file.setdefault(source, [0, 0])
            totals[0] += int(statistic.size)
            totals[1] += int(statistic.count)
            top_lines.append({
                "source": source,
                "line": int(frame.lineno),
                "traced_mib": round(statistic.size / MB, 4),
                "blocks": statistic.count,
                "is_benchmark_harness": source.startswith("tools/"),
            })
        absolute = [
            {"source": name, "traced_mib": round(amounts[0] / MB, 4),
             "blocks": amounts[1]}
            for name, amounts in per_file.items()
        ]
        absolute.sort(key=lambda item: (-item["traced_mib"], item["source"]))
        top_lines.sort(key=lambda item: (-item["traced_mib"], item["source"], item["line"]))
        rows: list[dict[str, Any]] = []
        released: list[dict[str, Any]] = []
        if self._previous is not None:
            # A file missing from the current snapshot may have released its
            # entire retained heap; keep negative deltas instead of omitting it.
            for name in sorted(set(per_file) | set(self._previous)):
                size, blocks = per_file.get(name, [0, 0])
                prior_size, prior_blocks = self._previous.get(name, [0, 0])
                delta_size = size - prior_size
                delta_blocks = blocks - prior_blocks
                if delta_size or delta_blocks:
                    item = {
                        "source": name, "delta_mib": round(delta_size / MB, 4),
                        "delta_blocks": delta_blocks,
                    }
                    if delta_size < 0 or (delta_size == 0 and delta_blocks < 0):
                        released.append(item)
                    else:
                        rows.append(item)
            rows.sort(key=lambda item: (-item["delta_mib"], item["source"]))
            released.sort(key=lambda item: (item["delta_mib"], item["source"]))
            rows = rows[:TOP_SITES]
            released = released[:TOP_SITES]
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
            "top_decreased_sources_since_previous_checkpoint": released,
            "top_traced_sources_now": absolute[:TOP_SITES],
            "top_traced_lines_now": top_lines[:TOP_SITES],
            "app_top_sources_traced_mib": app_traced_mib,
            "benchmark_top_sources_traced_mib": harness_traced_mib,
            "windows_process": private_windows_memory(),
        }
        self.entries.append(entry)
        if self._initial is None:
            self._initial = per_file
        self._previous = per_file

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
