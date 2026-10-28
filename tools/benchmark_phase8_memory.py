from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
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

from PySide6.QtCore import QEvent
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

GUIDE_DETAIL_BENCHMARK_ID = "guide_complet"
_MB = 1024.0 * 1024.0


@dataclass(frozen=True)
class ProcessRow:
    pid: int
    parent_pid: int
    name: str

_WIN32_MAX_PATH = 260


class _ProcessEntry32W(ctypes.Structure):
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
        ("szExeFile", wintypes.WCHAR * _WIN32_MAX_PATH),
    ]


class _ProcessMemoryCounters(ctypes.Structure):
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


@lru_cache(maxsize=1)
def _windows_api_dlls():
    """Reuse native DLL bindings; the sampler must not grow Atlas' RSS."""
    return (
        ctypes.WinDLL("kernel32", use_last_error=True),
        ctypes.WinDLL("psapi", use_last_error=True),
    )


def _windows_process_rows() -> list[ProcessRow]:
    if os.name != "nt":
        return []

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    kernel32, _psapi = _windows_api_dlls()

    snapshot_fn = kernel32.CreateToolhelp32Snapshot
    snapshot_fn.argtypes = [wintypes.DWORD, wintypes.DWORD]
    snapshot_fn.restype = wintypes.HANDLE
    first_fn = kernel32.Process32FirstW
    first_fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    first_fn.restype = wintypes.BOOL
    next_fn = kernel32.Process32NextW
    next_fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    next_fn.restype = wintypes.BOOL
    close_fn = kernel32.CloseHandle
    close_fn.argtypes = [wintypes.HANDLE]
    close_fn.restype = wintypes.BOOL

    handle = snapshot_fn(TH32CS_SNAPPROCESS, 0)
    if not handle or int(handle) == int(INVALID_HANDLE_VALUE or -1):
        return []

    rows: list[ProcessRow] = []
    try:
        entry = _ProcessEntry32W()
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

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010
    kernel32, psapi = _windows_api_dlls()

    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_memory = psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL

    handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, int(pid))
    if not handle:
        handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not get_memory(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        close_handle(handle)


def _windows_process_creation_time(pid: int) -> int | None:
    """Read the native process creation FILETIME to disambiguate reused PIDs."""
    if os.name != "nt":
        return None

    kernel32, _psapi = _windows_api_dlls()
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    get_times = kernel32.GetProcessTimes
    get_times.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    get_times.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = open_process(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not get_times(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel_time), ctypes.byref(user_time),
        ):
            return None
        return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    finally:
        close_handle(handle)


def _descendant_rows(root_pid: int, rows: list[ProcessRow]) -> list[ProcessRow]:
    children: dict[int, list[ProcessRow]] = {}
    for row in rows:
        children.setdefault(row.parent_pid, []).append(row)
    output: list[ProcessRow] = []
    pending = list(children.get(int(root_pid), ()))
    seen: set[int] = set()

    # A Toolhelp parent PID is not proof of ancestry: Windows reuses PIDs.
    # An actual child must have started no earlier than its live parent.
    verify_creation = os.name == "nt"
    start_times: dict[int, int] = {}
    if verify_creation:
        root_start = _windows_process_creation_time(root_pid)
        if root_start is None:
            if int(root_pid) == os.getpid():
                raise RuntimeError(
                    "Cannot verify Atlas process ancestry for RAM evidence"
                )
            return []  # An external warmup process may already have exited.
        start_times[int(root_pid)] = root_start

    while pending:
        row = pending.pop()
        if row.pid == root_pid or row.pid in seen:
            continue
        if verify_creation:
            started = _windows_process_creation_time(row.pid)
            if started is None or started < start_times[row.parent_pid]:
                continue  # Stale PPID or unverifiable process: don't traverse it.
            start_times[row.pid] = started
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
        "warmup_rss_mb": 0.0,
        "warmup_process_count": 0,
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

    # Production's cache warmer is launched by the wrapper, so it is a
    # sibling of Atlas, not a descendant. Include its live process tree while
    # both are running or the startup peak would be systematically hidden.
    raw_warmup_pid = os.environ.get("DOFUS_ATLAS_WARMUP_PID", "").strip()
    warmup_pid = int(raw_warmup_pid) if raw_warmup_pid.isdecimal() else 0
    warmup_total = 0
    warmup_count = 0
    warmup_processes: list[dict[str, Any]] = []
    if warmup_pid > 0:
        root_row = next(
            (
                row for row in rows
                if row.pid == warmup_pid and row.name.lower().startswith("python")
            ),
            None,
        )
        if root_row is not None:
            counted_pids = {os.getpid(), *(row.pid for row in descendants)}
            for row in (root_row, *_descendant_rows(warmup_pid, rows)):
                if row.pid in counted_pids:
                    continue
                counted_pids.add(row.pid)
                rss = _windows_process_rss_bytes(row.pid)
                if rss is None:
                    continue
                warmup_total += rss
                warmup_count += 1
                warmup_processes.append({
                    "pid": row.pid,
                    "name": row.name,
                    "rss_mb": round(rss / _MB, 2),
                })
    warmup_mb = round(warmup_total / _MB, 2)
    payload["warmup_rss_mb"] = warmup_mb
    payload["warmup_process_count"] = warmup_count
    payload["warmup_processes"] = sorted(
        warmup_processes, key=lambda row: row["rss_mb"], reverse=True
    )[:8]
    if process_rss_mb is not None:
        payload["tree_rss_mb"] = round(float(process_rss_mb) + child_mb + warmup_mb, 2)
    return payload


def _parent_runtime_diagnostics(
    window: Any,
    *,
    baseline_modules: set[str] | None = None,
) -> dict[str, Any]:
    """Trace parent residency without importing or activating cold runtime code."""

    runtime = getattr(window, "runtime", None)
    registry = getattr(runtime, "registry", None) if runtime is not None else None
    mouse_hook = getattr(runtime, "mouse_hook", None) if runtime is not None else None
    settings = getattr(runtime, "_settings", None) if runtime is not None else None
    clients = getattr(settings, "clients", ()) if settings is not None else ()

    loaded_modules = set(sys.modules)
    new_modules = loaded_modules - (baseline_modules or set())
    return {
        "thread_names": sorted(
            str(thread.name or "")
            for thread in threading.enumerate()
            if thread.is_alive()
        ),
        "runtime_exists": runtime is not None,
        "runtime_running": bool(getattr(runtime, "_running", False))
        if runtime is not None
        else False,
        "runtime_starting": bool(getattr(runtime, "_starting", False))
        if runtime is not None
        else False,
        "runtime_bindings_available": bool(
            getattr(runtime, "_runtime_bindings_available", False)
        )
        if runtime is not None
        else False,
        "runtime_settings_loaded": settings is not None,
        "runtime_client_count": len(clients or ()),
        "hotkey_backend_loaded": bool(getattr(registry, "_backend", None) is not None),
        "mouse_backend_loaded": bool(getattr(mouse_hook, "_backend", None) is not None),
        "loaded_module_count": len(loaded_modules),
        "loaded_app_module_count": sum(
            1
            for name in loaded_modules
            if name.startswith("app.") or name.startswith("local_dofus_data.")
        ),
        "new_relevant_modules": sorted(
            name
            for name in new_modules
            if name.startswith("app.")
            or name.startswith("local_dofus_data.")
            or name.startswith("win32")
            or name in {"pythoncom", "pywintypes"}
        ),
    }


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
        self.warmup_worker_seen = False

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
            external_pid_text = os.environ.get("DOFUS_ATLAS_WARMUP_PID", "").strip()
            external_pid = int(external_pid_text) if external_pid_text.isdecimal() else 0
            warmup_worker_seen = any(
                int(row.get("pid") or 0) != external_pid
                and str(row.get("name") or "").lower().startswith("python")
                for row in sample.get("warmup_processes", ())
            )
            with self._lock:
                if warmup_worker_seen:
                    self.warmup_worker_seen = True
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
    # This benchmark drives Qt with processEvents(), not QApplication.exec().
    # Qt does NOT dispatch DeferredDelete automatically in such a local loop.
    # Flush exactly the deleteLater() events which the production event loop
    # would deliver before measuring whether Home retained live widgets.
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    sample = memory_snapshot(label)
    # Take the RSS measurement before enumerating Qt objects so introspection
    # cannot inflate the measured process-tree checkpoint.
    sample["python_threads_alive"] = sum(
        thread.is_alive() for thread in threading.enumerate()
    )
    widgets = QApplication.allWidgets()
    sample["qt_widgets_alive"] = len(widgets)
    sample["qt_widget_classes"] = dict(
        Counter(type(widget).__name__ for widget in widgets).most_common(15)
    )
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


def _open_rich_guide_with_probe(
    app: QApplication,
    window: Any,
    stages: list[dict[str, Any]],
    *,
    guide_id: str = GUIDE_DETAIL_BENCHMARK_ID,
    timeout: float = 90.0,
) -> float:
    """Open one real Guide detail so the benchmark cannot pass on catalogue-only residency."""

    started = time.perf_counter()
    page = getattr(window, "page_widgets", {}).get("Quetes")
    navigate = getattr(page, "navigate_to_guide", None) if page is not None else None
    if not callable(navigate):
        raise RuntimeError("Encyclopedia Guide navigation is unavailable")
    manual_core = None
    original_manual_loader = None
    try:
        import importlib

        manual_core = importlib.import_module(
            "app.modules.encyclopedia.services.guide_ultime_manual_runtime_core"
        )
        original_manual_loader = getattr(manual_core, "load_manual_chapter", None)
        if callable(original_manual_loader):
            probe_count = 0

            def probed_manual_loader(path, *args, **kwargs):
                nonlocal probe_count
                result = original_manual_loader(path, *args, **kwargs)
                probe_count += 1
                name = Path(path).stem.replace(" ", "_")
                stages.append(
                    memory_snapshot(
                        f"guide_manual_chapter_{probe_count:02d}_{name}"[:120]
                    )
                )
                return result

            manual_core.load_manual_chapter = probed_manual_loader

        if not bool(navigate(str(guide_id))):
            raise RuntimeError(f"Guide navigation rejected: {guide_id}")

        deadline = started + max(1.0, float(timeout))
        while time.perf_counter() < deadline:
            app.processEvents()
            page = getattr(window, "page_widgets", {}).get("Quetes")
            view = getattr(page, "guides_view", None) if page is not None else None
            if (
                str(getattr(view, "current_guide_id", "") or "") == str(guide_id)
                and bool(getattr(view, "_runtime_ready", False))
            ):
                stages.append(memory_snapshot("guide_detail_ready"))
                return round((time.perf_counter() - started) * 1000.0, 2)
            time.sleep(0.005)

        raise RuntimeError(f"Timeout while opening rich Guide detail {guide_id} ({timeout:.1f}s).")
    finally:
        if manual_core is not None and callable(original_manual_loader):
            manual_core.load_manual_chapter = original_manual_loader


def _home_rss_drift(samples: list[dict[str, Any]]) -> float | None:
    """Change in post-Home process-tree RSS between first and last same-domain cycle."""
    if len(samples) < 2:
        return None
    first = samples[0].get("tree_rss_mb")
    last = samples[-1].get("tree_rss_mb")
    if first is None or last is None:
        return None
    return round(float(last) - float(first), 2)


def measure(*, navigation_cycles: int = 2, include_heavy_views: bool = False) -> dict[str, Any]:
    if not 2 <= navigation_cycles <= 10:
        raise ValueError("navigation_cycles must be between 2 and 10")
    app = QApplication.instance() or QApplication([])
    stages: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    sampler = PeakTreeSampler()
    sampler.set_phase("startup")
    # Production launches build caches in a sibling process. Scanning the full
    # Windows process tree every 50 ms for the ~50 s sibling warmup creates a
    # large observer-effect heap inside the process being measured. Defer the
    # tree sampler until Atlas can actually spawn its own preload children; the
    # OS-reported PeakWorkingSetSize still preserves the parent startup peak.
    # CI supplies a verified warmup PID: sample from startup to include the
    # concurrent sibling. Legacy token-only sessions keep the old lazy sampler
    # to avoid observer overhead when the external process cannot be tracked.
    defer_tree_sampler = bool(
        os.environ.get("DOFUS_ATLAS_CACHE_WARMUP_TOKEN", "").strip()
    ) and not bool(os.environ.get("DOFUS_ATLAS_WARMUP_PID", "").strip())
    if not defer_tree_sampler:
        sampler.start()
        go_file = os.environ.get("DOFUS_ATLAS_WARMUP_GO_FILE", "").strip()
        if go_file:
            # Only signal once peak monitoring has actually been activated.
            Path(go_file).touch(exist_ok=False)

    window = app_main.AtlasWindow()
    window.show()
    app.processEvents()
    startup_stage = _capture(app, stages, "startup_stabilized", 0.25)
    module_baseline = set(sys.modules)
    startup_stage["runtime_diagnostics"] = _parent_runtime_diagnostics(window)
    if defer_tree_sampler:
        startup_peak = float(
            startup_stage.get("process_peak_rss_mb")
            or startup_stage.get("process_rss_mb")
            or 0.0
        )
        sampler.peak_process_rss_mb = max(
            sampler.peak_process_rss_mb,
            startup_peak,
        )
        if startup_peak > sampler.peak_tree_rss_mb:
            sampler.peak_tree_rss_mb = startup_peak
            sampler.peak_tree_sample = {
                **startup_stage,
                "tree_rss_mb": round(startup_peak, 2),
                "phase": "startup",
            }

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
                    ready_stage = memory_snapshot(f"preload_{task}_ready")
                    ready_stage["runtime_diagnostics"] = _parent_runtime_diagnostics(
                        window,
                        baseline_modules=module_baseline,
                    )
                    stages.append(ready_stage)
                    preload_seen.add(task)
                    if task == "quests" and defer_tree_sampler:
                        # The external cache warmup is a launcher sibling, not
                        # part of Atlas' process tree. Once Quest preload is
                        # terminal, Atlas may start its own short-lived workers,
                        # so tree sampling becomes meaningful again.
                        parent_peak = float(
                            ready_stage.get("process_peak_rss_mb")
                            or ready_stage.get("process_rss_mb")
                            or 0.0
                        )
                        sampler.peak_process_rss_mb = max(
                            sampler.peak_process_rss_mb,
                            parent_peak,
                        )
                        if parent_peak > sampler.peak_tree_rss_mb:
                            sampler.peak_tree_rss_mb = parent_peak
                            sampler.peak_tree_sample = {
                                **ready_stage,
                                "tree_rss_mb": round(parent_peak, 2),
                                "phase": "preload_parent",
                            }
                        sampler.start()
                        defer_tree_sampler = False
        if time.perf_counter() >= preload_deadline:
            raise RuntimeError("Timeout while waiting for functional preload (90.0s).")
        # 50 Hz is ample for Qt/preload state transitions and avoids turning
        # the benchmark's own Python pump into a long-lived allocator stressor.
        time.sleep(0.02)
    if defer_tree_sampler:
        # Defensive fallback for already-terminal/failed preload state.
        sampler.start()
        defer_tree_sampler = False

    states = getattr(window, "preload_states", {})
    if isinstance(states, dict):
        for task in ("quests", "encyclopedia", "craft"):
            state = str(states.get(task, "") or "")
            if task not in preload_seen and state in {"READY", "FAILED"}:
                stages.append(memory_snapshot(f"preload_{task}_ready"))
                preload_seen.add(task)
    after_preload_stage = _capture(app, stages, "after_preload")
    after_preload_stage["runtime_diagnostics"] = _parent_runtime_diagnostics(
        window,
        baseline_modules=module_baseline,
    )

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

    sampler.set_phase("guide_catalogue_open")
    timings["guide_open_ms"] = _open_guide_with_probe(app, window, stages)
    _capture(app, stages, "guide_catalogue_active")
    sampler.set_phase("guide_detail_open")
    timings["guide_detail_open_ms"] = _open_rich_guide_with_probe(
        app,
        window,
        stages,
    )
    _capture(app, stages, "guide_active")
    sampler.set_phase("guide_home")
    window.show_page("Home")
    after_guide_home = _capture(app, stages, "after_guide_home", 0.75)
    sampler.set_phase("guide_home_stabilized")
    after_guide_home_stable = _capture(
        app, stages, "after_guide_home_stabilized", 1.50
    )

    craft_adapter_loaded_before = "local_dofus_data.compatibility_adapter" in sys.modules
    sampler.set_phase("craft_open")
    timings["craft_open_ms"] = open_page(app, window, "Craft")
    _capture(app, stages, "craft_active")
    sampler.set_phase("craft_home")
    window.show_page("Home")
    after_craft_home = _capture(app, stages, "after_craft_home", 0.75)
    # Read-only module presence AFTER the RSS checkpoint; no SQL import, no
    # memory trim, no change to the existing retention threshold.
    craft_adapter_loaded_after = "local_dofus_data.compatibility_adapter" in sys.modules
    before_equipment = _capture(app, stages, "before_equipment_home", 0.05)

    sampler.set_phase("equipment_open")
    timings["equipment_open_ms"] = open_page(app, window, "Equipement", timeout=60.0)
    equipment_active = _capture(app, stages, "equipment_active", 0.50)
    sampler.set_phase("equipment_home")
    window.show_page("Home")
    after_equipment = _capture(app, stages, "after_equipment_home", 0.50)
    sampler.set_phase("equipment_home_stabilized")
    after_equipment_stable = _capture(app, stages, "after_equipment_home_stabilized", 1.50)

    # Repeated real navigation differentiates a one-time allocator high-water
    # mark from retention that keeps accumulating across Home transitions.
    # Keep the original canonical checkpoints and budgets unchanged.
    round_trip_home_samples: dict[str, list[dict[str, Any]]] = {
        "quests": [],
        "achievements": [],
        "guide": [],
    }
    if include_heavy_views:
        round_trip_home_samples.update({"craft": [], "equipment": []})
    for cycle in range(1, 3):
        for domain, tab in (
            ("quests", QUESTS_TAB),
            ("achievements", ACHIEVEMENTS_TAB),
        ):
            sampler.set_phase(f"repeat_{cycle}_{domain}")
            open_encyclopedia(app, window, tab)
            window.show_page("Home")
            round_trip_home_samples[domain].append(
                _capture(app, stages, f"repeat_{cycle}_{domain}_home", 0.75)
            )

        sampler.set_phase(f"repeat_{cycle}_guide")
        _open_guide_with_probe(app, window, stages)
        _open_rich_guide_with_probe(app, window, stages)
        window.show_page("Home")
        round_trip_home_samples["guide"].append(
            _capture(app, stages, f"repeat_{cycle}_guide_home", 1.50)
        )

        if include_heavy_views:
            for domain, page_name in (("craft", "Craft"), ("equipment", "Equipement")):
                sampler.set_phase(f"repeat_{cycle}_{domain}")
                open_page(app, window, page_name, timeout=60.0)
                window.show_page("Home")
                round_trip_home_samples[domain].append(
                    _capture(app, stages, f"repeat_{cycle}_{domain}_home", 1.50)
                )

    # Optional investigation mode: keep the two canonical CI cycles intact.
    # Longer sequences are only requested on Windows for a specific RAM probe.
    for cycle in range(3, navigation_cycles + 1):
        for domain, tab in (("quests", QUESTS_TAB), ("achievements", ACHIEVEMENTS_TAB)):
            sampler.set_phase(f"repeat_{cycle}_{domain}")
            open_encyclopedia(app, window, tab)
            window.show_page("Home")
            round_trip_home_samples[domain].append(
                _capture(app, stages, f"repeat_{cycle}_{domain}_home", 0.75)
            )
        sampler.set_phase(f"repeat_{cycle}_guide")
        _open_guide_with_probe(app, window, stages)
        _open_rich_guide_with_probe(app, window, stages)
        window.show_page("Home")
        round_trip_home_samples["guide"].append(
            _capture(app, stages, f"repeat_{cycle}_guide_home", 1.50)
        )
        if include_heavy_views:
            for domain, page_name in (("craft", "Craft"), ("equipment", "Equipement")):
                sampler.set_phase(f"repeat_{cycle}_{domain}")
                open_page(app, window, page_name, timeout=60.0)
                window.show_page("Home")
                round_trip_home_samples[domain].append(
                    _capture(app, stages, f"repeat_{cycle}_{domain}_home", 1.50)
                )

    sampler.stop()
    if (
        os.environ.get("DOFUS_ATLAS_WARMUP_GO_FILE", "").strip()
        and not sampler.warmup_worker_seen
    ):
        raise RuntimeError(
            "Invalid RAM evidence: external warmup child was never sampled"
        )

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
    guide_home_stable_tree = float(after_guide_home_stable.get("tree_rss_mb") or 0.0)
    craft_home_tree = float(after_craft_home.get("tree_rss_mb") or 0.0)

    return {
        "git_head": git_head(),
        "timings": timings,
        "stages": stages,
        "peak_process_rss_mb": round(sampler.peak_process_rss_mb, 2),
        "peak_tree_rss_mb": round(sampler.peak_tree_rss_mb, 2),
        "peak_tree_sample": sampler.peak_tree_sample,
        "navigation_cycles": navigation_cycles,
        "include_heavy_views": include_heavy_views,
        "round_trip_home_drift_mb": {
            domain: _home_rss_drift(samples)
            for domain, samples in round_trip_home_samples.items()
        },
        "round_trip_home": {
            domain: [
                {
                    "tree_rss_mb": item.get("tree_rss_mb"),
                    "process_rss_mb": item.get("process_rss_mb"),
                    "python_threads_alive": item.get("python_threads_alive"),
                    "qt_widgets_alive": item.get("qt_widgets_alive"),
                }
                for item in samples
            ]
            for domain, samples in round_trip_home_samples.items()
        },
        "round_trip_guide_tree_drift_mb": round(
            float(round_trip_home_samples["guide"][-1]["tree_rss_mb"] or 0.0)
            - float(round_trip_home_samples["guide"][0]["tree_rss_mb"] or 0.0),
            2,
        ),
        "achievements_retained_tree_delta_mb": round(
            achievements_home_tree - quests_home_tree,
            2,
        ),
        "guide_retained_tree_delta_mb": round(
            guide_home_tree - quests_home_tree,
            2,
        ),
        # Supplemental evidence only: keep the legacy gate metric unchanged.
        "guide_retained_tree_delta_stabilized_mb": round(
            guide_home_stable_tree - quests_home_tree,
            2,
        ),
        "guide_incremental_retained_tree_delta_mb": round(
            guide_home_stable_tree - achievements_home_tree,
            2,
        ),
        "guide_home_stabilization_delta_mb": round(
            guide_home_stable_tree - guide_home_tree,
            2,
        ),
        "craft_retained_tree_delta_mb": round(
            craft_home_tree - guide_home_tree,
            2,
        ),
        "craft_adapter_module_loaded_before": craft_adapter_loaded_before,
        "craft_adapter_module_loaded_after": craft_adapter_loaded_after,
        "equipment_tree_delta_active_mb": round(active_tree - before_tree, 2),
        "equipment_tree_delta_after_home_mb": round(after_tree - before_tree, 2),
        "equipment_tree_delta_stabilized_mb": round(stable_tree - before_tree, 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 8 staged memory benchmark")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--navigation-cycles", type=int, default=2,
                        choices=range(2, 11),
                        metavar="{2..10}",
                        help="2 canonical CI cycles; use 5-10 for manual Windows retention probes")
    parser.add_argument("--include-heavy-views", action="store_true",
                        help="also repeat Craft and Equipment within each navigation cycle")
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
        "metrics": measure(navigation_cycles=args.navigation_cycles,
                           include_heavy_views=args.include_heavy_views),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
