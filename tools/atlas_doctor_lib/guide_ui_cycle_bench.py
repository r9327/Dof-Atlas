"""Doctor: bounded Windows Qt Guide/catalogue lifecycle benchmark.

Exercises the real Encyclopedia and Guide view switch, not an imitation of
the catalog. Runs only on explicitly selected Guide UI CI jobs.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import statistics
import tempfile
import time
import traceback
from pathlib import Path


def resident_bytes() -> int | None:
    """Current process RSS including native Qt allocations (not Python-only tracemalloc)."""
    if os.name == "nt":
        class MemoryCounters(ctypes.Structure):
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
        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters), counters.cb,
        ):
            return int(counters.WorkingSetSize)
        return None
    if sys_platform_linux():
        try:
            pages = int(Path("/proc/self/statm").read_text().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            return None
    return None


def sys_platform_linux() -> bool:
    return platform.system() == "Linux"


def measure(cycles: int) -> dict:
    # Keep all real profiles, progress and runtime caches in a disposable root.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from shiboken6 import isValid
    from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
    from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
    from app.modules.encyclopedia.constants import GUIDES_TAB
    from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
    from tools.atlas_doctor_lib.doctor_ui_qt import build_scene, settle

    records: list[dict] = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="atlas-doctor-guide-cycle-") as folder:
        os.environ["DOFUS_ATLAS_USER_ROOT"] = folder
        os.environ["DOFUS_ATLAS_VALIDATION_DATA_DIR"] = folder
        app, page, _owner = build_scene(Path(folder))
        try:
            # All three providers are real and already loaded in build_scene.
            # Tell the production page those data are ready, rather than faking
            # a Guide widget or using the asynchronous internet/Windows preload.
            page._restore_guides_catalog_home()
            catalog = page.guides_view
            if not isinstance(catalog, GuideCatalogView):
                raise RuntimeError("Production lightweight catalog not mounted")
            page.apply_preloaded_related_data(
                achievement_provider=page.service.achievement_provider,
                guide_provider=page.service.guide_provider,
                quest_graph=page._quest_graph,
            )
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            settle()
            for turn in range(cycles):
                catalog = page.guides_view
                if not isinstance(catalog, GuideCatalogView) or not catalog._runtime_ready:
                    raise RuntimeError(f"Catalog not hydrated after return {turn}")
                route = "guide_complet" if turn % 2 == 0 else "dofus_sylvestre"
                before = time.perf_counter()
                if not catalog.select_guide(route):
                    raise RuntimeError(f"Catalog cannot dispatch {route}")
                if not settle(lambda: page.guides_view is not catalog, timeout=8.0):
                    raise RuntimeError(f"Guide did not open at cycle {turn}")
                owner = page.guides_view
                if not settle(
                    lambda: isinstance(owner.stack.currentWidget(), SharedGuideManualView),
                    timeout=8.0,
                ):
                    raise RuntimeError(f"Real Guide page missing at cycle {turn}")
                detail = owner.stack.currentWidget()
                opened_ms = round((time.perf_counter() - before) * 1000, 2)
                if not detail.service.cards:
                    raise RuntimeError(f"Empty Guide route at cycle {turn}")
                # Go back through the *production* Guide signal, not an
                # artificially detached test catalog or a direct fake widget.
                owner.show_home()
                if not settle(
                    lambda: isinstance(page.guides_view, GuideCatalogView),
                    timeout=8.0,
                ):
                    raise RuntimeError(f"Catalog did not return at cycle {turn}")
                settle()
                if isValid(owner):
                    raise RuntimeError(f"Old heavy Guide widget retained at cycle {turn}")
                back = page.guides_view
                if not back._runtime_ready or back.home_dofus_model.rowCount() == 0:
                    raise RuntimeError(f"Catalog returned empty at cycle {turn}")
                records.append({
                    "cycle": turn + 1, "route": route, "open_ms": opened_ms,
                    "return_ms": round((time.perf_counter() - before) * 1000 - opened_ms, 2),
                    "rss_bytes": resident_bytes(),
                    "catalog_qt_widgets": len(back.findChildren(type(back))),
                    "dofus_count": back.home_dofus_model.rowCount(),
                })
            sizes = [r["rss_bytes"] for r in records]
            observed = [v for v in sizes if v is not None]
            # Compare warmed tail to warmed baseline; a single allocator
            # high-water mark isn't evidence of a leak.
            warm = [v for v in sizes[min(4, len(sizes) - 1):] if v is not None]
            baseline = min(warm[:max(1, min(5, len(warm)))]) if warm else None
            growth = max(warm[-min(5, len(warm)):]) - baseline if baseline is not None else None
            times = [r["open_ms"] for r in records]
            return {
                "status": "PASS" if all(ms < 10000 for ms in times) else "FAIL",
                "cycles_completed": len(records), "requested_cycles": cycles,
                "source": "Doctor / production EncyclopediaPage and SharedGuideManualView",
                "platform": platform.platform(), "qt": "offscreen; not installed EXE",
                "seconds_total": round(time.monotonic() - started, 2),
                "opening_ms": {
                    "min": min(times), "median": round(statistics.median(times), 2),
                    "max": max(times),
                },
                "rss_bytes": {
                    "first": sizes[0], "last": sizes[-1],
                    "peak_observed": max(observed) if observed else None,
                    "warmed_baseline": baseline, "warmed_growth": growth,
                    "growth_target_bytes": 32 * 1024 * 1024,
                },
                "image_cache": ENCYCLOPEDIA_IMAGE_SERVICE.info(),
                "cycles": records,
                "not_covered": ["installed user EXE", "physical GPU/DPI", "game client"],
            }
        finally:
            page.close()
            page.deleteLater()
            settle()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 30:
        parser.error("--cycles must be between 1 and 30")
    try:
        report = measure(args.cycles)
    except Exception as exc:
        report = {
            "status": "BLOCKED", "requested_cycles": args.cycles,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cycles"}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" and report["cycles_completed"] == args.cycles else 1


if __name__ == "__main__":
    raise SystemExit(main())
