from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

ROOT = Path.cwd().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from PySide6.QtWidgets import QApplication

from benchmark_phase8_preload import (
    app_main,
    encyclopedia_ready,
    git_head,
    memory_mb,
    open_encyclopedia,
    open_page,
    preload_terminal,
    pump,
    wait_until,
)
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB

_MB = 1024.0 * 1024.0


@dataclass(frozen=True)
class ProcessRow:
    pid: int
    parent_pid: int
    name: str


def _windows_process_rows() -> list[ProcessRow]:
    if os.name != "nt":
        return []

    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    MAX_PATH = 260

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * MAX_PATH),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot_fn = kernel32.CreateToolhelp32Snapshot
    snapshot_fn.argtypes = [wintypes.DWORD, wintypes.DWORD]
    snapshot_fn.restype = wintypes.HANDLE
    first_fn = kernel32.Process32FirstW
    first_fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    first_fn.restype = wintypes.BOOL
    next_fn = kernel32.Process32NextW
    next_fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    next_fn.restype = wintypes.BOOL
    close_fn = kernel32.CloseHandle
    close_fn.argtypes = [wintypes.HANDLE]
    close_fn.restype = wintypes.BOOL

    handle = snapshot_fn(TH32CS_SNAPPROCESS, 0)
    if not handle or int(handle) == int(INVALID_HANDLE_VALUE or -1):
        return []

    rows: list[ProcessRow] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not first_fn(handle, ctypes.byref(entry)):
            return []
        while True:
            rows.append(
                ProcessRow(
                    pid=int(entry.th32ProcessID),
                    parent_pid=int(entry.th32ParentProcessID),
                    name=str(entry.szExeFile or ""),
                )
            )
            entry.dwSize = ctypes.sizeof(entry)
            if not next_fn(handle, ctypes.byref(entry)):
                break
    finally:
        close_fn(handle)
    return rows


