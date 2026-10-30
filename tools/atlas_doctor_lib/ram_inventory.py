"""Read-only, bounded Qt/cache inventory for Doctor's RAM investigations.

Intentionally measures *ownership indicators*, never pretends to apportion
native RSS by Python object count. Called after the real RSS checkpoint so
object enumeration cannot contaminate the measured checkpoint.
"""
from __future__ import annotations

import gc
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import QApplication, QWidget

# Explicitly small, bounded and deterministic. No heap walk, rich-catalog
# import, image decoding, database fetch, QPixmap conversion, or caching.
CLASS_LIMIT = 20
OWNER_LIMIT = 25
ROUTE_CHECKPOINTS = frozenset(("organizer", "guide", "world_map", "crafts"))


def _top(counter: Counter[str], limit: int) -> list[dict[str, object]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    ]


def _qt_owners(window: object, widgets: list[QWidget]) -> dict[str, object]:
    pages = getattr(window, "page_widgets", {})
    pages = pages if isinstance(pages, dict) else {}
    owner_ids = {id(widget): str(key) for key, widget in pages.items()
                 if isinstance(widget, QWidget)}
    count_by_page: Counter[str] = Counter()
    count_by_class: Counter[str] = Counter()
    for widget in widgets:
        count_by_class[type(widget).__name__] += 1
        parent = widget
        label = "unowned_shell_or_popup"
        while parent is not None:
            owner = owner_ids.get(id(parent))
            if owner is not None:
                label = owner
                break
            parent = parent.parentWidget()
        count_by_page[label] += 1
    return {
        "total_live_widgets": len(widgets),
        "by_page": _top(count_by_page, OWNER_LIMIT),
        "by_class": _top(count_by_class, CLASS_LIMIT),
        "unowned_or_shell": count_by_page.get("unowned_shell_or_popup", 0),
    }


def _native_image_indicators(window: object) -> dict[str, object]:
    result: dict[str, object] = {"qt_global_pixmap_cache_limit_kib": int(QPixmapCache.cacheLimit())}
    module = sys.modules.get("app.modules.encyclopedia.services.image_service")
    service = getattr(module, "ENCYCLOPEDIA_IMAGE_SERVICE", None) if module is not None else None
    info = getattr(service, "info", None)
    result["encyclopedia_image_cache"] = (
        {"status": "OBSERVED", **info()} if callable(info)
        else {"status": "NOT_LOADED"}
    )
    pages = getattr(window, "page_widgets", {})
    pages = pages if isinstance(pages, dict) else {}
    world = pages.get("Scan Monde")
    canvas = getattr(world, "canvas", None)
    pixmap = getattr(canvas, "pixmap", None)
    if pixmap is None:
        result["world_canvas"] = {"status": "NOT_LOADED"}
    else:
        width = int(pixmap.width())
        height = int(pixmap.height())
        result["world_canvas"] = {
            "status": "OBSERVED",
            "width": width, "height": height,
            "estimated_rgba_bytes": width * height * 4,
            "image_suspended": bool(getattr(world, "_image_suspended", False)),
        }
    return result


def _page_lifecycle(window: object) -> dict[str, object]:
    factories = getattr(window, "page_factories", {})
    factories = factories if isinstance(factories, dict) else {}
    pages = getattr(window, "page_widgets", {})
    pages = pages if isinstance(pages, dict) else {}
    names = ("Organizer", "Quetes", "Craft", "Scan Monde", "Equipement")
    return {
        name: {
            "state": "LAZY" if name in factories else "LOADED" if name in pages else "ABSENT",
            "page_class": type(pages[name]).__name__ if name in pages else "",
        }
        for name in names
    }


def ram_ownership_snapshot(window: object, label: str) -> dict[str, object]:
    """Bounded diagnostic after RSS sampling; no native byte attribution."""
    app = QApplication.instance()
    if app is None:
        return {"status": "UNAVAILABLE", "reason": "NO_QAPPLICATION", "label": label}
    widgets = QApplication.allWidgets()
    try:
        from tools.atlas_doctor_lib.ram_forensics import private_windows_memory
        return {
            "status": "OBSERVED_PARTIAL",
            "label": str(label),
            "qt": _qt_owners(window, widgets),
            "native_image_indicators": _native_image_indicators(window),
            "windows_process_private": private_windows_memory(),
            "page_lifecycle": _page_lifecycle(window),
            "gc_generation_counts": list(gc.get_count()),
            "loaded_python_modules": len(sys.modules),
            # Keep the full application-only list: a rising module count
            # may explain one-time RSS growth without a Qt-widget leak.
            # This is an import inventory, NOT native memory attribution.
            "loaded_application_modules": sorted(
                key for key in sys.modules
                if key == "app" or key.startswith("app.")
            ),
            "limits": [
                "Qt widget counts cannot identify native RSS ownership or prove a leak",
                "QPixmapCache is a capacity, not currently allocated native memory",
                "Image counts do not include Qt shared platform pixmaps or GPU textures",
                "tracemalloc, a native heap profiler and real Windows GUI require separate runs",
            ],
        }
    finally:
        # Explicitly drop the temporary enumeration list and Qt wrappers.
        del widgets


