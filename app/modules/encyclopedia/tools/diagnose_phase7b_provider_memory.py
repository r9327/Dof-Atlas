from __future__ import annotations

import gc
import json
import sys
import threading
import time
from collections import Counter
from dataclasses import fields, is_dataclass
from typing import Any, Callable

from PySide6.QtWidgets import QApplication

from app.constants import ROOT_DIR
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB
from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider
from app.modules.encyclopedia.providers.dofus_item_provider import DofusItemProvider
from app.modules.encyclopedia.providers.guide_provider import GuideProvider
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from app.modules.encyclopedia.tools import benchmark_guides_performance as bench
from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard, GuideUltimeManualView
from app.modules.encyclopedia.views.guides_view import GuidesView
from main import AtlasWindow

OUTPUT = ROOT_DIR / "artifacts" / "phase7b_provider_memory_diagnostic.json"
REFERENCE_HEAD = "a278dc7ae462d0a05ddad8a22ba664b179b5ccca"


def rss() -> float | None:
    return bench.current_rss_mb()


def delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(b - a, 2)


def object_counts(app: QApplication) -> dict[str, Any]:
    objects = gc.get_objects()
    names = Counter(type(obj).__name__ for obj in objects)
    widgets = list(app.allWidgets())
    widget_names = Counter(type(obj).__name__ for obj in widgets)
    interesting = (
        "Achievement", "AchievementObjective", "Reward", "EntityRef",
        "Guide", "GuidePart", "GuideChapter", "GuideSeries", "GuideStep",
        "DofusItem", "GuideUltimeManualCard", "Future", "QTimer", "QPixmap", "QImage",
    )
    widget_interesting = (
        "QLabel", "QFrame", "QCheckBox", "QuestLine", "GuideHomeCard",
        "GuideStructureRow", "GuideUltimeManualCard", "AchievementDetailWidget",
    )
    return {
        "gc_objects": len(objects),
        "allocated_blocks": sys.getallocatedblocks(),
        "types": {name: names.get(name, 0) for name in interesting},
        "widgets": len(widgets),
        "widget_types": {name: widget_names.get(name, 0) for name in widget_interesting},
        "threads": [thread.name for thread in threading.enumerate()],
    }


def snapshot(app: QApplication) -> dict[str, Any]:
    return {"rss_mb": rss(), **object_counts(app)}


def deep_size(root: Any) -> int:
    seen: set[int] = set()
    stack = [root]
    total = 0
    while stack:
        obj = stack.pop()
        oid = id(obj)
        if oid in seen:
            continue
        seen.add(oid)
        try:
            total += sys.getsizeof(obj)
        except TypeError:
            continue
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
            continue
        if isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
            continue
        if is_dataclass(obj):
            for field in fields(obj):
                try:
                    stack.append(getattr(obj, field.name))
                except Exception:
                    pass
            continue
        values = getattr(obj, "__dict__", None)
        if isinstance(values, dict):
            stack.append(values)
    return total


def provider_footprints(window: AtlasWindow) -> dict[str, Any]:
    page = bench.current_encyclopedia_page(window)
    if page is None:
        return {}
    result: dict[str, Any] = {}
    achievement = page.service.achievement_provider
    if isinstance(achievement, AchievementProvider):
        fields_map = {
            "achievements": getattr(achievement, "_achievements", None),
            "by_id": getattr(achievement, "_by_id", None),
            "categories": getattr(achievement, "_categories", None),
            "by_category": getattr(achievement, "_by_category", None),
            "linked_quests": getattr(achievement, "_linked_quests", None),
            "linked_monsters": getattr(achievement, "_linked_monsters", None),
            "linked_dungeons": getattr(achievement, "_linked_dungeons", None),
            "linked_achievements": getattr(achievement, "_linked_achievements", None),
            "by_quest": getattr(achievement, "_by_quest", None),
        }
        result["achievement_provider"] = {
            "counts": {
                "achievements": len(getattr(achievement, "_achievements", ()) or ()),
                "categories": len(getattr(achievement, "_categories", {}) or {}),
                "by_quest": len(getattr(achievement, "_by_quest", {}) or {}),
            },
            "field_deep_mb": {
                key: round(deep_size(value) / (1024 * 1024), 2)
                for key, value in fields_map.items()
            },
            "combined_deep_mb": round(deep_size(fields_map) / (1024 * 1024), 2),
        }
    guide = page.service.guide_provider
    if isinstance(guide, GuideProvider):
        fields_map = {
            "guides": getattr(guide, "_guides", None),
            "by_id": getattr(guide, "_by_id", None),
            "by_category": getattr(guide, "_by_category", None),
            "by_entity": getattr(guide, "_by_entity", None),
            "validation_errors": getattr(guide, "validation_errors", None),
        }
        result["guide_provider"] = {
            "counts": {
                "guides": len(getattr(guide, "_guides", ()) or ()),
                "by_entity": len(getattr(guide, "_by_entity", {}) or {}),
            },
            "field_deep_mb": {
                key: round(deep_size(value) / (1024 * 1024), 2)
                for key, value in fields_map.items()
            },
            "combined_deep_mb": round(deep_size(fields_map) / (1024 * 1024), 2),
        }
        dofus = getattr(guide, "dofus_item_provider", None)
        if isinstance(dofus, DofusItemProvider):
            result["dofus_item_provider"] = {
                "count": len(getattr(dofus, "_items", ()) or ()),
                "combined_deep_mb": round(
                    deep_size({
                        "items": getattr(dofus, "_items", None),
                        "by_id": getattr(dofus, "_by_id", None),
                    }) / (1024 * 1024),
                    2,
                ),
            }
    return result