def _windows_process_rss_bytes(pid: int) -> int | None:
    if os.name != "nt":
        return None

    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010

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

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_memory = psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL

    handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, int(pid))
    if not handle:
        handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not get_memory(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        close_handle(handle)


def _descendant_rows(root_pid: int, rows: list[ProcessRow]) -> list[ProcessRow]:
    children: dict[int, list[ProcessRow]] = {}
    for row in rows:
        children.setdefault(row.parent_pid, []).append(row)
    output: list[ProcessRow] = []
    pending = list(children.get(int(root_pid), ()))
    seen: set[int] = set()
    while pending:
        row = pending.pop()
        if row.pid in seen:
            continue
        seen.add(row.pid)
        output.append(row)
        pending.extend(children.get(row.pid, ()))
    return output


def memory_snapshot(label: str) -> dict[str, Any]:
    process_rss_mb, process_peak_mb = memory_mb()
    payload: dict[str, Any] = {
        "label": str(label),
        "process_rss_mb": process_rss_mb,
        "process_peak_rss_mb": process_peak_mb,
        "tree_rss_mb": process_rss_mb,
        "child_rss_mb": 0.0,
        "child_count": 0,
        "children": [],
    }
    if os.name != "nt":
        return payload

    rows = _windows_process_rows()
    descendants = _descendant_rows(os.getpid(), rows)
    child_rows: list[dict[str, Any]] = []
    child_total = 0
    for row in descendants:
        rss = _windows_process_rss_bytes(row.pid)
        if rss is None:
            continue
        child_total += rss
        child_rows.append(
            {
                "pid": row.pid,
                "parent_pid": row.parent_pid,
                "name": row.name,
                "rss_mb": round(rss / _MB, 2),
            }
        )
    child_rows.sort(key=lambda item: float(item["rss_mb"]), reverse=True)
    child_mb = round(child_total / _MB, 2)
    payload["child_count"] = len(child_rows)
    payload["child_rss_mb"] = child_mb
    payload["children"] = child_rows[:12]
    if process_rss_mb is not None:
        payload["tree_rss_mb"] = round(float(process_rss_mb) + child_mb, 2)
    return payload


class PeakTreeSampler:
    def __init__(self, interval_seconds: float = 0.05) -> None:
        self.interval_seconds = max(0.02, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._phase = "startup"
        self.peak_process_rss_mb = 0.0
        self.peak_tree_rss_mb = 0.0
        self.peak_tree_sample: dict[str, Any] = {}

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = str(phase)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="AtlasMemorySampler", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            sample = memory_snapshot("sample")
            process_rss = float(sample.get("process_rss_mb") or 0.0)
            tree_rss = float(sample.get("tree_rss_mb") or process_rss)
            with self._lock:
                phase = self._phase
                self.peak_process_rss_mb = max(self.peak_process_rss_mb, process_rss)
                if tree_rss > self.peak_tree_rss_mb:
                    self.peak_tree_rss_mb = tree_rss
                    self.peak_tree_sample = {**sample, "phase": phase}

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)


def _capture(app: QApplication, stages: list[dict[str, Any]], label: str, settle: float = 0.20) -> dict[str, Any]:
    pump(app, settle)
    sample = memory_snapshot(label)
    stages.append(sample)
    return sample


def _open_guide_with_probe(
    app: QApplication,
    window: Any,
    stages: list[dict[str, Any]],
    *,
    timeout: float = 60.0,
) -> float:
    """Open Guide while separating provider residency from final Qt hydration."""

    started = time.perf_counter()
    window.open_encyclopedia_tab(GUIDES_TAB)
    deadline = started + max(1.0, float(timeout))
    provider_captured = False
    worker_captured = False

    while time.perf_counter() < deadline:
        app.processEvents()
        page = getattr(window, "page_widgets", {}).get("Quetes")
        if page is not None:
            if not worker_captured and bool(getattr(page, "_related_preload_started", False)):
                stages.append(memory_snapshot("guide_worker_started"))
                worker_captured = True

            service = getattr(page, "service", None)
            provider = getattr(service, "guide_provider", None)
            if not provider_captured and bool(getattr(provider, "_loaded", False)):
                stages.append(memory_snapshot("guide_provider_loaded"))
                provider_captured = True

        if encyclopedia_ready(window, GUIDES_TAB):
            if not provider_captured:
                stages.append(memory_snapshot("guide_provider_loaded_late"))
            return round((time.perf_counter() - started) * 1000.0, 2)
        time.sleep(0.005)

    raise RuntimeError(f"Timeout while waiting for Encyclopedia {GUIDES_TAB} ({timeout:.1f}s).")


def measure() -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    stages: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    sampler = PeakTreeSampler()
    sampler.set_phase("startup")
    sampler.start()

    window = app_main.AtlasWindow()
    window.show()
    app.processEvents()
    _capture(app, stages, "startup_stabilized", 0.25)

    sampler.set_phase("preload")
    preload_deadline = time.perf_counter() + 90.0
    preload_seen: set[str] = set()
    while not preload_terminal(window):
        app.processEvents()
        states = getattr(window, "preload_states", {})
        if isinstance(states, dict):
            for task in ("quests", "encyclopedia", "craft"):
                state = str(states.get(task, "") or "")
                if task not in preload_seen and state in {"READY", "FAILED"}:
                    stages.append(memory_snapshot(f"preload_{task}_ready"))
                    preload_seen.add(task)
        if time.perf_counter() >= preload_deadline:
            raise RuntimeError("Timeout while waiting for functional preload (90.0s).")
        time.sleep(0.005)
    states = getattr(window, "preload_states", {})
    if isinstance(states, dict):
        for task in ("quests", "encyclopedia", "craft"):
            state = str(states.get(task, "") or "")
            if task not in preload_seen and state in {"READY", "FAILED"}:
                stages.append(memory_snapshot(f"preload_{task}_ready"))
                preload_seen.add(task)
    _capture(app, stages, "after_preload")

    sampler.set_phase("quests_open")
    timings["quests_open_ms"] = open_encyclopedia(app, window, QUESTS_TAB)
    _capture(app, stages, "quests_active")
    sampler.set_phase("quests_home")
    window.show_page("Home")
    after_quests_home = _capture(app, stages, "after_quests_home", 0.75)

    sampler.set_phase("achievements_open")
    timings["achievements_open_ms"] = open_encyclopedia(app, window, ACHIEVEMENTS_TAB)
    _capture(app, stages, "achievements_active")
    sampler.set_phase("achievements_home")
    window.show_page("Home")
    after_achievements_home = _capture(app, stages, "after_achievements_home", 0.75)

    sampler.set_phase("guide_open")
    timings["guide_open_ms"] = _open_guide_with_probe(app, window, stages)
    _capture(app, stages, "guide_active")
    sampler.set_phase("guide_home")
    window.show_page("Home")
    after_guide_home = _capture(app, stages, "after_guide_home", 0.75)

    sampler.set_phase("craft_open")
    timings["craft_open_ms"] = open_page(app, window, "Craft")
    _capture(app, stages, "craft_active")
    sampler.set_phase("craft_home")
    window.show_page("Home")
    before_equipment = _capture(app, stages, "before_equipment_home", 0.35)

    sampler.set_phase("equipment_open")
    timings["equipment_open_ms"] = open_page(app, window, "Equipement", timeout=60.0)
    equipment_active = _capture(app, stages, "equipment_active", 0.50)
    sampler.set_phase("equipment_home")
    window.show_page("Home")
    after_equipment = _capture(app, stages, "after_equipment_home", 0.50)
    sampler.set_phase("equipment_home_stabilized")
    after_equipment_stable = _capture(app, stages, "after_equipment_home_stabilized", 1.50)

    sampler.stop()

    shutdown = getattr(window, "_shutdown_background_services", None)
    if callable(shutdown):
        shutdown()
    window.hide()
    window.deleteLater()
    app.processEvents()

    before_tree = float(before_equipment.get("tree_rss_mb") or 0.0)
    active_tree = float(equipment_active.get("tree_rss_mb") or 0.0)
    after_tree = float(after_equipment.get("tree_rss_mb") or 0.0)
    stable_tree = float(after_equipment_stable.get("tree_rss_mb") or 0.0)
    quests_home_tree = float(after_quests_home.get("tree_rss_mb") or 0.0)
    achievements_home_tree = float(after_achievements_home.get("tree_rss_mb") or 0.0)
    guide_home_tree = float(after_guide_home.get("tree_rss_mb") or 0.0)

    return {
        "git_head": git_head(),
        "timings": timings,
        "stages": stages,
        "peak_process_rss_mb": round(sampler.peak_process_rss_mb, 2),
        "peak_tree_rss_mb": round(sampler.peak_tree_rss_mb, 2),
        "peak_tree_sample": sampler.peak_tree_sample,
        "achievements_retained_tree_delta_mb": round(
            achievements_home_tree - quests_home_tree,
            2,
        ),
        "guide_retained_tree_delta_mb": round(
            guide_home_tree - quests_home_tree,
            2,
        ),
        "equipment_tree_delta_active_mb": round(active_tree - before_tree, 2),
        "equipment_tree_delta_after_home_mb": round(after_tree - before_tree, 2),
        "equipment_tree_delta_stabilized_mb": round(stable_tree - before_tree, 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 8 staged memory benchmark")
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
