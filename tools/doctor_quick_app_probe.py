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
from tools.atlas_doctor_lib.ram_inventory import (
    ROUTE_CHECKPOINTS, ram_ownership_snapshot, ram_checkpoints_summary,
    ram_scope_status,
)

# Inventory is intentionally explicit: a new menu entry must receive a review
# instead of disappearing silently from the benchmark.
ROUTES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("home", "page", "Home", "Home", False),
    ("organizer", "page", "Organizer", "Organizer", False),
    ("guide", "encyclopedia", "GUIDES", "Quetes", False),
    ("quests", "encyclopedia", "QUESTS", "Quetes", False),
    ("achievements", "encyclopedia", "ACHIEVEMENTS", "Quetes", False),
    ("dungeons", "encyclopedia", "DONJONS", "Quetes", True),
    ("monsters", "encyclopedia", "MONSTRES", "Quetes", True),
    ("archmonsters", "encyclopedia", "ARCHIMONSTRES", "Quetes", True),
    ("wanted", "encyclopedia", "AVIS DE RECHERCHE", "Quetes", True),
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

def startup_domain_breakdown(payload: object) -> dict[str, object]:
    """Attribute the exact launcher warmup to source domain workers.

    This is not reconstructed from a generic .cache timestamp: the calling
    window already validates the session token, so stale/foreign measurements
    never masquerade as evidence for this launch.
    """
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        return {"status": "UNAVAILABLE", "domains": {}}
    raw = payload.get("domains")
    if not isinstance(raw, dict):
        return {"status": "UNAVAILABLE", "domains": {}}
    domains: dict[str, object] = {}
    for domain in ("guide", "quest", "success"):
        info = raw.get(domain)
        if not isinstance(info, dict):
            continue
        elapsed = info.get("elapsed_ms")
        if type(elapsed) not in (int, float) or elapsed < 0:
            continue
        domains[domain] = {
            "mode": str(info.get("mode") or "unknown"),
            "elapsed_ms": float(elapsed),
            "worker_elapsed_ms": float(info.get("worker_elapsed_ms") or 0),
            "timings_ms": {
                str(name): float(value)
                for name, value in (
                    info.get("timings_ms") if isinstance(info.get("timings_ms"), dict)
                    else {}
                ).items()
                if isinstance(name, str) and type(value) in (int, float) and value >= 0
            },
        }
    return {
        "status": "OBSERVED" if len(domains) == 3 else "PARTIAL",
        "warmup_elapsed_ms": float(payload.get("elapsed_ms") or 0),
        "domains": domains,
    }


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
    if group == "encyclopedia" and label in {
        "DONJONS", "MONSTRES", "ARCHIMONSTRES", "AVIS DE RECHERCHE",
    }:
        # Bestiary has a real Encyclopedia shell but a placeholder inner tab.
        # A navigation-only census must not call it a functional module.
        tabs = getattr(widget, "tabs", None)
        inner = tabs.currentWidget() if tabs is not None else None
        is_placeholder = (
            inner is not None
            and inner.objectName() == "EncyclopediaUnavailableBestiary"
        )
    if is_placeholder != placeholder:
        raise RuntimeError(f"{key}: placeholder classification mismatch")

def home_handoff_ready(window: Any) -> bool:
    """Observe the actual Quest→Home gate, not a benchmark-forced show()."""
    states = getattr(window, "preload_states", {})
    return bool(
        isinstance(states, dict)
        and states.get("quests") in {"READY", "FAILED"}
        and getattr(window, "_home_revealed", False)
    )


def summarize_revisits(rows: list[dict[str, Any]], cycles: int) -> dict[str, Any]:
    """Describe cold/warm timings and observed Home drift, without calling it a leak."""
    by_route: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") not in {"PASS", "PLACEHOLDER"}:
            continue
        by_route.setdefault(str(row["id"]), []).append(row)
    summary: dict[str, Any] = {}
    for route_id, samples in sorted(by_route.items()):
        samples.sort(key=lambda x: x["cycle"])
        if len(samples) != cycles:
            continue
        home = [s.get("home_stabilized") or {} for s in samples]
        memory = [h.get("tree_rss_mb") for h in home]
        if not all(isinstance(n, (int, float)) and n >= 0 for n in memory):
            continue
        times = [float(s["open_ms"]) for s in samples]
        summary[route_id] = {
            "cold_open_ms": times[0],
            "warm_open_ms": times[-1],
            "warm_vs_cold_ms": round(times[-1] - times[0], 2),
            "home_stabilized_tree_rss_mib_by_cycle": memory,
            "home_tree_delta_first_to_last_mib": round(memory[-1] - memory[0], 2),
            "scope": "observed_0_75s_post_home_not_proof_of_memory_leak",
        }
    return summary


