"""Read-only, bounded Qt/cache inventory for Doctor's RAM investigations.

Intentionally measures *ownership indicators*, never pretends to apportion
native RSS by Python object count. Called after the real RSS checkpoint so
object enumeration cannot contaminate the measured checkpoint.
"""
from __future__ import annotations

import gc
import sys
from collections import Counter
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
        return {
            "status": "OBSERVED_PARTIAL",
            "label": str(label),
            "qt": _qt_owners(window, widgets),
            "native_image_indicators": _native_image_indicators(window),
            "page_lifecycle": _page_lifecycle(window),
            "gc_generation_counts": list(gc.get_count()),
            "loaded_python_modules": len(sys.modules),
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
        seen[label] = {
            "rss_process_mib": memory.get("process_rss_mb"),
            "rss_process_tree_mib": memory.get("tree_rss_mb"),
            "qt_widgets": qt.get("total_live_widgets"),
        }
    first = seen.get("initial_home")
    last = seen.get("last_home")
    result: dict[str, object] = {"status": "PARTIAL", "checkpoints": seen}
    if first is not None and last is not None:
        beginning = first.get("rss_process_tree_mib")
        ending = last.get("rss_process_tree_mib")
        if all(type(x) in (int, float) for x in (beginning, ending)):
            result["home_rss_delta_mib"] = round(float(ending) - float(beginning), 2)
        a, b = first.get("qt_widgets"), last.get("qt_widgets")
        if type(a) is int and type(b) is int:
            result["home_widget_count_delta"] = b - a
    return result


__all__ = ["ram_ownership_snapshot", "ram_checkpoints_summary", "ROUTE_CHECKPOINTS"]
