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
from app.modules.encyclopedia.services import build_related_encyclopedia_data, related_data_build_count
from app.modules.encyclopedia.views import EncyclopediaPage
from main import AtlasWindow


OUTPUT = ROOT_DIR / "artifacts" / "quests_guides_performance.json"

# Historical anchors kept for continuity with the existing performance report.
BEFORE = {
    "startup_constructor_ms": 82.0,
    "first_window_paint_ms": 116.0,
    "quest_catalog_warm_ms": 150.77,
    "related_providers_sync_ms": 3682.49,
    "first_guide_render_ms": 97.65,
    "first_quest_render_ms": 127.19,
    "next_quest_render_ms": 45.27,
    "notes": "Startup snapshot validated on 2026-08-15; interaction probe captured before this addendum.",
}

AFTER_COLD_CACHE_REBUILD = {
    "guide_click_dispatch_ms": 1.12,
    "related_data_ready_background_ms": 4661.24,
    "max_event_loop_gap_during_background_ms": 494.43,
    "notes": "Mesure après invalidation volontaire du cache; la page courante reste affichée pendant la reconstruction.",
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
        class ProcessMemoryCounters(ctypes.Structure):
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

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            handle,
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


def open_tab(
    app: QApplication,
    window: AtlasWindow,
    label: str,
    *,
    require_related: bool = False,
    timeout: float = 20.0,
) -> float:
    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    wait_until(app, lambda: tab_is_visible(window, label), timeout, f"{label} tab")

    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page did not load.")
    if require_related:
        wait_until(
            app,
            lambda: bool(getattr(page, "_related_ready", False)),
            timeout,
            f"{label} related data",
        )
        if label == GUIDES_TAB:
            page.ensure_guides_view()
        elif label == ACHIEVEMENTS_TAB:
            page.ensure_achievements_view()
        app.processEvents()
    return milliseconds(started)


def measure() -> dict[str, object]:
    app = QApplication.instance() or QApplication([])

    startup_started = time.perf_counter()
    window = AtlasWindow()
    constructor_ms = milliseconds(startup_started)
    window.show()
    app.processEvents()
    first_window_ms = milliseconds(startup_started)

    # Normal startup deliberately defers heavy catalogue work until navigation.
    # Waiting for ``preload_finished`` therefore waited on work that was never
    # started and produced a false 30-second timeout. Stabilization measures the
    # first idle event-loop window; view timings below own their on-demand work.
    pump_events(app, 0.25)
    startup_stable_ms = milliseconds(startup_started)
    startup_stable_rss_mb = current_rss_mb()

    quests_open_ms = open_tab(app, window, QUESTS_TAB)
    pump_events(app, 0.1)
    quests_rss_mb = current_rss_mb()

    guide_open_ms = open_tab(app, window, GUIDES_TAB, require_related=True)
    pump_events(app, 0.1)
    guide_rss_mb = current_rss_mb()

    achievements_open_ms = open_tab(app, window, ACHIEVEMENTS_TAB, require_related=True)
    pump_events(app, 0.1)
    achievements_rss_mb = current_rss_mb()

    idle_cpu_percent_one_core = measure_idle_cpu_percent(app, 1.0)
    rss_after_all_views_mb = current_rss_mb()

    page = current_encyclopedia_page(window)
    cache_reuse_ms: float | None = None
    cache_reused_same_object: bool | None = None
    related_builds_during_reuse: int | None = None
    if page is not None:
        catalog = page.quest_provider.get_catalog()
        count_before_reuse = related_data_build_count()
        started = time.perf_counter()
        first = build_related_encyclopedia_data(catalog)
        second = build_related_encyclopedia_data(catalog)
        cache_reuse_ms = milliseconds(started)
        count_after_reuse = related_data_build_count()
        cache_reused_same_object = first is second
        related_builds_during_reuse = count_after_reuse - count_before_reuse

    window._shutdown_background_services()
    window.hide()
    window.deleteLater()
    app.processEvents()
    return {
        "startup_constructor_ms": constructor_ms,
        "first_window_paint_ms": first_window_ms,
        "startup_stabilized_ms": startup_stable_ms,
        "startup_stabilized_rss_mb": startup_stable_rss_mb,
        "startup_preload_state": "DEFERRED_ON_DEMAND",
        "quests_open_ms": quests_open_ms,
        "rss_after_quests_mb": quests_rss_mb,
        "guide_open_ms": guide_open_ms,
        "rss_after_guide_mb": guide_rss_mb,
        "achievements_open_ms": achievements_open_ms,
        "rss_after_achievements_mb": achievements_rss_mb,
        "rss_after_all_views_mb": rss_after_all_views_mb,
        "idle_cpu_percent_one_core": idle_cpu_percent_one_core,
        "idle_cpu_sample_seconds": 1.0,
        "cache_reuse_ms": cache_reuse_ms,
        "cache_reused_same_object": cache_reused_same_object,
        "related_builds_during_reuse": related_builds_during_reuse,
    }


def main() -> int:
    payload = {
        "schema_version": 2,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pyside": PYSIDE_VERSION,
            "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
            "git_head": git_head(),
            "notes": (
                "Offscreen reproducible application baseline. Startup stops at an idle event-loop window; "
                "heavy catalogue work remains deferred to the measured view interactions. "
                "network-capture/UAC interaction is intentionally excluded. RAM is process working set on Windows. "
                "Idle CPU is process CPU time as a percentage of one logical core."
            ),
        },
        "before": BEFORE,
        "after_cold_cache_rebuild": AFTER_COLD_CACHE_REBUILD,
        "after": measure(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
