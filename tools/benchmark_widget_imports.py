"""Cold-process import-time/working-set probe for Encyclopedia widgets.

Run one mode per fresh interpreter; inspect only process-local imports.
This is NOT a Phase 8 process-tree RAM/UX benchmark.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))


def current_rss_mb() -> float:
    if os.name == "nt":
        # Task-manager working set / resident bytes, not virtual address space.
        import ctypes
        from ctypes import wintypes

        class MEMORY_COUNTERS(ctypes.Structure):
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
            ]

        counter = MEMORY_COUNTERS()
        counter.cb = ctypes.sizeof(counter)
        func = ctypes.windll.psapi.GetProcessMemoryInfo
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not func(handle, ctypes.byref(counter), counter.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return round(counter.WorkingSetSize / (1024 * 1024), 3)
    # Linux/macos fallback for local deterministic quick smoke only.
    try:
        import resource
        scale = 1024 if sys.platform.startswith("linux") else 1024 * 1024
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / scale, 3)
    except ImportError:
        return 0.0


def probe(mode: str) -> dict[str, object]:
    before_modules = set(sys.modules)
    before_rss = current_rss_mb()
    start = time.perf_counter()
    if mode == "package":
        importlib.import_module("app.modules.encyclopedia.widgets")
    elif mode == "submodule":
        importlib.import_module("app.modules.encyclopedia.widgets.guide_card")
    elif mode == "public_api":
        module = importlib.import_module("app.modules.encyclopedia.widgets")
        getattr(module, "GuideCardDelegate")
    else:
        raise ValueError(mode)
    milliseconds = (time.perf_counter() - start) * 1000
    after_rss = current_rss_mb()
    added = set(sys.modules) - before_modules
    widgets = sorted(x for x in added if x.startswith("app.modules.encyclopedia.widgets."))
    return {
        "mode": mode, "elapsed_ms": round(milliseconds, 3),
        "rss_before_mb": before_rss, "rss_after_mb": after_rss,
        "rss_delta_mb": round(after_rss - before_rss, 3),
        "widget_submodules_loaded": len(widgets),
        "all_modules_added": len(added),
        "sample_loaded_widgets": widgets[:10],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["package", "submodule", "public_api"], required=True)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=ROOT).strip()
    result = {"git_head": sha, **probe(a.mode)}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
