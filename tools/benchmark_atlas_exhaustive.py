"""Manual, exhaustive Windows/Qt guide benchmark.

Not a replacement for the canonical short Phase 8 certification.
Qt offscreen event-loop lag is a proxy for stalls, NOT real display FPS.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import ExitStack
import json
import math
import os
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.constants import GUIDES_TAB
from app.modules.encyclopedia.views.guide_library_sources import (
    ATLAS_EQUIVALENTS, load_ganymede_listings,
)
from tools.benchmark_phase8_preload import (
    app_main, git_head, open_encyclopedia, preload_terminal, pump, wait_until,
)
from tools.benchmark_phase8_memory import PeakTreeSampler, memory_snapshot
from tools.benchmark_phase8_preload import memory_mb
from tools.atlas_perf_attribution import (
    SpanAttributor, QtStallStackSampler, TargetedProfile, StartupCpuProfiler, process_io,
    io_delta, render_report,
)


def percentile(values: list[float], percent: float) -> float | None:
    """Nearest-rank percentile; deterministic and honest about small samples."""
    if not values:
        return None
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(percent / 100 * len(ordered)) - 1)], 2)


def summarize_samples(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "PASS"]
    # cProfile/tracemalloc can radically increase execution time; exclude
    # high-overhead targeted replays from normal distribution statistics.
    clean = [row for row in completed if not row.get("profiled")]
    times = [float(row["open_ms"]) for row in clean]
    return {
        "planned": len(rows),
        "passed": len(completed),
        "failed": len(rows) - len(completed),
        "normal_samples": len(clean),
        "profiled_samples": len(completed) - len(clean),
        "open_p50_ms": percentile(times, 50),
        "open_p95_ms": percentile(times, 95),
        "open_p99_ms": percentile(times, 99),
        "slowest_guides": [
            {"guide_id": row["guide_id"], "cycle": row["cycle"], "open_ms": row["open_ms"]}
            for row in sorted(clean, key=lambda row: row["open_ms"], reverse=True)[:10]
        ],
        "freeze_count_250ms": sum(
            int(row.get("open_ui", {}).get("stall_250ms", 0)) +
            int(row.get("home_ui", {}).get("stall_250ms", 0))
            for row in rows
        ),
    }


def ganymede_inventory(atlas_ids: set[str]) -> list[dict[str, Any]]:
    """Do not misreport reference-only Ganymede listings as runnable guides."""
    entries = load_ganymede_listings()
    result = []
    for entry in entries:
        atlas_id = ATLAS_EQUIVALENTS.get(entry.source_id)
        result.append({
            "source_id": entry.source_id,
            "title": entry.title,
            "listed_steps": entry.step_count,
            "atlas_equivalent": atlas_id,
            "coverage": "atlas_equivalent_benchmarked" if atlas_id in atlas_ids else "metadata_only_not_executable",
            "source_url": entry.source_url,
        })
    return result


class EventLoopLag:
    """Measure delayed Qt timer callbacks while the UI thread is processing a journey."""

    def __init__(self, interval_ms: int = 20):
        self.interval_ms = interval_ms
        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._on_tick)
        self.on_heartbeat = None
        self.previous = 0.0
        self.delays: list[float] = []
        self.ticks = 0

    def _on_tick(self) -> None:
        now = time.perf_counter()
        if self.previous:
            self.delays.append(max(0.0, (now - self.previous) * 1000 - self.interval_ms))
        self.previous = now
        self.ticks += 1
        if self.on_heartbeat is not None:
            self.on_heartbeat()

    def start(self) -> None:
        self.delays = []
        self.ticks = 0
        self.previous = time.perf_counter()
        self.timer.start()

    def stop(self) -> dict[str, Any]:
        # Pump once before stopping to capture delay from a synchronous blocker.
        QApplication.processEvents()
        self.timer.stop()
        values = list(self.delays)
        return {
            "qt_timer_interval_ms": self.interval_ms,
            "ticks": self.ticks,
            "lag_p50_ms": percentile(values, 50),
            "lag_p95_ms": percentile(values, 95),
            "lag_p99_ms": percentile(values, 99),
            "lag_max_ms": round(max(values), 2) if values else None,
            "stall_100ms": sum(value >= 100 for value in values),
            "stall_250ms": sum(value >= 250 for value in values),
            "stall_1000ms": sum(value >= 1000 for value in values),
            "coverage": "qt_offscreen_event_loop_proxy_no_real_screen_fps",
        }


class CpuRssSampler:
    """Sampler runs independently of Qt to catch main-thread CPU/RSS spikes."""

    def __init__(self, interval: float = 0.05):
        self.interval = interval
        self.phase = "startup"
        self.peaks: dict[str, dict[str, float]] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="AtlasDeepCpuSampler", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def set_phase(self, phase: str) -> None:
        with self.lock:
            self.phase = phase

    def get(self, phase: str) -> dict[str, float]:
        with self.lock:
            return dict(self.peaks.get(phase, {}))

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=3)

    def _run(self) -> None:
        last_wall = time.perf_counter()
        last_cpu = time.process_time()
        while not self.stop_event.wait(self.interval):
            wall, cpu = time.perf_counter(), time.process_time()
            busy = max(0.0, 100 * (cpu - last_cpu) / max(wall - last_wall, 0.001))
            last_wall, last_cpu = wall, cpu
            current_rss, _ = memory_mb()
            with self.lock:
                row = self.peaks.setdefault(self.phase, {"cpu_peak_pct_one_core": 0.0, "rss_peak_mb": 0.0})
                row["cpu_peak_pct_one_core"] = round(max(row["cpu_peak_pct_one_core"], busy), 2)
                if current_rss is not None:
                    row["rss_peak_mb"] = round(max(row["rss_peak_mb"], current_rss), 2)


def guide_visible(page: Any, guide_id: str) -> bool:
    view = getattr(page, "guides_view", None)
    if view is None or not bool(getattr(view, "_runtime_ready", False)):
        return False
    if str(getattr(page, "_pending_guide_id", "") or ""):
        return False
    if str(getattr(view, "current_guide_id", "") or "") != guide_id:
        return False
    if getattr(view, "state", None) != getattr(view, "GUIDE_OVERVIEW", object()):
        return False
    # A selected ID alone can be a false positive: demand an active detail widget.
    stack = getattr(view, "stack", None)
    if stack is None:
        return False
    current = stack.currentWidget()
    if guide_id == "guide_complet":
        return (current is not None and current is getattr(view, "guide_ultime_view", None)
                and bool(getattr(getattr(view, "guide_ultime_service", None), "available", False)))
    # Optimized route guides (e.g. Sylvestre) use a dedicated manual card
    # renderer, not detail_page. Verify both the real active widget AND its
    # populated/available runtime; do not mistakenly wait 45s for detail_page.
    manual_views = getattr(view, "_catalog_manual_views", {}) or {}
    if guide_id in manual_views:
        service = (getattr(view, "_catalog_manual_services", {}) or {}).get(guide_id)
        return (current is not None and current is manual_views[guide_id]
                and bool(getattr(service, "available", False))
                and bool(getattr(service, "cards", None)))
    return current is not None and current is getattr(view, "detail_page", None)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def export_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "guide_id", "title", "cycle", "status", "open_ms", "return_home_ms",
        "cpu_open_ms", "cpu_avg_pct_one_core", "cpu_peak_pct_one_core", "rss_before_mb", "rss_detail_mb",
        "rss_home_mb", "rss_peak_mb", "tree_detail_mb", "tree_home_mb",
        "ui_lag_p95_ms", "ui_lag_p99_ms", "ui_lag_max_ms", "ui_stalls_250ms", "error",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            ui = row.get("open_ui") or {}
            resources = row.get("open_resources") or {}
            writer.writerow({
                "guide_id": row["guide_id"], "title": row["title"], "cycle": row["cycle"],
                "status": row["status"], "open_ms": row.get("open_ms"),
                "return_home_ms": row.get("return_home_ms"),
                "cpu_open_ms": row.get("cpu_open_ms"),
                "cpu_avg_pct_one_core": row.get("cpu_avg_pct_one_core"),
                "cpu_peak_pct_one_core": resources.get("cpu_peak_pct_one_core"),
                "rss_before_mb": row.get("rss_before_mb"),
                "rss_detail_mb": row.get("rss_detail_mb"), "rss_home_mb": row.get("rss_home_mb"),
                "rss_peak_mb": resources.get("rss_peak_mb"),
                "tree_detail_mb": row.get("tree_detail_mb"), "tree_home_mb": row.get("tree_home_mb"),
                "ui_lag_p95_ms": ui.get("lag_p95_ms"), "ui_lag_p99_ms": ui.get("lag_p99_ms"),
                "ui_lag_max_ms": ui.get("lag_max_ms"), "ui_stalls_250ms": (
                    int(ui.get("stall_250ms", 0)) + int((row.get("home_ui") or {}).get("stall_250ms", 0))
                ), "error": row.get("error", ""),
            })


def guide_checkpoint_targets(guide: Any, view: Any, count: int) -> list[tuple[str, Any]]:
    """Select safe, representative UI destinations; never mark steps completed."""
    if count == 0:
        return []
    guide_id = str(guide.id)
    manual_views = getattr(view, "_catalog_manual_views", {}) or {}
    manual_services = getattr(view, "_catalog_manual_services", {}) or {}
    if guide_id == "guide_complet" or guide_id in manual_views:
        manual_view = (getattr(view, "guide_ultime_view", None) if guide_id == "guide_complet"
                       else manual_views.get(guide_id))
        service = (getattr(view, "guide_ultime_service", None) if guide_id == "guide_complet"
                   else manual_services.get(guide_id))
        cards = getattr(service, "cards", ()) or ()
        navigate = getattr(manual_view, "_show_index", None)
        if not cards or not callable(navigate):
            return []
        indices = sorted({0, len(cards) // 2, len(cards) - 1})
        return [(f"card_{index + 1}_of_{len(cards)}", lambda i=index: navigate(i))
                for index in indices]
    series = [
        segment for part in getattr(guide, "parts", ())
        for chapter in getattr(part, "chapters", ())
        for segment in getattr(chapter, "series", ())
    ]
    select = getattr(view, "select_series", None)
    if not series or not callable(select):
        return []
    indices = sorted({0, len(series) // 2, len(series) - 1})
    return [(f"series_{index + 1}_of_{len(series)}",
             lambda item=series[index]: select(item.id))
            for index in indices]


def run(*, cycles: int, output: Path, timeout: float,
        diagnose_slow_ms: float = 1000.0,
        diagnose_guides: frozenset[str] = frozenset(),
        checkpoints: int = 3, profile_startup: bool = False) -> dict[str, Any]:
    started_all = time.perf_counter()
    startup_profiler = StartupCpuProfiler(enabled=profile_startup)
    startup_profiler.begin()
    app = QApplication.instance() or QApplication([])
    after_qt = time.perf_counter()
    window = app_main.AtlasWindow()
    timeline: dict[str, float] = {
        "qt_application_init_ms": round((after_qt - started_all) * 1000, 2),
        "atlas_window_constructor_ms": round((time.perf_counter() - after_qt) * 1000, 2),
    }
    lag = EventLoopLag()
    watchdog = QtStallStackSampler(threshold_ms=150)
    lag.on_heartbeat = watchdog.heartbeat
    attributor = SpanAttributor()
    hooks = ExitStack()
    slow_guides: set[str] = set()
    cpu = CpuRssSampler()
    tree = PeakTreeSampler()
    rows: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "schema_version": 1, "git_head": git_head(), "status": "RUNNING",
        "environment": {"os": sys.platform, "qt_platform": os.environ.get("QT_QPA_PLATFORM"),
                        "python": sys.version.split()[0], "cycles": cycles},
        "measurement_limits": [
            "Qt offscreen timer delays are not actual display FPS or Windows native message-pump stalls",
            "CPU percentage is process consumption relative to one logical core, not machine-wide use",
            "Process-tree peak excludes external launcher siblings unless they are descendants",
            "Guide opens measure selection and Qt-ready state, not display scan-out",
            "Ganymede metadata-only entries are not executable Atlas guide routes",
        ],
        "samples": rows,
        "timeline": timeline,
        "diagnostic_policy": {"slow_ms": diagnose_slow_ms, "checkpoints": checkpoints,
                              "startup_instrumented": profile_startup,
                              "targeted_guides": sorted(diagnose_guides),
                              "profiled_samples_not_comparable": True},
    }
    cpu.start()
    tree.start()
    watchdog.start()
    try:
        time_checkpoint = time.perf_counter()
        window.show()
        app.processEvents()
        timeline["first_qt_events_ms"] = round((time.perf_counter() - time_checkpoint) * 1000, 2)
        time_checkpoint = time.perf_counter()
        wait_until(app, lambda: preload_terminal(window), timeout=120, label="Atlas preloads")
        timeline["functional_preload_ms"] = round((time.perf_counter() - time_checkpoint) * 1000, 2)
        time_checkpoint = time.perf_counter()
        open_encyclopedia(app, window, GUIDES_TAB)
        timeline["guide_catalogue_ready_ms"] = round((time.perf_counter() - time_checkpoint) * 1000, 2)
        page = window.page_widgets.get("Quetes")
        if page is None:
            raise RuntimeError("Encyclopedia page was not created")
        provider = page.service.guide_provider
        time_checkpoint = time.perf_counter()
        guides = provider.load_all()
        timeline["provider_load_all_ms"] = round((time.perf_counter() - time_checkpoint) * 1000, 2)
        guide_ids = [str(guide.id) for guide in guides]
        if not guide_ids or len(set(guide_ids)) != len(guide_ids):
            raise RuntimeError("Empty or duplicated playable Guide catalogue")
        # The provider could silently omit invalid entries: compare against the
        # enabled manifest instead of claiming full coverage of a partial load.
        manifest_path = ROOT / "data/encyclopedia/guides/catalog.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_ids = [
            str(row["id"]) for row in manifest["guides"]
            if row.get("enabled", True) is True
        ]
        payload["manifest_enabled_guide_ids"] = expected_ids
        if not expected_ids or len(expected_ids) != len(set(expected_ids)):
            raise RuntimeError("Invalid or duplicated enabled Guide manifest")
        if set(expected_ids) != set(guide_ids):
            raise RuntimeError(
                "Playable Guide coverage differs from enabled manifest: "
                f"missing={sorted(set(expected_ids)-set(guide_ids))}, "
                f"extra={sorted(set(guide_ids)-set(expected_ids))}"
            )
        payload["atlas_catalogue_count"] = len(guide_ids)
        payload["atlas_guide_ids"] = guide_ids
        payload["ganymede_sources"] = ganymede_inventory(set(guide_ids))
        payload["ganymede_source_count"] = len(payload["ganymede_sources"])
        if profile_startup:
            payload["startup_cpu_functions"] = startup_profiler.finish()
            payload["measurement_limits"].append(
                "Startup cProfile modifies elapsed durations: compare CPU hotspots, not startup P95 baseline"
            )
        write_json(output, payload)
        from app.modules.encyclopedia.views.guides_view import GuidesView
        from app.modules.encyclopedia.views.manual_route_guides_view import ManualRouteGuidesView
        from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
        from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
            GuideCatalogManualRuntimeService,
        )
        from app.modules.encyclopedia.providers.quest_provider import QuestProvider
        hooks.enter_context(attributor.instrument(page.__class__, (
            "navigate_to_guide", "open_pending_lazy_tab", "ensure_full_guides_view",
            "_start_full_guide_runtime",
        )))
        hooks.enter_context(attributor.instrument(GuidesView, (
            "select_guide", "_select_guide_standard", "_show_guide_overview_standard",
            "_render_continuous_source_guide", "_render_header", "_render_breadcrumb",
            "_populate_guide_left", "_populate_series_quests",
            "_populate_guide_navigation", "_populate_guide_info",
            "ensure_guide_ultime_view",
        )))
        hooks.enter_context(attributor.instrument(ManualRouteGuidesView, (
            "select_guide", "ensure_catalog_manual_view",
            "_catalog_route_map_count", "_refresh_catalog_route_home_labels",
        )))
        # Split the Sylvestre 20-second first-open into source quest lookup,
        # position/step transformation and Qt widget construction. These are
        # measurements only; no runtime or UI behavior is changed.
        hooks.enter_context(attributor.instrument(GuideCatalogManualRuntimeService, (
            "_load_manual_preview", "_quest_segments", "_merge_consecutive_positions",
            "_segment_to_card", "_finalize_segment", "_merge_segment",
        )))
        hooks.enter_context(attributor.instrument(QuestProvider, ("get_catalog", "get_quest")))
        hooks.enter_context(attributor.instrument(SharedGuideManualView, (
            "_build_ui", "_render_window", "_render_preparation",
            "_load_preparation_needs",
        )))
        hooks.enter_context(attributor.instrument(provider.__class__, ("get_by_id", "load_all")))

        for cycle in range(1, cycles + 1):
            for guide in guides:
                guide_id = str(guide.id)
                phase = f"{cycle}:{guide_id}"
                row: dict[str, Any] = {
                    "guide_id": guide_id, "title": str(guide.title),
                    "cycle": cycle, "status": "FAIL",
                }
                rows.append(row)
                try:
                    before = memory_snapshot("deep_before")
                    row["rss_before_mb"] = before["process_rss_mb"]
                    cpu.set_phase(phase + ":open")
                    open_cpu = time.process_time()
                    began = time.perf_counter()
                    before_io = process_io()
                    profile = None  # Never reuse a profile from an earlier guide on failure.
                    is_profiled = (guide_id in diagnose_guides or
                                   (cycle > 1 and guide_id in slow_guides))
                    row["profiled"] = bool(is_profiled)
                    watchdog.begin(phase + ":open")
                    lag.start()
                    with attributor.active(phase + ":open"), TargetedProfile(enabled=is_profiled) as profile:
                        try:
                            if not page.navigate_to_guide(guide_id):
                                raise RuntimeError("Navigation rejected the guide")
                            wait_until(
                                app, lambda: guide_visible(page, guide_id),
                                timeout=timeout, label=f"Guide {guide_id} detail",
                                poll_seconds=0.01,
                            )
                            if cycle == 1 and "first_guide_reachable_ms" not in timeline:
                                timeline["first_guide_reachable_ms"] = round(
                                    (time.perf_counter() - started_all) * 1000, 2)
                        finally:
                            row["open_ms"] = round((time.perf_counter() - began) * 1000, 2)
                            row["cpu_open_ms"] = round((time.process_time() - open_cpu) * 1000, 2)
                            row["cpu_avg_pct_one_core"] = round(
                                100 * row["cpu_open_ms"] / max(row["open_ms"], 0.01), 2)
                            pump(app, 0.06)  # Keep short opens observable by Qt timer.
                            row["open_ui"] = lag.stop()
                            watchdog.end()
                            row["stall_stacks"] = watchdog.get(phase + ":open")
                            row["open_io"] = io_delta(before_io, process_io())
                    if is_profiled:
                        row["targeted_profile"] = profile.result
                        # An instrumented run must not be treated as a normal timing.
                    row["method_hotspots"] = attributor.top(phase + ":open")
                    row["open_resources"] = cpu.get(phase + ":open")
                    row["checkpoints"] = []
                    if checkpoints:
                        view = getattr(page, "guides_view", None)
                        targets = guide_checkpoint_targets(guide, view, checkpoints)
                        if not targets:
                            row["checkpoint_coverage"] = "UNAVAILABLE_OR_NO_STEPS"
                        for label, change in targets[:checkpoints]:
                            subphase = phase + ":checkpoint:" + label
                            cpu.set_phase(subphase)
                            watchdog.begin(subphase)
                            lag.start()
                            point_started = time.perf_counter()
                            try:
                                with attributor.active(subphase):
                                    change()
                                    pump(app, 0.04)
                                detail = memory_snapshot("deep_checkpoint")
                                row["checkpoints"].append({
                                    "label": label, "status": "PASS",
                                    "elapsed_ms": round((time.perf_counter() - point_started) * 1000, 2),
                                    "rss_mb": detail.get("process_rss_mb"),
                                    "tree_mb": detail.get("tree_rss_mb"),
                                    "method_hotspots": attributor.top(subphase),
                                    "cpu": cpu.get(subphase),
                                })
                            except Exception as check_error:
                                row["checkpoints"].append({
                                    "label": label, "status": "FAIL",
                                    "error": f"{type(check_error).__name__}: {check_error}",
                                })
                                raise RuntimeError(f"Checkpoint {label} failed: {check_error}") from check_error
                            finally:
                                row["checkpoints"][-1]["qt_lag"] = lag.stop()
                                row["checkpoints"][-1]["stall_stacks"] = watchdog.get(subphase)
                                watchdog.end()
                    cpu.set_phase(phase + ":checkpoint")
                    detail = memory_snapshot("deep_detail")
                    row["rss_detail_mb"] = detail["process_rss_mb"]
                    row["tree_detail_mb"] = detail["tree_rss_mb"]
                    cpu.set_phase(phase + ":home")
                    watchdog.begin(phase + ":home")
                    lag.start()
                    began = time.perf_counter()
                    home_io_before = process_io()
                    try:
                        with attributor.active(phase + ":home"):
                            window.show_page("Home")
                            pump(app, 0.30)
                    finally:
                        row["return_home_ms"] = round((time.perf_counter() - began) * 1000, 2)
                        row["home_ui"] = lag.stop()
                        watchdog.end()
                        row["home_stall_stacks"] = watchdog.get(phase + ":home")
                        row["home_io"] = io_delta(home_io_before, process_io())
                    row["home_method_hotspots"] = attributor.top(phase + ":home")
                    cpu.set_phase(phase + ":home-checkpoint")
                    home = memory_snapshot("deep_home")
                    row["rss_home_mb"] = home["process_rss_mb"]
                    row["tree_home_mb"] = home["tree_rss_mb"]
                    # Re-enter the same real UI in the next sample; don't mock rendering.
                    open_encyclopedia(app, window, GUIDES_TAB)
                    page = window.page_widgets.get("Quetes")
                    if page is None:
                        raise RuntimeError("Encyclopedia page lost after Home")
                    row["status"] = "PASS"
                except Exception as exc:
                    lag.stop()
                    watchdog.end()
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    row["method_hotspots"] = attributor.top(phase + ":open")
                    row["stall_stacks"] = watchdog.get(phase + ":open")
                    row["open_resources"] = cpu.get(phase + ":open")
                    if profile is not None and row.get("profiled"):
                        row["targeted_profile"] = profile.result
                    try:
                        window.show_page("Home")
                        pump(app, 0.10)
                        open_encyclopedia(app, window, GUIDES_TAB)
                        page = window.page_widgets.get("Quetes")
                    except Exception as recovery_exc:
                        row["recovery_error"] = str(recovery_exc)
                finally:
                    cpu.set_phase("between_guides")
                    if cycle == 1 and (row.get("status") != "PASS" or
                            float(row.get("open_ms") or 0) >= diagnose_slow_ms):
                        slow_guides.add(guide_id)
                    payload["summary"] = summarize_samples(rows)
                    write_json(output, payload)
    finally:
        if startup_profiler.profiler is not None:
            payload["startup_cpu_functions"] = startup_profiler.finish()
        hooks.close()
        watchdog.end()
        watchdog.close()
        lag.timer.stop()
        cpu.close()
        tree.stop()
        payload["peak_process_tree_mb"] = round(tree.peak_tree_rss_mb, 2)
        payload["peak_atlas_process_mb"] = round(tree.peak_process_rss_mb, 2)
        payload["summary"] = summarize_samples(rows)
        payload["coverage_complete"] = (
            len(rows) == payload.get("atlas_catalogue_count", -1) * cycles
            and all(row["status"] == "PASS" for row in rows)
        )
        payload["status"] = "PASS" if payload["coverage_complete"] else "FAIL"
        write_json(output, payload)
        try:
            window._shutdown_background_services()
        except Exception:
            pass
        window.hide()
        window.deleteLater()
        app.processEvents()
    export_csv(output.with_suffix(".csv"), rows)
    output.with_suffix(".html").write_text(render_report(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Every playable Guide: RSS, CPU, latency, Qt stalls")
    parser.add_argument("--output", type=Path, default=Path("artifacts/atlas_exhaustive/guides.json"))
    parser.add_argument("--cycles", type=int, choices=(1, 2, 5, 10), default=2)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--checkpoints", type=int, choices=(0, 3), default=3)
    parser.add_argument("--profile-startup", action="store_true",
                        help="Opt-in slow startup CPU profile (not comparable to ordinary latency)")
    parser.add_argument("--diagnose-slow-ms", type=float, default=1000.0,
                        help="Profile guides that exceeded this in cycle one, during subsequent cycles")
    parser.add_argument("--diagnose-guide", action="append", default=[],
                        help="Force high-overhead CPU/allocation profile of an exact Atlas guide id")
    options = parser.parse_args()
    result = run(cycles=options.cycles, output=options.output, timeout=options.timeout,
                 diagnose_slow_ms=options.diagnose_slow_ms,
                 diagnose_guides=frozenset(options.diagnose_guide),
                 checkpoints=options.checkpoints, profile_startup=options.profile_startup)
    print(json.dumps({
        "status": result["status"], "git_head": result["git_head"],
        "atlas_guides": result.get("atlas_catalogue_count"),
        "ganymede_source_listings": result.get("ganymede_source_count"),
        "summary": result["summary"],
        "peak_tree_mb": result["peak_process_tree_mb"],
    }, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
