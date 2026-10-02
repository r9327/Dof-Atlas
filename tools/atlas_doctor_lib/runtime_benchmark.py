from __future__ import annotations

import argparse
import copy
import ctypes
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any


SCHEMA_VERSION = 1
HOT_ROUND_TRIPS = 5
ENVIRONMENT_KEYS = ("platform", "python", "pyside", "qt_qpa_platform")


def milliseconds(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def git_head(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def current_rss_mb() -> float | None:
    """Return this process resident set without adding a runtime dependency."""

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
            return round(
                resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0),
                2,
            )
        except (OSError, ValueError, IndexError):
            return None
    return None


def _pump_events(app: Any, seconds: float) -> None:
    deadline = time.perf_counter() + max(0.0, seconds)
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _wait_until(app: Any, predicate: Any, timeout: float, description: str) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(0.005)
    raise RuntimeError(f"Timeout while waiting for {description} ({timeout:.1f}s).")


def _wait_until_with_ui_block(
    app: Any,
    predicate: Any,
    timeout: float,
    description: str,
) -> float:
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


def _measure_idle_cpu_percent(app: Any, seconds: float = 1.0) -> float:
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    _pump_events(app, seconds)
    wall_elapsed = max(time.perf_counter() - wall_started, 1e-9)
    cpu_elapsed = max(time.process_time() - cpu_started, 0.0)
    return round((cpu_elapsed / wall_elapsed) * 100.0, 2)


def _current_encyclopedia_page(window: Any) -> Any | None:
    from app.modules.encyclopedia.views import EncyclopediaPage

    page = window.page_widgets.get("Quetes")
    return page if isinstance(page, EncyclopediaPage) else None


def _achievement_provider_object_counts(window: Any) -> dict[str, int]:
    page = _current_encyclopedia_page(window)
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
        reward_ids.update(
            id(reward) for reward in tuple(getattr(achievement, "rewards", ()) or ())
        )
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


def _tab_is_visible(window: Any, label: str) -> bool:
    page = _current_encyclopedia_page(window)
    if page is None or window.pending_encyclopedia_tab:
        return False
    index = page.tabs.currentIndex()
    return index >= 0 and page.tabs.tabText(index) == label


def _runtime_is_ready(window: Any, label: str) -> bool:
    from app.modules.encyclopedia.constants import (
        ACHIEVEMENTS_TAB,
        GUIDES_TAB,
        QUESTS_TAB,
    )

    page = _current_encyclopedia_page(window)
    if page is None or not _tab_is_visible(window, label):
        return False
    if label == QUESTS_TAB:
        return page.quest_page is not None
    if label == ACHIEVEMENTS_TAB:
        view = page.get_achievements_view()
        return bool(getattr(page, "_achievement_ready", False)) and bool(
            view is not None and getattr(view, "_runtime_ready", False)
        )
    if label == GUIDES_TAB:
        return bool(getattr(page, "_guide_runtime_ready", False)) and bool(
            page.guides_view is not None
            and getattr(page.guides_view, "_runtime_ready", False)
        )
    return True


def _open_runtime(
    app: Any,
    window: Any,
    label: str,
    *,
    timeout: float = 60.0,
) -> tuple[float, float]:
    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    max_ui_block_ms = _wait_until_with_ui_block(
        app,
        lambda: _runtime_is_ready(window, label),
        timeout,
        f"{label} canonical runtime",
    )
    return milliseconds(started), max_ui_block_ms


def _first_achievement_detail(app: Any, window: Any) -> tuple[float, int, float]:
    page = _current_encyclopedia_page(window)
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
    _pump_events(app, 0.01)
    return milliseconds(started), achievement_id, call_block_ms


def _first_guide_detail(app: Any, window: Any) -> tuple[float, str, float]:
    page = _current_encyclopedia_page(window)
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
    _pump_events(app, 0.01)
    return milliseconds(started), guide_id, call_block_ms


def _open_hot_tab(
    app: Any,
    window: Any,
    label: str,
    *,
    timeout: float = 10.0,
) -> float:
    started = time.perf_counter()
    window.open_encyclopedia_tab(label)
    _wait_until(app, lambda: _tab_is_visible(window, label), timeout, f"hot {label} tab")
    return milliseconds(started)


def _summarize_samples(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"avg_ms": 0.0, "max_ms": 0.0}
    return {
        "avg_ms": round(sum(samples) / len(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def measure_sample(root: Path) -> dict[str, Any]:
    """Measure the real Atlas Encyclopedia path in one fresh process."""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

    from PySide6 import __version__ as pyside_version
    from PySide6.QtWidgets import QApplication

    from app.modules.encyclopedia.constants import (
        ACHIEVEMENTS_TAB,
        GUIDES_TAB,
        QUESTS_TAB,
    )
    from main import AtlasWindow

    app = QApplication.instance() or QApplication([])
    startup_started = time.perf_counter()
    window = AtlasWindow()
    try:
        constructor_ms = milliseconds(startup_started)
        window.show()
        app.processEvents()
        first_window_ms = milliseconds(startup_started)
        _pump_events(app, 0.25)
        startup_stable_ms = milliseconds(startup_started)
        startup_stable_rss_mb = current_rss_mb()

        quests_open_ms, quests_open_ui_block_ms = _open_runtime(
            app, window, QUESTS_TAB, timeout=30.0
        )
        _pump_events(app, 0.05)
        rss_after_quests_mb = current_rss_mb()

        achievements_open_ms, achievements_open_ui_block_ms = _open_runtime(
            app, window, ACHIEVEMENTS_TAB
        )
        _pump_events(app, 0.05)
        rss_after_achievements_mb = current_rss_mb()
        achievement_objects_after_runtime = _achievement_provider_object_counts(window)

        achievement_detail_ms, achievement_id, achievement_ui_block_ms = (
            _first_achievement_detail(app, window)
        )
        _pump_events(app, 0.05)
        rss_after_first_achievement_detail_mb = current_rss_mb()
        achievement_objects_after_first_detail = _achievement_provider_object_counts(window)
        page = _current_encyclopedia_page(window)
        achievement_provider = page.service.achievement_provider if page is not None else None
        achievement_reward_detail_thread = str(
            getattr(achievement_provider, "last_detail_thread_name", "") or ""
        )
        achievement_reward_detail_ms = float(
            getattr(achievement_provider, "last_detail_ms", 0.0) or 0.0
        )
        achievement_detail_sources_ready = bool(
            getattr(achievement_provider, "detail_sources_ready", False)
        )

        guide_open_ms, guide_open_ui_block_ms = _open_runtime(app, window, GUIDES_TAB)
        _pump_events(app, 0.05)
        rss_after_guide_mb = current_rss_mb()

        guide_detail_ms, guide_id, guide_ui_block_ms = _first_guide_detail(app, window)
        _pump_events(app, 0.05)
        rss_after_first_guide_detail_mb = current_rss_mb()
        rss_after_all_views_mb = current_rss_mb()

        quests_hot_return_ms = _open_hot_tab(app, window, QUESTS_TAB)
        achievements_hot_return_ms = _open_hot_tab(app, window, ACHIEVEMENTS_TAB)
        guide_hot_return_ms = _open_hot_tab(app, window, GUIDES_TAB)

        round_trip_samples: dict[str, list[float]] = {
            "quests": [],
            "achievements": [],
            "guide": [],
        }
        for _ in range(HOT_ROUND_TRIPS):
            round_trip_samples["quests"].append(
                _open_hot_tab(app, window, QUESTS_TAB)
            )
            round_trip_samples["achievements"].append(
                _open_hot_tab(app, window, ACHIEVEMENTS_TAB)
            )
            round_trip_samples["guide"].append(
                _open_hot_tab(app, window, GUIDES_TAB)
            )
        _pump_events(app, 0.1)
        rss_after_round_trips_mb = current_rss_mb()
        idle_cpu_percent_one_core = _measure_idle_cpu_percent(app, 1.0)

        metrics = {
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
            "hot_round_trip_quests": _summarize_samples(round_trip_samples["quests"]),
            "hot_round_trip_achievements": _summarize_samples(
                round_trip_samples["achievements"]
            ),
            "hot_round_trip_guide": _summarize_samples(round_trip_samples["guide"]),
            "rss_after_quests_mb": rss_after_quests_mb,
            "rss_after_achievements_mb": rss_after_achievements_mb,
            "rss_after_guide_mb": rss_after_guide_mb,
            "rss_after_first_achievement_detail_mb": rss_after_first_achievement_detail_mb,
            "rss_after_first_guide_detail_mb": rss_after_first_guide_detail_mb,
            "rss_after_all_views_mb": rss_after_all_views_mb,
            "rss_after_round_trips_mb": rss_after_round_trips_mb,
            "idle_cpu_percent_one_core": idle_cpu_percent_one_core,
            "idle_cpu_sample_seconds": 1.0,
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "atlas_doctor_runtime_sample",
            "environment": {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "pyside": pyside_version,
                "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
                "git_head": git_head(root),
            },
            "metrics": metrics,
        }
    finally:
        shutdown = getattr(window, "_shutdown_background_services", None)
        if callable(shutdown):
            shutdown()
        window.hide()
        window.deleteLater()
        app.processEvents()


def _median_tree(values: list[Any]) -> Any:
    present = [value for value in values if value is not None]
    if not present:
        return None
    if all(isinstance(value, dict) for value in present):
        keys: set[str] = set()
        for value in present:
            keys.update(str(key) for key in value)
        return {
            key: _median_tree([value.get(key) for value in present])
            for key in sorted(keys)
        }
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in present
    ):
        return round(float(median(float(value) for value in present)), 3)
    first = present[0]
    if all(value == first for value in present):
        return copy.deepcopy(first)
    return copy.deepcopy(first)


def aggregate_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("At least one runtime sample is required.")
    environments = [sample.get("environment") or {} for sample in samples]
    medians = _median_tree([sample.get("metrics") or {} for sample in samples])
    environment = dict(environments[0])
    environment["sample_count"] = len(samples)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "atlas_doctor_runtime_benchmark",
        "environment": environment,
        "sample_count": len(samples),
        "samples": samples,
        "medians": medians,
        # Compatibility contract used by Doctor compare/report. New code should
        # prefer `medians`; `after` intentionally contains the same aggregate.
        "after": copy.deepcopy(medians),
    }


def _flatten_numeric(payload: Any, prefix: str = "") -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_numeric(value, child))
    elif isinstance(payload, (int, float)) and not isinstance(payload, bool):
        result[prefix] = float(payload)
    return result


def _is_cost_metric(metric: str) -> bool:
    leaf = metric.rsplit(".", 1)[-1]
    return (
        leaf.endswith("_ms")
        or leaf.endswith("_mb")
        or leaf.endswith("_percent")
        or leaf.endswith("_percent_one_core")
    )


def _baseline_medians(benchmark: dict[str, Any] | None) -> dict[str, Any]:
    if not benchmark:
        return {}
    medians = benchmark.get("medians")
    if isinstance(medians, dict):
        return medians
    legacy = benchmark.get("after")
    return legacy if isinstance(legacy, dict) else {}


def compare_to_baseline(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    if not baseline:
        return {"status": "UNAVAILABLE", "reason": "No previous runtime benchmark."}

    current_environment = current.get("environment") or {}
    baseline_environment = baseline.get("environment") or {}
    mismatches = [
        key
        for key in ENVIRONMENT_KEYS
        if current_environment.get(key) != baseline_environment.get(key)
    ]
    if mismatches:
        return {
            "status": "UNAVAILABLE",
            "reason": "Runtime environments differ; performance delta is not comparable.",
            "environment_mismatches": mismatches,
            "baseline_git_head": baseline_environment.get("git_head"),
        }

    current_values = _flatten_numeric(_baseline_medians(current))
    baseline_values = _flatten_numeric(_baseline_medians(baseline))
    rows: list[dict[str, Any]] = []
    for metric in sorted(current_values.keys() & baseline_values.keys()):
        if not _is_cost_metric(metric):
            continue
        before = baseline_values[metric]
        after = current_values[metric]
        delta = after - before
        percent = None if before == 0 else round((delta / before) * 100.0, 2)
        rows.append(
            {
                "metric": metric,
                "baseline": round(before, 3),
                "current": round(after, 3),
                "delta": round(delta, 3),
                "delta_percent": percent,
            }
        )
    regressions = [
        row
        for row in rows
        if row["delta_percent"] is not None
        and row["delta_percent"] >= 15.0
        and row["current"] - row["baseline"] > 1.0
    ]
    improvements = [
        row
        for row in rows
        if row["delta_percent"] is not None
        and row["delta_percent"] <= -15.0
        and row["baseline"] - row["current"] > 1.0
    ]
    return {
        "status": "WARN" if regressions else "PASS",
        "baseline_git_head": baseline_environment.get("git_head"),
        "metrics": rows,
        "regressions_15pct": regressions,
        "improvements_15pct": improvements,
    }


def attach_baseline_comparison(
    benchmark: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    result = copy.deepcopy(benchmark)
    if baseline:
        result["baseline"] = {
            "environment": copy.deepcopy(baseline.get("environment") or {}),
            "medians": copy.deepcopy(_baseline_medians(baseline)),
        }
    result["comparison"] = compare_to_baseline(result, baseline)
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Atlas Doctor runtime benchmark sample runner."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    payload = measure_sample(root)
    _write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
