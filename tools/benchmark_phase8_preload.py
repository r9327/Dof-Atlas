from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

ROOT = Path.cwd().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

import main as app_main
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB


TERMINAL_PRELOAD_STATES = {"READY", "FAILED"}


def milliseconds(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    return completed.stdout.strip()


def memory_mb() -> tuple[float | None, float | None]:
    if os.name == "nt":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
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

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        if not get_process_memory_info(
            get_current_process(),
            ctypes.byref(counters),
            counters.cb,
        ):
            return None, None
        scale = 1024.0 * 1024.0
        return (
            round(counters.WorkingSetSize / scale, 2),
            round(counters.PeakWorkingSetSize / scale, 2),
        )

    statm = Path("/proc/self/statm")
    if statm.is_file():
        try:
            resident_pages = int(statm.read_text(encoding="ascii").split()[1])
            rss = round(resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0), 2)
            return rss, None
        except (OSError, ValueError, IndexError):
            return None, None
    return None, None


def pump(app: QApplication, seconds: float) -> None:
    deadline = time.perf_counter() + max(0.0, seconds)
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def wait_until(
    app: QApplication,
    predicate: Callable[[], bool],
    *,
    timeout: float,
    label: str,
    poll_seconds: float = 0.005,
) -> tuple[float, float | None]:
    """Pump Qt without making the benchmark itself a memory workload.

    memory_mb() already exposes Windows' cumulative PeakWorkingSetSize at the
    explicit measurement points below. Sampling it every 5 ms during a 30+
    second cache warmup only raises the measured process' own Python heap.
    """

    started = time.perf_counter()
    deadline = started + timeout
    interval = max(0.001, float(poll_seconds))
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return milliseconds(started), None
        time.sleep(interval)
    raise RuntimeError(f"Timeout while waiting for {label} ({timeout:.1f}s).")


def page_loaded(window: Any, name: str) -> bool:
    factories = getattr(window, "page_factories", {})
    if isinstance(factories, dict) and name in factories:
        return False
    page = getattr(window, "page_widgets", {}).get(name)
    if page is None:
        return False
    ready = getattr(window, "page_ready_for_navigation", None)
    if callable(ready):
        try:
            return bool(ready(page))
        except Exception:
            return False
    page_ready = getattr(page, "is_navigation_ready", None)
    if callable(page_ready):
        try:
            return bool(page_ready())
        except Exception:
            return False
    return True


def current_tab_label(page: Any) -> str:
    labels = getattr(page, "tab_labels", None)
    tabs = getattr(page, "tabs", None)
    if not callable(labels) or tabs is None:
        return ""
    try:
        values = list(labels())
        index = int(tabs.currentIndex())
    except Exception:
        return ""
    if 0 <= index < len(values):
        return str(values[index])
    return ""


def encyclopedia_ready(window: Any, label: str) -> bool:
    if not page_loaded(window, "Quetes"):
        return False
    if str(getattr(window, "pending_encyclopedia_tab", "") or ""):
        return False
    page = getattr(window, "page_widgets", {}).get("Quetes")
    if page is None or current_tab_label(page) != label:
        return False
    if label == QUESTS_TAB:
        return getattr(page, "quest_page", None) is not None
    if label == ACHIEVEMENTS_TAB:
        if bool(getattr(page, "_achievement_ready", False)):
            return True
        getter = getattr(page, "get_achievements_view", None)
        if callable(getter):
            try:
                view = getter()
            except Exception:
                return False
            return view is not None and bool(getattr(view, "_runtime_ready", True))
        return True
    if label == GUIDES_TAB:
        if bool(getattr(page, "_guide_runtime_ready", False)):
            return True
        view = getattr(page, "guides_view", None)
        return view is not None and bool(getattr(view, "_runtime_ready", True))
    return True


def open_encyclopedia(app: QApplication, window: Any, label: str) -> float:
    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    wait_until(
        app,
        lambda: encyclopedia_ready(window, label),
        timeout=60.0,
        label=f"Encyclopedia {label}",
    )
    return milliseconds(started)


def open_page(app: QApplication, window: Any, name: str, *, timeout: float = 45.0) -> float:
    started = time.perf_counter()
    window.show_page(name)
    wait_until(
        app,
        lambda: page_loaded(window, name),
        timeout=timeout,
        label=name,
    )
    return milliseconds(started)


def preload_terminal(window: Any) -> bool:
    states = getattr(window, "preload_states", None)
    if not isinstance(states, dict) or not states:
        return True
    return all(str(state) in TERMINAL_PRELOAD_STATES for state in states.values())


def preload_state_snapshot(window: Any) -> dict[str, str]:
    states = getattr(window, "preload_states", None)
    if not isinstance(states, dict):
        return {}
    return {str(key): str(value) for key, value in states.items()}


def measure() -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])

    startup_started = time.perf_counter()
    window = app_main.AtlasWindow()
    constructor_ms = milliseconds(startup_started)
    window.show()
    app.processEvents()
    first_paint_ms = milliseconds(startup_started)
    pump(app, 0.25)
    startup_stabilized_ms = milliseconds(startup_started)
    startup_rss_mb, startup_peak_rss_mb = memory_mb()

    preload_states_before = preload_state_snapshot(window)
    preload_duration_ms, _preload_peak = wait_until(
        app,
        lambda: preload_terminal(window),
        timeout=90.0,
        label="functional preload",
        poll_seconds=0.02,
    )
    preload_completed_from_constructor_ms = milliseconds(startup_started)
    preload_states_after = preload_state_snapshot(window)
    pump(app, 0.05)
    rss_after_preload_mb, peak_after_preload_mb = memory_mb()

    quests_open_ms = open_encyclopedia(app, window, QUESTS_TAB)
    achievements_open_ms = open_encyclopedia(app, window, ACHIEVEMENTS_TAB)
    guide_open_ms = open_encyclopedia(app, window, GUIDES_TAB)
    craft_open_ms = open_page(app, window, "Craft")
    equipment_open_ms = open_page(app, window, "Equipement", timeout=60.0)

    pump(app, 0.1)
    final_rss_mb, final_peak_rss_mb = memory_mb()

    shutdown = getattr(window, "_shutdown_background_services", None)
    if callable(shutdown):
        shutdown()
    window.hide()
    window.deleteLater()
    app.processEvents()

    peaks = [
        value
        for value in (
            startup_peak_rss_mb,
            peak_after_preload_mb,
            final_peak_rss_mb,
        )
        if value is not None
    ]

    return {
        "git_head": git_head(),
        "startup_constructor_ms": constructor_ms,
        "first_window_paint_ms": first_paint_ms,
        "startup_stabilized_ms": startup_stabilized_ms,
        "startup_stabilized_rss_mb": startup_rss_mb,
        "preload_wait_from_stabilized_ms": preload_duration_ms,
        "preload_completed_from_constructor_ms": preload_completed_from_constructor_ms,
        "preload_states_before": preload_states_before,
        "preload_states_after": preload_states_after,
        "rss_after_preload_mb": rss_after_preload_mb,
        "peak_rss_mb": round(max(peaks), 2) if peaks else None,
        "quests_open_ms": quests_open_ms,
        "achievements_open_ms": achievements_open_ms,
        "guide_open_ms": guide_open_ms,
        "craft_open_ms": craft_open_ms,
        "equipment_open_ms": equipment_open_ms,
        "rss_after_first_accesses_mb": final_rss_mb,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Comparable Phase 8 preload benchmark")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "schema_version": 1,
        "environment": {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        },
        "metrics": measure(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