def pin_single_cpu_core() -> dict[str, int]:
    """Actually restrict the current Windows process, not a pretend slow-PC profile."""
    if os.name != "nt":
        raise RuntimeError("Windows CPU affinity simulation requires Windows")
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessAffinityMask.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    handle = kernel.GetCurrentProcess()
    allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
    if not kernel.GetProcessAffinityMask(handle, ctypes.byref(allowed), ctypes.byref(system)):
        raise OSError(ctypes.get_last_error(), "GetProcessAffinityMask failed")
    if not allowed.value:
        raise RuntimeError("No allowed CPU core")
    selected = allowed.value & -allowed.value
    if not kernel.SetProcessAffinityMask(handle, selected):
        raise OSError(ctypes.get_last_error(), "SetProcessAffinityMask failed")
    verified, system_after = ctypes.c_size_t(), ctypes.c_size_t()
    if not kernel.GetProcessAffinityMask(handle, ctypes.byref(verified), ctypes.byref(system_after)) or verified.value != selected:
        raise RuntimeError("One-core CPU affinity was not applied")
    return {"allowed_mask": allowed.value, "measured_process_mask": verified.value,
            "kind": "one_logical_cpu_affinity_not_low_end_hardware"}


def run(*, output: Path, timeout: float = 18.0, max_seconds: float = 540.0,
        cycles: int = 3, idle_seconds: float = 0.0,
        one_core: bool = False, ram_forensics: bool = False) -> dict[str, Any]:
    assert_inventory()
    if (not 5 <= timeout <= 45 or not 120 <= max_seconds <= 1800
            or cycles not in (1, 2, 3, 5, 10) or not 0 <= idle_seconds <= 120):
        raise ValueError("Unbounded or invalid timing options")
    output = output.resolve()
    if not output.is_relative_to((ROOT / "artifacts").resolve()) or output.suffix != ".json":
        raise ValueError("JSON output must stay under artifacts/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    start = time.perf_counter()
    cpu_started_all = time.process_time()
    sampler = PeakTreeSampler()
    cpu = CpuRssSampler()
    app = QApplication.instance() or QApplication([])
    profiler = None
    if ram_forensics:
        from tools.atlas_doctor_lib.ram_forensics import RamForensics
        profiler = RamForensics(ROOT)
    report: dict[str, Any] = {
        "schema": 2, "kind": "atlas_quick_full_app_navigation",
        "git_head": git_head(), "qt_platform": os.environ["QT_QPA_PLATFORM"],
        "cycles": cycles, "planned_samples": len(ROUTES) * cycles,
        "home_stabilization_wait_ms": 750, "idle_seconds_requested": idle_seconds,
        "is_certification": False, "one_core_requested": one_core,
        "ram_forensics_enabled": ram_forensics,
        "timing_comparable": not ram_forensics,
        "expected_routes": [x[0] for x in ROUTES],
        "routes": [], "preload_states": {}, "ram_ownership_checkpoints": [],
        "measurement_limits": [
            "Qt offscreen is not a GPU/FPS/real desktop validation",
            "Visible placeholder pages are checked as navigation, not working features",
            "One character and one Atlas process; not 8 Dofus clients",
            "Each screen is checked for real navigation/ready state, not all internal functions",
            "Runner is not a constrained low-end PC",
            "Short post-Home idle observations do not prove a native Qt memory leak",
            "Home handoff is a Qt readiness gate; benchmark-forced show() does not prove a real first desktop paint",
        ]
    }
    window = None
    try:
        if one_core:
            report["cpu_affinity"] = pin_single_cpu_core()
        if profiler is not None:
            profiler.start()
        sampler.set_phase("startup")
        sampler.start()
        cpu.start()
        born = time.perf_counter()
        born_cpu = time.process_time()
        window = app_main.AtlasWindow()
        window.show()
        pump(app, 0.05)
        report["constructor_to_visible_ms"] = round((time.perf_counter() - born) * 1000, 2)
        report["constructor_cpu_ms"] = round((time.process_time() - born_cpu) * 1000, 2)
        if not getattr(window, "preload_states", None):
            raise RuntimeError("Missing preload state inventory")
        sampler.set_phase("preload")
        cpu.set_phase("preload")
        preload_start = time.perf_counter()
        preload_cpu_started = time.process_time()
        preload_lag = EventLoopLag()
        preload_lag.start()
        report["home_handoff_ms_from_constructor"] = None

        def observe_preload() -> bool:
            if report["home_handoff_ms_from_constructor"] is None and home_handoff_ready(window):
                report["home_handoff_ms_from_constructor"] = round(
                    (time.perf_counter() - born) * 1000, 2,
                )
            return preload_terminal(window)

        try:
            wait_until(app, observe_preload, timeout=min(90.0, max_seconds / 3),
                       label="functional preload", poll_seconds=0.025)
            observe_preload()
        finally:
            report["preload_qt"] = preload_lag.stop()
        report["home_handoff_status"] = (
            "OBSERVED_GATE_ONLY" if report["home_handoff_ms_from_constructor"] is not None
            else "NOT_OBSERVED"
        )
        report["preload_ms"] = round((time.perf_counter() - preload_start) * 1000, 2)
        report["preload_domain_breakdown"] = startup_domain_breakdown(
            app_main._startup_cache_warmup_payload()
        )
        report["preload_cpu_ms"] = round((time.process_time() - preload_cpu_started) * 1000, 2)
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
        if profiler is not None:
            profiler.capture("initial_home")
        report["ram_ownership_checkpoints"].append({
            "label": "initial_home", "memory": report["after_preload"],
            "ownership": ram_ownership_snapshot(window, "initial_home"),
        })

        for cycle in range(1, cycles + 1):
            for entry in ROUTES:
                route_id, group, label, page, placeholder = entry
                if time.perf_counter() - start > max_seconds:
                    report["routes"].append({
                        "cycle": cycle, "id": route_id, "status": "FAIL",
                        "error": "GLOBAL_TIME_BUDGET",
                    })
                    continue
                phase = f"{route_id}:cycle{cycle}"
                sampler.set_phase(phase)
                cpu.set_phase(phase)
                lag = EventLoopLag()
                lag.start()
                opened = time.perf_counter()
                opened_cpu = time.process_time()
                row: dict[str, Any] = {
                    "cycle": cycle, "id": route_id, "category": group,
                    "label": label, "placeholder": placeholder, "status": "FAIL",
                }
                try:
                    open_route(app, window, entry, timeout)
                    row["status"] = "PLACEHOLDER" if placeholder else "PASS"
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"[:350]
                finally:
                    row["open_ms"] = round((time.perf_counter() - opened) * 1000, 2)
                    row["open_cpu_ms"] = round((time.process_time() - opened_cpu) * 1000, 2)
                    row["qt"] = lag.stop()
                    row["cpu_rss"] = cpu.get(phase)
                    row["active"] = memory_snapshot("quick_active")
                    if profiler is not None and cycle == 1 and route_id in ROUTE_CHECKPOINTS:
                        profiler.capture(f"{route_id}_active")
                    home_at = time.perf_counter()
                    home_cpu_at = time.process_time()
                    try:
                        window.show_page("Home")
                        pump(app, 0.10)
                        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                        row["home"] = memory_snapshot("quick_home")
                        if window.active_page_name() != "Home":
                            raise RuntimeError("Home not active after route")
                        pump(app, 0.75)
                        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                        row["home_stabilized"] = memory_snapshot("quick_home_stabilized")
                        if window.active_page_name() != "Home":
                            raise RuntimeError("Home not active after settling")
                        if cycle == 1 and route_id in ROUTE_CHECKPOINTS:
                            if profiler is not None:
                                profiler.capture(f"{route_id}_after_home")
                            # RSS is captured *before* enumerating Qt widgets.
                            report["ram_ownership_checkpoints"].append({
                                "label": f"{route_id}_home_after_first",
                                "memory": row["home_stabilized"],
                                "ownership": ram_ownership_snapshot(
                                    window, f"{route_id}_home_after_first"
                                ),
                            })
                    except Exception as exc:
                        row["status"] = "FAIL"
                        row["home_error"] = f"{type(exc).__name__}: {exc}"[:350]
                    finally:
                        row["return_home_ms"] = round((time.perf_counter() - home_at) * 1000, 2)
                        row["return_home_cpu_ms"] = round((time.process_time() - home_cpu_at) * 1000, 2)
                    report["routes"].append(row)
        report["revisit_comparison"] = summarize_revisits(report["routes"], cycles)
        final_home_memory = next(
            (row["home_stabilized"] for row in reversed(report["routes"])
             if "home_stabilized" in row), None,
        )
        if isinstance(final_home_memory, dict):
            if profiler is not None:
                profiler.capture("last_home")
            report["ram_ownership_checkpoints"].append({
                "label": "last_home", "memory": final_home_memory,
                "ownership": ram_ownership_snapshot(window, "last_home"),
            })
        report["ram_ownership_summary"] = ram_checkpoints_summary(
            report["ram_ownership_checkpoints"]
        )
        # A longer idle observation is separate from the fast 750ms post-route
        # snapshot, and never presented as evidence of a native-memory leak.
        if idle_seconds:
            if time.perf_counter() - start + idle_seconds > max_seconds:
                raise RuntimeError("INSUFFICIENT_GLOBAL_BUDGET_FOR_IDLE_OBSERVATION")
            report["idle_samples"] = []
            observed = 0.0
            idle_started_at = time.perf_counter()
            idle_cpu_at = time.process_time()
            for point in (0.0, idle_seconds / 2.0, idle_seconds):
                if point > observed:
                    pump(app, point - observed)
                observed = point
                report["idle_samples"].append({
                    "offset_seconds": round(point, 2),
                    "memory": memory_snapshot("quick_idle_home"),
                })
            report["idle_observation_ms"] = round((time.perf_counter() - idle_started_at) * 1000, 2)
            report["idle_cpu_ms"] = round((time.process_time() - idle_cpu_at) * 1000, 2)
            baseline = report["idle_samples"][0]["memory"].get("tree_rss_mb")
            ending = report["idle_samples"][-1]["memory"].get("tree_rss_mb")
            if isinstance(baseline, (int, float)) and isinstance(ending, (int, float)):
                report["idle_tree_rss_delta_mib"] = round(ending - baseline, 2)
        report["elapsed_seconds"] = round(time.perf_counter() - start, 2)
    except Exception as exc:
        report["fatal"] = f"{type(exc).__name__}: {exc}"[:600]
    finally:
        if profiler is not None:
            report["ram_forensics"] = profiler.finish()
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
        report.setdefault("elapsed_seconds", round(time.perf_counter() - start, 2))
        report["process_cpu_total_ms"] = round((time.process_time() - cpu_started_all) * 1000, 2)
        report["peak_process_rss_mib"] = round(sampler.peak_process_rss_mb, 2)
        report["peak_process_tree_rss_mib"] = round(sampler.peak_tree_rss_mb, 2)
        report["worst_tree_phase"] = sampler.peak_tree_sample.get("phase")
        from tools.atlas_doctor_lib.cost_attribution import cost_attribution
        report["cost_attribution"] = cost_attribution(report)
        report["measured_routes"] = len(report["routes"])
        report["functional_pass"] = sum(r["status"] == "PASS" for r in report["routes"])
        report["placeholder_pass"] = sum(r["status"] == "PLACEHOLDER" for r in report["routes"])
        report["failed_routes"] = [f"{r['id']}:cycle{r.get('cycle', '?')}" for r in report["routes"] if r["status"] == "FAIL"]
        report.setdefault("revisit_comparison", summarize_revisits(report["routes"], cycles))
        report["ram_scope"] = ram_scope_status()
        # Functional benchmark PASS never implies all 50 forensic RAM audits
        # (or real GUI/Windows heap attribution) have been completed.
        report["ram_audit_complete"] = False
        report["last_home_stabilized"] = next(
            (r["home_stabilized"] for r in reversed(report["routes"])
             if "home_stabilized" in r), None,
        )
        report["status"] = ("PASS" if
             report.get("preload_status") == "PASS" and
             (not idle_seconds or len(report.get("idle_samples", [])) == 3) and
             report["measured_routes"] == len(ROUTES) * cycles and
             not report["failed_routes"] and not report.get("fatal") and
             not report.get("shutdown_error") else "FAIL")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/quick_app/report.json"))
    parser.add_argument("--timeout", type=float, default=18.0)
    parser.add_argument("--max-seconds", type=float, default=540.0)
    parser.add_argument("--cycles", type=int, choices=(1, 2, 3, 5, 10), default=3)
    parser.add_argument("--idle-seconds", type=float, default=0.0)
    parser.add_argument("--one-core", action="store_true")
    parser.add_argument("--ram-forensics", action="store_true",
                        help="Profilage Python tracemalloc en session isolee; timings non comparables.")
    args = parser.parse_args()
    report = run(output=args.output, timeout=args.timeout, max_seconds=args.max_seconds,
                 cycles=args.cycles, idle_seconds=args.idle_seconds,
                 one_core=args.one_core, ram_forensics=args.ram_forensics)
    print(json.dumps({k: report.get(k) for k in (
        "status", "git_head", "cycles", "preload_ms", "preload_states", "functional_pass",
        "placeholder_pass", "failed_routes", "fatal", "peak_process_tree_rss_mib",
        "elapsed_seconds")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
