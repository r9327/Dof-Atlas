"""Manual, exhaustive Windows/Qt guide benchmark.

Not a replacement for the canonical short Phase 8 certification.
Qt offscreen event-loop lag is a proxy for stalls, NOT real display FPS.
"""
from __future__ import annotations

import argparse
import csv
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
    times = [float(row["open_ms"]) for row in completed]
    return {
        "planned": len(rows),
        "passed": len(completed),
        "failed": len(rows) - len(completed),
        "open_p50_ms": percentile(times, 50),
        "open_p95_ms": percentile(times, 95),
        "open_p99_ms": percentile(times, 99),
        "slowest_guides": [
            {"guide_id": row["guide_id"], "cycle": row["cycle"], "open_ms": row["open_ms"]}
            for row in sorted(completed, key=lambda row: row["open_ms"], reverse=True)[:10]
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
        self.previous = 0.0
        self.delays: list[float] = []
        self.ticks = 0

    def _on_tick(self) -> None:
        now = time.perf_counter()
        if self.previous:
            self.delays.append(max(0.0, (now - self.previous) * 1000 - self.interval_ms))
        self.previous = now
        self.ticks += 1

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

    def __init__(self, interval: float = 0.10):
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
    return stack is not None and stack.currentWidget() is not None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def export_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "guide_id", "title", "cycle", "status", "open_ms", "return_home_ms",
        "cpu_open_ms", "cpu_peak_pct_one_core", "rss_before_mb", "rss_detail_mb",
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


def run(*, cycles: int, output: Path, timeout: float) -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    window = app_main.AtlasWindow()
    lag = EventLoopLag()
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
    }
    cpu.start()
    tree.start()
    try:
        window.show()
        app.processEvents()
        wait_until(app, lambda: preload_terminal(window), timeout=120, label="Atlas preloads")
        open_encyclopedia(app, window, GUIDES_TAB)
        page = window.page_widgets.get("Quetes")
        if page is None:
            raise RuntimeError("Encyclopedia page was not created")
        provider = page.service.guide_provider
        guides = provider.load_all()
        guide_ids = [str(guide.id) for guide in guides]
        if not guide_ids or len(set(guide_ids)) != len(guide_ids):
            raise RuntimeError("Empty or duplicated playable Guide catalogue")
        payload["atlas_catalogue_count"] = len(guide_ids)
        payload["atlas_guide_ids"] = guide_ids
        payload["ganymede_sources"] = ganymede_inventory(set(guide_ids))
        payload["ganymede_source_count"] = len(payload["ganymede_sources"])
        write_json(output, payload)

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
                    lag.start()
                    if not page.navigate_to_guide(guide_id):
                        raise RuntimeError("Navigation rejected the guide")
                    wait_until(
                        app, lambda: guide_visible(page, guide_id),
                        timeout=timeout, label=f"Guide {guide_id} detail",
                        poll_seconds=0.01,
                    )
                    row["open_ms"] = round((time.perf_counter() - began) * 1000, 2)
                    row["cpu_open_ms"] = round((time.process_time() - open_cpu) * 1000, 2)
                    row["open_ui"] = lag.stop()
                    row["open_resources"] = cpu.get(phase + ":open")
                    cpu.set_phase(phase + ":checkpoint")
                    detail = memory_snapshot("deep_detail")
                    row["rss_detail_mb"] = detail["process_rss_mb"]
                    row["tree_detail_mb"] = detail["tree_rss_mb"]
                    cpu.set_phase(phase + ":home")
                    lag.start()
                    began = time.perf_counter()
                    window.show_page("Home")
                    pump(app, 0.30)
                    row["return_home_ms"] = round((time.perf_counter() - began) * 1000, 2)
                    row["home_ui"] = lag.stop()
                    cpu.set_phase(phase + ":home-checkpoint")
                    home = memory_snapshot("deep_home")
                    row["rss_home_mb"] = home["process_rss_mb"]
                    row["tree_home_mb"] = home["tree_rss_mb"]
                    row["status"] = "PASS"
                    # Re-enter the same real UI in the next sample; don't mock rendering.
                    open_encyclopedia(app, window, GUIDES_TAB)
                    page = window.page_widgets.get("Quetes")
                    if page is None:
                        raise RuntimeError("Encyclopedia page lost after Home")
                except Exception as exc:
                    lag.stop()
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    try:
                        window.show_page("Home")
                        pump(app, 0.10)
                        open_encyclopedia(app, window, GUIDES_TAB)
                        page = window.page_widgets.get("Quetes")
                    except Exception as recovery_exc:
                        row["recovery_error"] = str(recovery_exc)
                finally:
                    cpu.set_phase("between_guides")
                    payload["summary"] = summarize_samples(rows)
                    write_json(output, payload)
    finally:
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
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Every playable Guide: RSS, CPU, latency, Qt stalls")
    parser.add_argument("--output", type=Path, default=Path("artifacts/atlas_exhaustive/guides.json"))
    parser.add_argument("--cycles", type=int, choices=(1, 2, 5, 10), default=2)
    parser.add_argument("--timeout", type=float, default=45.0)
    options = parser.parse_args()
    result = run(cycles=options.cycles, output=options.output, timeout=options.timeout)
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
