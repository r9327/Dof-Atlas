from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtWidgets import QApplication

from app.constants import ROOT_DIR
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.views import EncyclopediaPage
from main import AtlasWindow


OUTPUT = ROOT_DIR / "artifacts" / "quests_guides_performance.json"
HOT_ROUND_TRIPS = 5

# Historical anchors kept only for continuity with the earlier performance report.
# They are not treated as a same-machine baseline for the current measurement.
BEFORE = {
    "startup_constructor_ms": 82.0,
    "first_window_paint_ms": 116.0,
    "quest_catalog_warm_ms": 150.77,
    "related_providers_sync_ms": 3682.49,
    "first_guide_render_ms": 97.65,
    "first_quest_render_ms": 127.19,
    "next_quest_render_ms": 45.27,
    "notes": "Historical snapshot only; current Phase 7B metrics below measure the real on-demand user path.",
}


def milliseconds(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def current_rss_mb() -> float | None:
    """Return the current process resident set without adding a dependency."""

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
            return None
        return round(counters.WorkingSetSize / (1024.0 * 1024.0), 2)

    statm = Path("/proc/self/statm")
    if statm.is_file():
        try:
            resident_pages = int(statm.read_text(encoding="ascii").split()[1])
            return round(resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0), 2)
        except (OSError, ValueError, IndexError):
            return None
    return None


def pump_events(app: QApplication, seconds: float) -> None:
    deadline = time.perf_counter() + max(0.0, seconds)
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def wait_until(app: QApplication, predicate, timeout: float, description: str) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(0.005)
    raise RuntimeError(f"Timeout while waiting for {description} ({timeout:.1f}s).")


def wait_until_with_ui_block(
    app: QApplication,
    predicate,
    timeout: float,
    description: str,
) -> float:
    """Wait for async work and report the longest processEvents call."""

    deadline = time.perf_counter() + timeout
    max_block_seconds = 0.0
    while time.perf_counter() < deadline:
        event_started = time.perf_counter()
        app.processEvents()
        max_block_seconds = max(max_block_seconds, time.perf_counter() - event_started)
        if predicate():
            event_started = time.perf_counter()
            app.processEvents()
            max_block_seconds = max(max_block_seconds, time.perf_counter() - event_started)
            return round(max_block_seconds * 1000.0, 2)
        time.sleep(0.005)
    raise RuntimeError(f"Timeout while waiting for {description} ({timeout:.1f}s).")


def measure_idle_cpu_percent(app: QApplication, seconds: float = 1.0) -> float:
    """Process CPU usage expressed as a percentage of one logical CPU core."""

    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    pump_events(app, seconds)
    wall_elapsed = max(time.perf_counter() - wall_started, 1e-9)
    cpu_elapsed = max(time.process_time() - cpu_started, 0.0)
    return round((cpu_elapsed / wall_elapsed) * 100.0, 2)


def current_encyclopedia_page(window: AtlasWindow) -> EncyclopediaPage | None:
    page = window.page_widgets.get("Quetes")
    return page if isinstance(page, EncyclopediaPage) else None


def tab_is_visible(window: AtlasWindow, label: str) -> bool:
    page = current_encyclopedia_page(window)
    if page is None or window.pending_encyclopedia_tab:
        return False
    index = page.tabs.currentIndex()
    return index >= 0 and page.tabs.tabText(index) == label


def index_is_ready(window: AtlasWindow, label: str) -> bool:
    page = current_encyclopedia_page(window)
    if page is None or not tab_is_visible(window, label):
        return False
    if label == QUESTS_TAB:
        return page.quest_page is not None
    if label == ACHIEVEMENTS_TAB:
        view = getattr(page, "_achievement_index_view", None)
        return view is not None and bool(getattr(view, "_rows", []))
    if label == GUIDES_TAB:
        view = getattr(page, "_guide_index_view", None)
        return view is not None and bool(getattr(view, "_rows", []))
    return True


def open_index(
    app: QApplication,
    window: AtlasWindow,
    label: str,
    *,
    timeout: float = 30.0,
) -> float:
    """Measure the cold usable index, without forcing a rich detail runtime."""

    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    wait_until(app, lambda: index_is_ready(window, label), timeout, f"{label} index")
    return milliseconds(started)


