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


def achievement_provider_object_counts(window: AtlasWindow) -> dict[str, int]:
    """Count rich Success objects retained by the canonical provider."""

    page = current_encyclopedia_page(window)
    if page is None:
        return {"Achievement": 0, "Reward": 0, "EntityRef": 0}
    provider = page.service.achievement_provider
    achievements = list(getattr(provider, "_achievements", ()) or ())
    detail = getattr(provider, "_detail_cache", None)
    achievement_ids = {id(achievement) for achievement in achievements}
    if detail is not None:
        achievement_ids.add(id(detail))

    reward_ids: set[int] = set()
    entity_ref_ids: set[int] = set()
    for achievement in (*achievements, *((detail,) if detail is not None else ())):
        reward_ids.update(id(reward) for reward in tuple(getattr(achievement, "rewards", ()) or ()))
        for ref in (
            *tuple(getattr(achievement, "linked_quests", ()) or ()),
            *tuple(getattr(achievement, "linked_monsters", ()) or ()),
            *tuple(getattr(achievement, "linked_dungeons", ()) or ()),
            *tuple(getattr(achievement, "linked_achievements", ()) or ()),
            *tuple(getattr(achievement, "resolved_linked_quests", ()) or ()),
            *tuple(getattr(achievement, "resolved_linked_monsters", ()) or ()),
            *tuple(getattr(achievement, "resolved_linked_dungeons", ()) or ()),
        ):
            entity_ref_ids.add(id(ref))
        for objective in tuple(getattr(achievement, "objectives", ()) or ()):
            ref = getattr(objective, "entity_ref", None)
            if ref is not None:
                entity_ref_ids.add(id(ref))
            entity_ref_ids.update(
                id(ref)
                for ref in tuple(getattr(objective, "entity_refs", ()) or ())
            )
    return {
        "Achievement": len(achievement_ids),
        "Reward": len(reward_ids),
        "EntityRef": len(entity_ref_ids),
    }


def tab_is_visible(window: AtlasWindow, label: str) -> bool:
    page = current_encyclopedia_page(window)
    if page is None or window.pending_encyclopedia_tab:
        return False
    index = page.tabs.currentIndex()
    return index >= 0 and page.tabs.tabText(index) == label


def runtime_is_ready(window: AtlasWindow, label: str) -> bool:
    page = current_encyclopedia_page(window)
    if page is None or not tab_is_visible(window, label):
        return False
    if label == QUESTS_TAB:
        return page.quest_page is not None
    if label == ACHIEVEMENTS_TAB:
        return bool(getattr(page, "_achievement_ready", False)) and page.get_achievements_view() is not None
    if label == GUIDES_TAB:
        return bool(getattr(page, "_guide_runtime_ready", False)) and page.guides_view is not None
    return True



def open_runtime(
    app: QApplication,
    window: AtlasWindow,
    label: str,
    *,
    timeout: float = 60.0,
) -> tuple[float, float]:
    """Measure the canonical view through completion of async hydration."""
    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    max_ui_block_ms = wait_until_with_ui_block(
        app,
        lambda: runtime_is_ready(window, label),
        timeout,
        f"{label} canonical runtime",
    )
    return milliseconds(started), max_ui_block_ms



def first_achievement_detail(
    app: QApplication,
    window: AtlasWindow,
) -> tuple[float, int, float]:
    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page did not load before Success detail measurement.")
    view = page.get_achievements_view()
    if view is None or not bool(getattr(view, "_runtime_ready", False)):
        raise RuntimeError("Canonical Success view is not hydrated.")
    achievements = list(getattr(view, "achievements", ()) or ())
    if not achievements:
        raise RuntimeError("Canonical Success view contains no selectable achievement.")
    achievement_id = int(getattr(achievements[0], "id", 0) or 0)
    if achievement_id <= 0:
        raise RuntimeError("Canonical Success view returned an invalid achievement id.")
    started = time.perf_counter()
    call_started = time.perf_counter()
    selected = bool(view.select_achievement(achievement_id))
    call_block_ms = round((time.perf_counter() - call_started) * 1000.0, 2)
    if not selected:
        raise RuntimeError(f"Unable to select Success {achievement_id} from canonical view.")
    pump_events(app, 0.01)
    return milliseconds(started), achievement_id, call_block_ms