def ram_checkpoints_summary(items: list[dict[str, object]]) -> dict[str, object]:
    """Do not add RSS and Qt object counts together or invent ownership shares."""
    seen: dict[str, dict[str, object]] = {}
    app_modules_by_label: dict[str, set[str]] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "")
        snapshot = entry.get("ownership")
        memory = entry.get("memory")
        if not label or not isinstance(snapshot, dict) or not isinstance(memory, dict):
            continue
        if snapshot.get("status") != "OBSERVED_PARTIAL":
            continue
        qt = snapshot.get("qt")
        if not isinstance(qt, dict):
            continue
        windows_private = snapshot.get("windows_process_private")
        loaded = snapshot.get("loaded_application_modules")
        if isinstance(loaded, list) and all(isinstance(x, str) for x in loaded):
            app_modules_by_label[label] = set(loaded)
        seen[label] = {
            "rss_process_mib": memory.get("process_rss_mb"),
            "rss_process_tree_mib": memory.get("tree_rss_mb"),
            "private_commit_mib": (
                windows_private.get("private_commit_mib")
                if isinstance(windows_private, dict)
                and windows_private.get("status") == "OBSERVED"
                else None
            ),
            "qt_widgets": qt.get("total_live_widgets"),
        }
    first = seen.get("initial_home")
    last = seen.get("last_home")
    result: dict[str, object] = {"status": "PARTIAL", "checkpoints": seen}
    if first is not None and last is not None:
        if "initial_home" in app_modules_by_label and "last_home" in app_modules_by_label:
            newly_loaded = sorted(
                app_modules_by_label["last_home"] - app_modules_by_label["initial_home"]
            )
            result["app_modules_imported_between_home_checkpoints"] = newly_loaded
            result["app_modules_imported_count"] = len(newly_loaded)
            result["module_imports_are_not_native_rss_attribution"] = True
        private_before, private_after = (
            first.get("private_commit_mib"), last.get("private_commit_mib")
        )
        if all(type(x) in (int, float) for x in (private_before, private_after)):
            result["home_private_commit_delta_mib"] = round(
                float(private_after) - float(private_before), 3
            )
        beginning = first.get("rss_process_tree_mib")
        ending = last.get("rss_process_tree_mib")
        if all(type(x) in (int, float) for x in (beginning, ending)):
            result["home_rss_delta_mib"] = round(float(ending) - float(beginning), 2)
        a, b = first.get("qt_widgets"), last.get("qt_widgets")
        if type(a) is int and type(b) is int:
            result["home_widget_count_delta"] = b - a
    return result




def ram_scope_status(path: Path | None = None) -> dict[str, object]:
    """Fail closed on missing, duplicated or truncated workstream inventories."""
    manifest = (
        Path(path) if path is not None else
        Path(__file__).resolve().parents[2] /
        "docs/performance/atlas-ram-inventory-v1.json"
    )
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        rows = payload["workstreams"]
        if payload.get("schema") != 1 or not isinstance(rows, list):
            raise ValueError("RAM register schema invalid")
        expected = [f"RAM-{i:02d}" for i in range(1, 51)]
        ids = [row["id"] for row in rows]
        if ids != expected:
            raise ValueError("RAM register missing, re-ordered or duplicated IDs")
        status = Counter()
        for row in rows:
            if not isinstance(row, dict) or row.get("status") not in {
                "measured", "instrumented", "todo"
            }:
                raise ValueError("RAM register contains unknown coverage status")
            if not all(str(row.get(key, "")).strip()
                       for key in ("priority", "domain", "title", "evidence", "owner")):
                raise ValueError(f"RAM register evidence missing: {row['id']}")
            status[row["status"]] += 1
        return {
            "status": "PARTIAL" if status["todo"] or status["instrumented"] else "EVIDENCE_REVIEW_REQUIRED",
            "workstreams_total": len(rows),
            "with_existing_evidence": status["measured"],
            "instrumented_not_certified": status["instrumented"],
            "not_instrumented": status["todo"],
            "missing_ids": [],
            "pending_ids": [row["id"] for row in rows if row["status"] != "measured"],
            "native_heap_attribution_confirmed": False,
            "real_windows_release_certified": False,
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"}


__all__ = [
    "ram_ownership_snapshot", "ram_checkpoints_summary",
    "ram_scope_status", "ROUTE_CHECKPOINTS",
]