def first_achievement_detail(
    app: QApplication,
    window: AtlasWindow,
    *,
    timeout: float = 60.0,
) -> tuple[float, int, float]:
    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page did not load before Success detail measurement.")
    index_view = getattr(page, "_achievement_index_view", None)
    rows = list(getattr(index_view, "_rows", []) or [])
    if not rows:
        raise RuntimeError("Success index contains no selectable achievement.")
    achievement_id = int(rows[0][0])

    started = time.perf_counter()
    page._on_achievement_requested(achievement_id)
    max_ui_block_ms = wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_achievement_ready", False))
        and getattr(page, "_pending_achievement_id", None) is None
        and page.get_achievements_view() is not None
        and tab_is_visible(window, ACHIEVEMENTS_TAB),
        timeout,
        f"Success detail {achievement_id}",
    )
    return milliseconds(started), achievement_id, max_ui_block_ms


def first_guide_detail(
    app: QApplication,
    window: AtlasWindow,
    *,
    timeout: float = 60.0,
) -> tuple[float, str, float]:
    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page did not load before Guide detail measurement.")
    index_view = getattr(page, "_guide_index_view", None)
    rows = list(getattr(index_view, "_rows", []) or [])
    if not rows:
        raise RuntimeError("Guide index contains no selectable guide.")
    guide_id = str(rows[0][0])

    started = time.perf_counter()
    page._on_guide_requested(guide_id)
    max_ui_block_ms = wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_guide_runtime_ready", False))
        and not str(getattr(page, "_pending_guide_id", "") or "")
        and page.guides_view is not None
        and str(getattr(page.guides_view, "current_guide_id", "") or "") == guide_id
        and tab_is_visible(window, GUIDES_TAB),
        timeout,
        f"Guide detail {guide_id}",
    )
    return milliseconds(started), guide_id, max_ui_block_ms


def open_hot_tab(
    app: QApplication,
    window: AtlasWindow,
    label: str,
    *,
    timeout: float = 10.0,
) -> float:
    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    wait_until(app, lambda: tab_is_visible(window, label), timeout, f"hot {label} tab")
    return milliseconds(started)


