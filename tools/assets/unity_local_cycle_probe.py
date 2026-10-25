"""Local-only, isolated Qt/Windows Guide catalog lifecycle probe.

Real production Guide/Encyclopedia widgets and data are used. This is not
full AtlasWindow / EXE certification, and is never scheduled by GitHub Actions.
Run on Windows from the repository root with Python 3.13 and the pinned runtime:
    py -3.13 tools/assets/unity_local_cycle_probe.py --output artifacts/unity-local
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


def working_set_bytes() -> int | None:
    """Windows private-process working-set measurement; not Python heap size."""
    if sys.platform != "win32":
        return None

    class Counters(ctypes.Structure):
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

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        process, ctypes.byref(counters), counters.cb
    ):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def run(output: Path, cycles: int) -> dict:
    # All source imports are delayed until after the data-root isolation.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["ATLAS_THEME"] = "dofus_unity"
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget
    from shiboken6 import isValid
    from tools.atlas_doctor_lib.doctor_ui_qt import build_scene, settle
    from app.modules.encyclopedia.constants import GUIDES_TAB
    from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView

    output.mkdir(parents=True, exist_ok=True)
    samples: list[dict] = []
    result = {
        "status": "BLOCKED", "cycles_requested": cycles, "cycles_completed": 0,
        "source": "real Qt EncyclopediaPage and GuideCatalogView",
        "mode": "Qt offscreen on local Windows; not a full AtlasWindow or installed EXE",
        "ci_run": False, "platform": platform.platform(),
        "qt_scale_factor": os.environ.get("QT_SCALE_FACTOR", "(default)"),
        "screenshots": [], "samples": samples,
    }
    page = None
    try:
        with tempfile.TemporaryDirectory(prefix="atlas-unity-probe-") as directory:
            os.environ["DOFUS_ATLAS_USER_ROOT"] = directory
            app, page, owner = build_scene(Path(directory))
            # build_scene already loaded the real provider and hydrated the
            # rich Guide; synchronize the application's readiness bit.
            if not owner._runtime_ready:
                raise RuntimeError("real rich Guide runtime not ready")
            page._guide_runtime_ready = True
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            page._restore_guides_catalog_home()
            if not isinstance(page.guides_view, GuideCatalogView):
                raise RuntimeError("real lightweight catalog not restored")
            page.resize(1200, 800)
            settle()

            screen = app.primaryScreen()
            if screen is None:
                raise RuntimeError("no Qt screen")
            result["qt_logical_dpi"] = screen.logicalDotsPerInch()
            result["qt_pixel_ratio"] = screen.devicePixelRatio()
            result["limits"] = (
                "Offscreen DPI is simulated; actual monitor 100/125/150% and "
                "EXE packaging require independent real-device verification."
            )

            def screenshot(label: str) -> None:
                name = label + ".png"
                pix = page.grab()
                if pix.isNull() or not pix.save(str(output / name)):
                    raise RuntimeError(f"Qt grab failed: {name}")
                result["screenshots"].append(name)

            def measure(index: int) -> None:
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                settle()
                samples.append({
                    "cycle": index,
                    "widgets": len(page.findChildren(QWidget)) + 1,
                    "working_set_bytes": working_set_bytes(),
                })

            screenshot("catalog-before")
            measure(0)
            for idx in range(cycles):
                catalog = page.guides_view
                if not isinstance(catalog, GuideCatalogView):
                    raise RuntimeError(f"cycle {idx + 1}: missing real catalog")
                guide_id = "guide_complet" if idx % 2 == 0 else "dofus_sylvestre"
                card = catalog.featured_cards[guide_id]
                if not card.open_button.isEnabled():
                    raise RuntimeError(f"cycle {idx + 1}: {guide_id} disabled")
                QTest.mouseClick(card.open_button, Qt.LeftButton)
                if not settle(
                    lambda: page.guides_view is not catalog
                    and getattr(page.guides_view, "_runtime_ready", False),
                    timeout=12.0,
                ):
                    raise RuntimeError(f"cycle {idx + 1}: real Guide did not open")
                if idx == 0:
                    screenshot("guide-open")
                rich = page.guides_view
                if not hasattr(rich, "catalogRequested"):
                    raise RuntimeError("Guide missing catalogRequested navigation signal")
                # Exercise the actual wired signal, not a direct model reset.
                rich.catalogRequested.emit()
                if not settle(lambda: isinstance(page.guides_view, GuideCatalogView), timeout=8.0):
                    raise RuntimeError(f"cycle {idx + 1}: catalog return failed")
                if not page.guides_view._runtime_ready:
                    raise RuntimeError(f"cycle {idx + 1}: catalog returned unhydrated")
                measure(idx + 1)
                result["cycles_completed"] += 1
            screenshot("catalog-after")
            result["widget_delta_after_cycles"] = (
                samples[-1]["widgets"] - samples[0]["widgets"]
            )
            if (samples[0]["working_set_bytes"] is not None
                    and samples[-1]["working_set_bytes"] is not None):
                result["working_set_delta_bytes"] = (
                    samples[-1]["working_set_bytes"] - samples[0]["working_set_bytes"]
                )
            result["status"] = "MEASURED_NOT_CERTIFIED"
            page.close()
            page.deleteLater()
            settle()
            page = None
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if page is not None and isValid(page):
            page.close()
            page.deleteLater()
            settle()
        result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (output / "report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=30)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("this local working-set and Qt probe requires Windows")
    if not 1 <= args.cycles <= 30:
        parser.error("cycles must be 1..30")
    report = run(args.output, args.cycles)
    print(f"{report['status']} {report['cycles_completed']}/{args.cycles} cycles")
    print(f"Evidence: {args.output / 'report.json'}")
    return 0 if report["status"] == "MEASURED_NOT_CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
