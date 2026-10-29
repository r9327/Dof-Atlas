"""Short, read-only real Qt navigation census for every visible Atlas main-menu route.

This is a CI-only measurement companion to existing Phase 8 and Doctor tests.
It does NOT imply that placeholders work, the executable boots on a real desktop,
or that an individual tab's complete business logic has been exercised.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
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

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from benchmark_phase8_preload import (
    app_main, encyclopedia_ready, git_head, page_loaded, preload_terminal, pump,
    wait_until,
)
from benchmark_phase8_memory import PeakTreeSampler, memory_snapshot
from benchmark_atlas_exhaustive import CpuRssSampler, EventLoopLag

# Inventory is intentionally explicit: a new menu entry must receive a review
# instead of disappearing silently from the benchmark.
ROUTES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("home", "page", "Home", "Home", False),
    ("organizer", "page", "Organizer", "Organizer", False),
    ("guide", "encyclopedia", "GUIDES", "Quetes", False),
    ("quests", "encyclopedia", "QUESTS", "Quetes", False),
    ("achievements", "encyclopedia", "ACHIEVEMENTS", "Quetes", False),
    ("dungeons", "encyclopedia", "DONJONS", "Quetes", False),
    ("monsters", "encyclopedia", "MONSTRES", "Quetes", False),
    ("archmonsters", "encyclopedia", "ARCHIMONSTRES", "Quetes", False),
    ("wanted", "encyclopedia", "AVIS DE RECHERCHE", "Quetes", False),
    ("crafts", "tools", "Crafts", "Craft", False),
    ("world_map", "tools", "Map monde", "Scan Monde", False),
    ("treasure_hunt", "tools", "Chasse au trésor", "Placeholder::Chasse au trésor", True),
    ("ocre", "tools", "Ocre", "Placeholder::Ocre", True),
    ("stuffs_pvm", "stuffs", "PvM", "Equipement", False),
    ("stuffs_pvp", "stuffs", "PvP", "Equipement", False),
    ("stuffs_builders", "stuffs", "Builders", "Equipement", False),
    ("almanax", "page", "Almanax", "Almanax", True),
    ("settings", "page", "Settings", "Settings", False),
    ("tutorials", "placeholder", "Tutoriels", "Placeholder::Tutoriels", True),
    ("dofus_noob", "placeholder", "Dofus Noob", "Placeholder::Dofus Noob", True),
)

def assert_inventory(routes: tuple[tuple[str, str, str, str, bool], ...] = ROUTES) -> None:
    ids = [row[0] for row in routes]
    if len(ids) != len(set(ids)) or len(ids) != 20:
        raise ValueError("Route inventory incomplete or duplicated")
    if any(not all(isinstance(v, str) and v for v in row[:4]) for row in routes):
        raise ValueError("Invalid route inventory")
    if any(row[1] not in {"page", "encyclopedia", "tools", "stuffs", "placeholder"} for row in routes):
        raise ValueError("Unknown route category")

def open_route(app: QApplication, window: Any, entry: tuple[str, str, str, str, bool], timeout: float) -> None:
    key, group, label, page, placeholder = entry
    if group == "encyclopedia":
        from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
        actual = {"GUIDES": GUIDES_TAB, "QUESTS": QUESTS_TAB, "ACHIEVEMENTS": ACHIEVEMENTS_TAB}.get(label, label)
        window.open_encyclopedia_tab(actual)
        wait_until(app, lambda: encyclopedia_ready(window, actual),
                   timeout=timeout, label=key, poll_seconds=0.015)
    elif group == "tools":
        window.open_tools_tab(label)
        wait_until(app, lambda: page_loaded(window, page),
                   timeout=timeout, label=key, poll_seconds=0.015)
    elif group == "stuffs":
        window.open_stuffs_tab(label)
        wait_until(app, lambda: page_loaded(window, page)
                   and str(getattr(window.page_widgets.get(page), "section", label)) == label,
                   timeout=timeout, label=key, poll_seconds=0.015)
    elif group == "placeholder":
        window.show_placeholder(label, "Banc de navigation", "Tutoriels")
    else:
        window.show_page(label)
        wait_until(app, lambda: page_loaded(window, page),
                   timeout=timeout, label=key, poll_seconds=0.015)
    app.processEvents()
    if window.active_page_name() != page:
        raise RuntimeError(f"{key}: active page {window.active_page_name()!r} != {page!r}")
    widget = window.page_widgets.get(page)
    if widget is None:
        raise RuntimeError(f"{key}: missing real Qt page")
    is_placeholder = widget.objectName() == "PlaceholderPage"
    if is_placeholder != placeholder:
        raise RuntimeError(f"{key}: placeholder classification mismatch")

def run(*, output: Path, timeout: float = 18.0, max_seconds: float = 540.0) -> dict[str, Any]:
    assert_inventory()
    if not 5 <= timeout <= 45 or not 120 <= max_seconds <= 600:
        raise ValueError("Unbounded or invalid timing options")
    output = output.resolve()
    if not output.is_relative_to((ROOT / "artifacts").resolve()) or output.suffix != ".json":
        raise ValueError("JSON output must stay under artifacts/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    start = time.perf_counter()
    sampler = PeakTreeSampler()
    cpu = CpuRssSampler()
    app = QApplication.instance() or QApplication([])
    report: dict[str, Any] = {
        "schema": 1, "kind": "atlas_quick_full_app_navigation",
        "git_head": git_head(), "qt_platform": os.environ["QT_QPA_PLATFORM"],
        "expected_routes": [x[0] for x in ROUTES],
        "routes": [], "preload_states": {}, "measurement_limits": [
            "Qt offscreen is not a GPU/FPS/real desktop validation",
            "Visible placeholder pages are checked as navigation, not working features",
            "One character and one Atlas process; not 8 Dofus clients",
            "Each screen is checked for real navigation/ready state, not all internal functions",
            "Runner is not a constrained low-end PC",
        ]
    }
    window = None
    try:
        sampler.set_phase("startup")
        sampler.start()
        cpu.start()
        born = time.perf_counter()
        window = app_main.AtlasWindow()
        window.show()
        pump(app, 0.05)
        report["constructor_to_visible_ms"] = round((time.perf_counter() - born) * 1000, 2)
        if not getattr(window, "preload_states", None):
            raise RuntimeError("Missing preload state inventory")
        sampler.set_phase("preload")
        cpu.set_phase("preload")
        preload_start = time.perf_counter()
        preload_lag = EventLoopLag()
        preload_lag.start()
        try:
            wait_until(app, lambda: preload_terminal(window), timeout=min(90.0, max_seconds / 3),
                       label="functional preload", poll_seconds=0.025)
        finally:
            report["preload_qt"] = preload_lag.stop()
        report["preload_ms"] = round((time.perf_counter() - preload_start) * 1000, 2)
        report["preload_cpu_rss"] = cpu.get("preload")
        report["preload_states"] = {str(k): str(v) for k, v in window.preload_states.items()}
        report["preload_errors"] = {
            str(k): [str(e)[:300] for e in v.get("errors", [])[:5]]
            for k, v in getattr(window, "preload_results", {}).items()
            if isinstance(v, dict) and v.get("errors")
        }
        report["preload_fail_diagnostics"] = {
            str(k): {
                "skipped_reason": str(v.get("_skipped_reason") or "")[:300],
                "prepared": v.get("_prepared"),
                "has_errors": bool(v.get("errors")),
            }
            for k, v in getattr(window, "preload_results", {}).items()
            if isinstance(v, dict) and k in report["preload_states"]
        }
        report["preload_status"] = ("PASS" if report["preload_states"]
                                    and all(v == "READY" for v in report["preload_states"].values())
                                    else "FAIL")
        report["after_preload"] = memory_snapshot("quick_after_preload")

        for entry in ROUTES:
            route_id, group, label, page, placeholder = entry
            if time.perf_counter() - start > max_seconds:
                report["routes"].append({"id": route_id, "status": "FAIL", "error": "GLOBAL_TIME_BUDGET"})
                continue
            sampler.set_phase(route_id)
            cpu.set_phase(route_id)
            lag = EventLoopLag()
            lag.start()
            opened = time.perf_counter()
            row: dict[str, Any] = {
                "id": route_id, "category": group, "label": label,
                "placeholder": placeholder, "status": "FAIL"
            }
            try:
                open_route(app, window, entry, timeout)
                row["status"] = "PLACEHOLDER" if placeholder else "PASS"
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:350]
            finally:
                row["open_ms"] = round((time.perf_counter() - opened) * 1000, 2)
                row["qt"] = lag.stop()
                row["cpu_rss"] = cpu.get(route_id)
                row["active"] = memory_snapshot("quick_active")
                try:
                    window.show_page("Home")
                    pump(app, 0.10)
                    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                    row["home"] = memory_snapshot("quick_home")
                    if window.active_page_name() != "Home":
                        raise RuntimeError("Home not active after route")
                except Exception as exc:
                    row["status"] = "FAIL"
                    row["home_error"] = f"{type(exc).__name__}: {exc}"[:350]
                report["routes"].append(row)
        report["elapsed_seconds"] = round(time.perf_counter() - start, 2)
    except Exception as exc:
        report["fatal"] = f"{type(exc).__name__}: {exc}"[:600]
    finally:
        cpu.close()
        sampler.stop()
        if window is not None:
            try:
                cleanup = getattr(window, "_shutdown_background_services", None)
                if callable(cleanup):
                    cleanup()
                window.hide()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
            except Exception as exc:
                report["shutdown_error"] = f"{type(exc).__name__}: {exc}"[:350]
        report["peak_process_rss_mib"] = round(sampler.peak_process_rss_mb, 2)
        report["peak_process_tree_rss_mib"] = round(sampler.peak_tree_rss_mb, 2)
        report["worst_tree_phase"] = sampler.peak_tree_sample.get("phase")
        report["measured_routes"] = len(report["routes"])
        report["functional_pass"] = sum(r["status"] == "PASS" for r in report["routes"])
        report["placeholder_pass"] = sum(r["status"] == "PLACEHOLDER" for r in report["routes"])
        report["failed_routes"] = [r["id"] for r in report["routes"] if r["status"] == "FAIL"]
        report["status"] = ("PASS" if
             report.get("preload_status") == "PASS" and
             report["measured_routes"] == len(ROUTES) and
             not report["failed_routes"] and not report.get("fatal") and
             not report.get("shutdown_error") else "FAIL")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/quick_app/report.json"))
    parser.add_argument("--timeout", type=float, default=18.0)
    parser.add_argument("--max-seconds", type=float, default=540.0)
    args = parser.parse_args()
    report = run(output=args.output, timeout=args.timeout, max_seconds=args.max_seconds)
    print(json.dumps({k: report.get(k) for k in (
        "status", "git_head", "preload_ms", "preload_states", "functional_pass",
        "placeholder_pass", "failed_routes", "fatal", "peak_process_tree_rss_mib",
        "elapsed_seconds")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