def summarize_samples(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"avg_ms": 0.0, "max_ms": 0.0}
    return {
        "avg_ms": round(sum(samples) / len(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def measure() -> dict[str, object]:
    app = QApplication.instance() or QApplication([])

    startup_started = time.perf_counter()
    window = AtlasWindow()
    constructor_ms = milliseconds(startup_started)
    window.show()
    app.processEvents()
    first_window_ms = milliseconds(startup_started)

    # Normal startup deliberately keeps heavy Encyclopedia content on demand.
    pump_events(app, 0.25)
    startup_stable_ms = milliseconds(startup_started)
    startup_stable_rss_mb = current_rss_mb()

    quests_index_open_ms = open_index(app, window, QUESTS_TAB)
    pump_events(app, 0.05)
    rss_after_quests_mb = current_rss_mb()

    achievements_index_open_ms = open_index(app, window, ACHIEVEMENTS_TAB)
    pump_events(app, 0.05)
    rss_after_achievements_index_mb = current_rss_mb()

    guide_index_open_ms = open_index(app, window, GUIDES_TAB)
    pump_events(app, 0.05)
    rss_after_guide_index_mb = current_rss_mb()
    rss_after_indexes_mb = current_rss_mb()

    # Rich runtimes are intentionally measured only after the user selects a
    # real item from the light index. A simple tab click must not pay this cost.
    window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
    wait_until(app, lambda: tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "Success index revisit")
    achievement_detail_ms, achievement_id, achievement_ui_block_ms = first_achievement_detail(app, window)
    pump_events(app, 0.05)
    rss_after_first_achievement_detail_mb = current_rss_mb()

    window.open_encyclopedia_tab(GUIDES_TAB)
    wait_until(app, lambda: tab_is_visible(window, GUIDES_TAB), 10.0, "Guide index revisit")
    guide_detail_ms, guide_id, guide_ui_block_ms = first_guide_detail(app, window)
    pump_events(app, 0.05)
    rss_after_first_guide_detail_mb = current_rss_mb()
    rss_after_first_views_mb = current_rss_mb()

    quests_hot_return_ms = open_hot_tab(app, window, QUESTS_TAB)
    achievements_hot_return_ms = open_hot_tab(app, window, ACHIEVEMENTS_TAB)
    guide_hot_return_ms = open_hot_tab(app, window, GUIDES_TAB)

    round_trip_samples: dict[str, list[float]] = {
        "quests": [],
        "achievements": [],
        "guide": [],
    }
    for _ in range(HOT_ROUND_TRIPS):
        round_trip_samples["quests"].append(open_hot_tab(app, window, QUESTS_TAB))
        round_trip_samples["achievements"].append(open_hot_tab(app, window, ACHIEVEMENTS_TAB))
        round_trip_samples["guide"].append(open_hot_tab(app, window, GUIDES_TAB))
    pump_events(app, 0.1)
    rss_after_round_trips_mb = current_rss_mb()

    idle_cpu_percent_one_core = measure_idle_cpu_percent(app, 1.0)

    result = {
        "startup_constructor_ms": constructor_ms,
        "first_window_paint_ms": first_window_ms,
        "startup_stabilized_ms": startup_stable_ms,
        "startup_stabilized_rss_mb": startup_stable_rss_mb,
        "startup_preload_state": "DEFERRED_ON_DEMAND",
        "quests_index_open_ms": quests_index_open_ms,
        "achievements_index_open_ms": achievements_index_open_ms,
        "guide_index_open_ms": guide_index_open_ms,
        "first_achievement_detail_ms": achievement_detail_ms,
        "first_achievement_detail_max_ui_block_ms": achievement_ui_block_ms,
        "first_achievement_id": achievement_id,
        "first_guide_detail_ms": guide_detail_ms,
        "first_guide_detail_max_ui_block_ms": guide_ui_block_ms,
        "first_guide_id": guide_id,
        "quests_hot_return_ms": quests_hot_return_ms,
        "achievements_hot_return_ms": achievements_hot_return_ms,
        "guide_hot_return_ms": guide_hot_return_ms,
        "hot_round_trip_cycles": HOT_ROUND_TRIPS,
        "hot_round_trip_quests": summarize_samples(round_trip_samples["quests"]),
        "hot_round_trip_achievements": summarize_samples(round_trip_samples["achievements"]),
        "hot_round_trip_guide": summarize_samples(round_trip_samples["guide"]),
        "rss_after_quests_mb": rss_after_quests_mb,
        "rss_after_achievements_index_mb": rss_after_achievements_index_mb,
        "rss_after_guide_index_mb": rss_after_guide_index_mb,
        "rss_after_indexes_mb": rss_after_indexes_mb,
        "rss_after_first_achievement_detail_mb": rss_after_first_achievement_detail_mb,
        "rss_after_first_guide_detail_mb": rss_after_first_guide_detail_mb,
        "rss_after_first_views_mb": rss_after_first_views_mb,
        "rss_after_round_trips_mb": rss_after_round_trips_mb,
        "idle_cpu_percent_one_core": idle_cpu_percent_one_core,
        "idle_cpu_sample_seconds": 1.0,
        # Compatibility names retained for existing report consumers.
        "quests_open_ms": quests_index_open_ms,
        "achievements_open_ms": achievements_index_open_ms,
        "guide_open_ms": guide_index_open_ms,
        "rss_after_achievements_mb": rss_after_achievements_index_mb,
        "rss_after_guide_mb": rss_after_guide_index_mb,
        "rss_after_all_views_mb": rss_after_first_views_mb,
    }

    window._shutdown_background_services()
    window.hide()
    window.deleteLater()
    app.processEvents()
    return result


def main() -> int:
    payload = {
        "schema_version": 3,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pyside": PYSIDE_VERSION,
            "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
            "git_head": git_head(),
            "notes": (
                "Offscreen reproducible Phase 7B user-path measurement. Cold tab metrics wait for the usable light index only; "
                "rich Guide/Success runtime is measured separately after selecting a real item. Network capture/UAC is excluded. "
                "RAM is process working set on Windows; max UI block measures the longest QApplication.processEvents call while "
                "waiting for each first rich detail; hot returns are measured after both rich runtimes are resident."
            ),
        },
        "before": BEFORE,
        "after": measure(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