def first_guide_detail(
    app: QApplication,
    window: AtlasWindow,
) -> tuple[float, str, float]:
    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page did not load before Guide detail measurement.")
    view = page.guides_view
    if view is None or not bool(getattr(view, "_runtime_ready", False)):
        raise RuntimeError("Canonical Guide view is not hydrated.")
    guides = list(getattr(view, "guides", ()) or ())
    if not guides:
        raise RuntimeError("Canonical Guide view contains no selectable guide.")
    guide_id = str(getattr(guides[0], "id", "") or "")
    if not guide_id:
        raise RuntimeError("Canonical Guide view returned an invalid guide id.")
    started = time.perf_counter()
    call_started = time.perf_counter()
    selected = bool(view.select_guide(guide_id))
    call_block_ms = round((time.perf_counter() - call_started) * 1000.0, 2)
    if not selected:
        raise RuntimeError(f"Unable to select Guide {guide_id} from canonical view.")
    pump_events(app, 0.01)
    return milliseconds(started), guide_id, call_block_ms



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
    pump_events(app, 0.25)
    startup_stable_ms = milliseconds(startup_started)
    startup_stable_rss_mb = current_rss_mb()

    quests_open_ms, quests_open_ui_block_ms = open_runtime(app, window, QUESTS_TAB, timeout=30.0)
    pump_events(app, 0.05)
    rss_after_quests_mb = current_rss_mb()

    achievements_open_ms, achievements_open_ui_block_ms = open_runtime(app, window, ACHIEVEMENTS_TAB)
    pump_events(app, 0.05)
    rss_after_achievements_mb = current_rss_mb()
    achievement_objects_after_runtime = achievement_provider_object_counts(window)

    achievement_detail_ms, achievement_id, achievement_ui_block_ms = first_achievement_detail(app, window)
    pump_events(app, 0.05)
    rss_after_first_achievement_detail_mb = current_rss_mb()
    achievement_objects_after_first_detail = achievement_provider_object_counts(window)
    page = current_encyclopedia_page(window)
    achievement_provider = page.service.achievement_provider if page is not None else None
    achievement_reward_detail_thread = str(getattr(achievement_provider, "last_detail_thread_name", "") or "")
    achievement_reward_detail_ms = float(getattr(achievement_provider, "last_detail_ms", 0.0) or 0.0)
    achievement_detail_sources_ready = bool(getattr(achievement_provider, "detail_sources_ready", False))

    guide_open_ms, guide_open_ui_block_ms = open_runtime(app, window, GUIDES_TAB)
    pump_events(app, 0.05)
    rss_after_guide_mb = current_rss_mb()

    guide_detail_ms, guide_id, guide_ui_block_ms = first_guide_detail(app, window)
    pump_events(app, 0.05)
    rss_after_first_guide_detail_mb = current_rss_mb()
    rss_after_first_views_mb = current_rss_mb()

    quests_hot_return_ms = open_hot_tab(app, window, QUESTS_TAB)
    achievements_hot_return_ms = open_hot_tab(app, window, ACHIEVEMENTS_TAB)
    guide_hot_return_ms = open_hot_tab(app, window, GUIDES_TAB)

    round_trip_samples: dict[str, list[float]] = {"quests": [], "achievements": [], "guide": []}
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
        "quests_open_ms": quests_open_ms,
        "quests_open_max_ui_block_ms": quests_open_ui_block_ms,
        "achievements_open_ms": achievements_open_ms,
        "achievements_open_max_ui_block_ms": achievements_open_ui_block_ms,
        "guide_open_ms": guide_open_ms,
        "guide_open_max_ui_block_ms": guide_open_ui_block_ms,
        "first_achievement_detail_ms": achievement_detail_ms,
        "first_achievement_detail_max_ui_block_ms": achievement_ui_block_ms,
        "first_achievement_id": achievement_id,
        "first_achievement_reward_detail_ms": achievement_reward_detail_ms,
        "first_achievement_reward_detail_thread": achievement_reward_detail_thread,
        "achievement_detail_sources_ready": achievement_detail_sources_ready,
        "achievement_objects_after_runtime": achievement_objects_after_runtime,
        "achievement_objects_after_first_detail": achievement_objects_after_first_detail,
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
        "rss_after_achievements_mb": rss_after_achievements_mb,
        "rss_after_guide_mb": rss_after_guide_mb,
        "rss_after_first_achievement_detail_mb": rss_after_first_achievement_detail_mb,
        "rss_after_first_guide_detail_mb": rss_after_first_guide_detail_mb,
        "rss_after_all_views_mb": rss_after_first_views_mb,
        "rss_after_round_trips_mb": rss_after_round_trips_mb,
        "idle_cpu_percent_one_core": idle_cpu_percent_one_core,
        "idle_cpu_sample_seconds": 1.0,
    }

    window._shutdown_background_services()
    window.hide()
    window.deleteLater()
    app.processEvents()
    return result



def main() -> int:
    payload = {
        "schema_version": 4,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pyside": PYSIDE_VERSION,
            "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
            "git_head": git_head(),
            "notes": (
                "Offscreen canonical Encyclopedia user-path measurement. Cold Guide/Success metrics include the stable real view "
                "and completion of asynchronous runtime hydration; no lightweight functional index is measured."
            ),
        },
        "before": BEFORE,
        "after": measure(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