def wrap_method(cls: type, name: str, records: list[dict[str, Any]], app: QApplication) -> None:
    original = getattr(cls, name, None)
    if original is None:
        return

    def wrapped(self, *args, **kwargs):
        before = rss()
        widgets_before = len(app.allWidgets()) if threading.current_thread() is threading.main_thread() else None
        started = time.perf_counter()
        value = original(self, *args, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000.0, 2)
        after = rss()
        widgets_after = len(app.allWidgets()) if widgets_before is not None else None
        records.append({
            "name": f"{cls.__name__}.{name}",
            "thread": threading.current_thread().name,
            "ui_thread": threading.current_thread() is threading.main_thread(),
            "total_ms": elapsed,
            "rss_before_mb": before,
            "rss_after_mb": after,
            "rss_delta_mb": delta(before, after),
            "widgets_delta": (
                widgets_after - widgets_before
                if widgets_before is not None and widgets_after is not None
                else None
            ),
        })
        return value

    setattr(cls, name, wrapped)


def install(records: list[dict[str, Any]], app: QApplication) -> None:
    for method in (
        "load_all", "load_retained", "_ensure_loaded", "_load",
        "_load_categories", "_objectives_by_achievement", "_rewards_by_achievement",
        "_dungeon_links", "_named_rows",
    ):
        wrap_method(AchievementProvider, method, records, app)
    for method in (
        "load_all", "_ensure_loaded", "_load", "_guide_entries", "_load_guide",
        "_sections", "_parts", "validate_guide",
    ):
        wrap_method(GuideProvider, method, records, app)
    for method in ("load_all", "get_by_id", "_ensure_loaded", "_load"):
        wrap_method(DofusItemProvider, method, records, app)
    for method in (
        "__init__", "_build_quest_name_index", "_load_manual_preview",
        "_load_manual_preview_uncached", "load",
    ):
        wrap_method(GuideUltimeManualRuntimeService, method, records, app)
    for method in ("__init__", "refresh_external_progress"):
        wrap_method(GuideUltimeManualView, method, records, app)
    wrap_method(GuideUltimeManualCard, "__init__", records, app)
    for method in ("ensure_guide_ultime_view", "select_guide"):
        wrap_method(GuidesView, method, records, app)


def measure() -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    records: list[dict[str, Any]] = []
    install(records, app)

    window = AtlasWindow()
    window.show()
    app.processEvents()
    bench.pump_events(app, 0.25)
    checkpoints: dict[str, Any] = {"startup": snapshot(app)}

    bench.open_index(app, window, ACHIEVEMENTS_TAB)
    bench.open_index(app, window, GUIDES_TAB)
    checkpoints["after_indexes"] = snapshot(app)

    page = bench.current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page unavailable")

    window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
    bench.wait_until(app, lambda: bench.tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "Success index")
    rows = list(getattr(getattr(page, "_achievement_index_view", None), "_rows", []) or [])
    achievement_id = int(rows[0][0])
    started = time.perf_counter()
    page._on_achievement_requested(achievement_id)
    block = bench.wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_achievement_ready", False))
        and getattr(page, "_pending_achievement_id", None) is None,
        60.0,
        "first Success detail",
    )
    checkpoints["first_achievement"] = {
        "total_ms": bench.milliseconds(started),
        "max_process_events_ms": block,
        **snapshot(app),
    }
    checkpoints["after_achievement_footprint"] = provider_footprints(window)

    window.open_encyclopedia_tab(GUIDES_TAB)
    bench.wait_until(app, lambda: bench.tab_is_visible(window, GUIDES_TAB), 10.0, "Guide index")
    guide_rows = list(getattr(getattr(page, "_guide_index_view", None), "_rows", []) or [])
    normal_guide_id = str(guide_rows[0][0])
    started = time.perf_counter()
    page._on_guide_requested(normal_guide_id)
    block = bench.wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_guide_runtime_ready", False))
        and not str(getattr(page, "_pending_guide_id", "") or ""),
        60.0,
        "first normal Guide detail",
    )
    checkpoints["first_normal_guide"] = {
        "guide_id": normal_guide_id,
        "total_ms": bench.milliseconds(started),
        "max_process_events_ms": block,
        **snapshot(app),
    }
    checkpoints["after_guide_footprint"] = provider_footprints(window)

    guide_view = page.guides_view
    if guide_view is None:
        raise RuntimeError("Guide view unavailable")
    before = rss()
    widgets_before = len(app.allWidgets())
    started = time.perf_counter()
    selected = bool(guide_view.select_guide("guide_complet"))
    total = bench.milliseconds(started)
    after = rss()
    checkpoints["guide_complet"] = {
        "selected": selected,
        "total_ms": total,
        "ui_ms": total,
        "rss_before_mb": before,
        "rss_after_mb": after,
        "rss_delta_mb": delta(before, after),
        "widgets_before": widgets_before,
        "widgets_after": len(app.allWidgets()),
        "widgets_delta": len(app.allWidgets()) - widgets_before,
        **object_counts(app),
    }

    return {
        "reference_head": REFERENCE_HEAD,
        "diagnostic_head": bench.git_head(),
        "checkpoints": checkpoints,
        "records": records,
    }


def main() -> int:
    payload = {"schema_version": 1, "diagnostic_only": True, "result": measure()}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"provider-memory diagnostic written: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
