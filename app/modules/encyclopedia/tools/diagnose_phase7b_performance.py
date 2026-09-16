from __future__ import annotations

import functools
import gc
import json
import os
import platform
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import Future
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QThread, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from app.constants import ROOT_DIR
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
from app.modules.encyclopedia.tools.benchmark_guides_performance import (
    current_encyclopedia_page,
    current_rss_mb,
    index_is_ready,
    pump_events,
    tab_is_visible,
    wait_until,
    wait_until_with_ui_block,
)
from app.modules.encyclopedia.views.achievements_view import AchievementsView
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
from app.modules.encyclopedia.views.guides_view import GuidesView
from app.pages.lazy_quests_page import LazyQuestsPage
from main import AtlasWindow


OUTPUT = ROOT_DIR / "artifacts" / "phase7b_deep_diagnostic.json"
REFERENCE_SHA = "a278dc7ae462d0a05ddad8a22ba664b179b5ccca"
CHECKPOINTS = {5, 20, 50}

_EVENTS: list[dict[str, object]] = []
_PATCHES: list[tuple[type, str, object]] = []


def git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _widget_type_counts() -> Counter[str]:
    return Counter(type(widget).__name__ for widget in QApplication.allWidgets())


def _qt_object_counts() -> dict[str, int]:
    app = QApplication.instance()
    if app is None:
        return {"widgets": 0, "timers": 0, "qthreads": 0, "webviews": 0}
    widgets = QApplication.allWidgets()
    timers: set[int] = set()
    qthreads: set[int] = set()
    webviews = 0
    for widget in widgets:
        if type(widget).__name__ == "QWebEngineView":
            webviews += 1
        for timer in widget.findChildren(QTimer):
            timers.add(id(timer))
        for thread in widget.findChildren(QThread):
            qthreads.add(id(thread))
    for timer in app.findChildren(QTimer):
        timers.add(id(timer))
    for thread in app.findChildren(QThread):
        qthreads.add(id(thread))
    return {
        "widgets": len(widgets),
        "timers": len(timers),
        "qthreads": len(qthreads),
        "webviews": webviews,
    }


def _gc_type_counts() -> dict[str, int]:
    wanted = {
        "QPixmap",
        "QImage",
        "Future",
        "Thread",
        "GuideHomeCard",
        "QuestLine",
        "AchievementDetailWidget",
        "QTreeWidgetItem",
        "QListWidgetItem",
    }
    counts: Counter[str] = Counter()
    for obj in gc.get_objects():
        try:
            name = type(obj).__name__
        except Exception:
            continue
        if name in wanted:
            counts[name] += 1
    counts["Future"] = max(counts.get("Future", 0), sum(1 for obj in gc.get_objects() if isinstance(obj, Future)))
    return dict(counts)


def resource_snapshot(label: str, *, deep: bool = True) -> dict[str, object]:
    qt = _qt_object_counts()
    snapshot: dict[str, object] = {
        "label": label,
        "rss_mb": current_rss_mb(),
        "python_threads": len(threading.enumerate()),
        "python_thread_names": sorted(thread.name for thread in threading.enumerate()),
        "image_cache": ENCYCLOPEDIA_IMAGE_SERVICE.info(),
        **qt,
    }
    if deep:
        snapshot["widget_types"] = dict(_widget_type_counts().most_common(20))
        snapshot["gc_types"] = _gc_type_counts()
    return snapshot


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return round(after - before, 2)


def patch_method(cls: type, method_name: str, label: str) -> None:
    original = getattr(cls, method_name, None)
    if original is None or not callable(original):
        return

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        rss_before = current_rss_mb()
        widgets_before = len(QApplication.allWidgets())
        started = time.perf_counter()
        error = ""
        try:
            return original(*args, **kwargs)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            rss_after = current_rss_mb()
            widgets_after = len(QApplication.allWidgets())
            _EVENTS.append(
                {
                    "name": label,
                    "elapsed_ms": elapsed_ms,
                    "thread": threading.current_thread().name,
                    "ui_thread": threading.current_thread() is threading.main_thread(),
                    "rss_before_mb": rss_before,
                    "rss_after_mb": rss_after,
                    "rss_delta_mb": _delta(rss_after, rss_before),
                    "widgets_before": widgets_before,
                    "widgets_after": widgets_after,
                    "widgets_delta": widgets_after - widgets_before,
                    "error": error,
                }
            )

    _PATCHES.append((cls, method_name, original))
    setattr(cls, method_name, wrapped)


def install_instrumentation() -> None:
    targets = (
        (EncyclopediaPage, "_build_quests_page_progressive", "quests.build_page"),
        (EncyclopediaPage, "ensure_achievements_view", "success.ensure_view"),
        (EncyclopediaPage, "_collect_achievement_runtime", "success.worker_to_ui"),
        (EncyclopediaPage, "ensure_guides_view", "guide.ensure_view"),
        (EncyclopediaPage, "collect_related_preload", "guide.collect_related_preload"),
        (EncyclopediaPage, "open_pending_lazy_tab", "guide.open_pending_lazy_tab"),
        (AchievementProvider, "_load", "success.provider_load"),
        (AchievementProvider, "load_all", "success.provider_load_all"),
        (AchievementProvider, "load_retained", "success.provider_load_retained"),
        (QuestProvider, "get_catalog", "quests.provider_get_catalog"),
        (AchievementsView, "hydrate_runtime", "success.hydrate_runtime"),
        (AchievementsView, "populate_categories", "success.populate_categories"),
        (AchievementsView, "refresh", "success.refresh"),
        (AchievementsView, "show_achievement", "success.show_achievement"),
        (AchievementsView, "clear_detail", "success.clear_detail"),
        (GuidesView, "hydrate_runtime", "guide.hydrate_runtime"),
        (GuidesView, "refresh_home", "guide.refresh_home"),
        (GuidesView, "select_guide", "guide.select_guide"),
        (GuidesView, "_ensure_detail_page", "guide.ensure_detail_page"),
        (GuidesView, "build_detail_page", "guide.build_detail_page"),
        (GuidesView, "show_guide_overview", "guide.show_overview"),
        (GuidesView, "_populate_guide_left", "guide.populate_left"),
        (GuidesView, "_populate_series_quests", "guide.populate_series_quests"),
        (GuidesView, "_populate_guide_info", "guide.populate_info"),
        (GuidesView, "_render_header", "guide.render_header"),
        (DeferredAchievementGuidesView, "select_guide", "guide.deferred_select_guide"),
        (LazyQuestsPage, "rebuild_hierarchy", "quests.rebuild_hierarchy"),
        (LazyQuestsPage, "ensure_category_series_loaded", "quests.load_category_series"),
        (LazyQuestsPage, "ensure_series_quests_loaded", "quests.load_series_quests"),
        (LazyQuestsPage, "show_quest_detail", "quests.show_detail"),
    )
    for cls, method, label in targets:
        patch_method(cls, method, label)


def restore_instrumentation() -> None:
    while _PATCHES:
        cls, method_name, original = _PATCHES.pop()
        setattr(cls, method_name, original)


def event_summary(start_index: int = 0) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in _EVENTS[start_index:]:
        grouped[str(event["name"])].append(event)
    result: dict[str, dict[str, object]] = {}
    for name, rows in sorted(grouped.items()):
        elapsed = [float(row["elapsed_ms"]) for row in rows]
        ui_elapsed = [float(row["elapsed_ms"]) for row in rows if row.get("ui_thread")]
        deltas = [row.get("rss_delta_mb") for row in rows if row.get("rss_delta_mb") is not None]
        result[name] = {
            "calls": len(rows),
            "total_ms": round(sum(elapsed), 2),
            "max_ms": round(max(elapsed), 2),
            "ui_total_ms": round(sum(ui_elapsed), 2),
            "ui_max_ms": round(max(ui_elapsed), 2) if ui_elapsed else 0.0,
            "max_single_rss_delta_mb": round(max((float(value) for value in deltas), default=0.0), 2),
            "max_widgets_delta": max((int(row["widgets_delta"]) for row in rows), default=0),
            "threads": sorted({str(row["thread"]) for row in rows}),
        }
    return result


def measure_index(app: QApplication, window: AtlasWindow, label: str) -> dict[str, object]:
    started = time.perf_counter()
    rss_before = current_rss_mb()
    event_start = len(_EVENTS)
    window.open_encyclopedia_tab(label)
    max_ui_block_ms = wait_until_with_ui_block(
        app,
        lambda: index_is_ready(window, label),
        30.0,
        f"{label} index",
    )
    rss_after = current_rss_mb()
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "max_ui_block_ms": max_ui_block_ms,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": _delta(rss_after, rss_before),
        "events": event_summary(event_start),
    }


def _success_ids(view: AchievementsView, limit: int = 50) -> list[int]:
    by_category: dict[int, list[int]] = defaultdict(list)
    for achievement in view.achievements:
        category = int(achievement.subcategory_id or achievement.category_id)
        by_category[category].append(int(achievement.id))
    categories = [values for _key, values in sorted(by_category.items()) if values]
    result: list[int] = []
    offset = 0
    while categories and len(result) < limit:
        progressed = False
        for values in categories:
            if offset < len(values):
                result.append(values[offset])
                progressed = True
                if len(result) >= limit:
                    break
        if not progressed:
            break
        offset += 1
    return result


def _quest_ids(page: LazyQuestsPage, limit: int = 50) -> list[int]:
    ids = sorted(int(value) for value in page.catalog.by_id)
    if len(ids) <= limit:
        return ids
    step = max(1, len(ids) // limit)
    return ids[::step][:limit]


def _guide_ids(view: GuidesView) -> list[str]:
    return [str(guide.id) for guide in view.guides]


def first_success_detail(app: QApplication, window: AtlasWindow) -> dict[str, object]:
    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page missing before Success diagnostic.")
    index_view = getattr(page, "_achievement_index_view", None)
    rows = list(getattr(index_view, "_rows", []) or [])
    if not rows:
        raise RuntimeError("Success index contains no selectable row.")
    achievement_id = int(rows[0][0])
    rss_before = current_rss_mb()
    event_start = len(_EVENTS)
    started = time.perf_counter()
    page._on_achievement_requested(achievement_id)
    max_ui_block_ms = wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_achievement_ready", False))
        and getattr(page, "_pending_achievement_id", None) is None
        and page.get_achievements_view() is not None
        and tab_is_visible(window, ACHIEVEMENTS_TAB),
        90.0,
        f"Success detail {achievement_id}",
    )
    pump_events(app, 0.1)
    rss_after = current_rss_mb()
    return {
        "achievement_id": achievement_id,
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "max_ui_block_ms": max_ui_block_ms,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": _delta(rss_after, rss_before),
        "events": event_summary(event_start),
        "resources_after": resource_snapshot("after_first_success"),
    }


def first_guide_detail(app: QApplication, window: AtlasWindow) -> dict[str, object]:
    page = current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page missing before Guide diagnostic.")
    index_view = getattr(page, "_guide_index_view", None)
    rows = list(getattr(index_view, "_rows", []) or [])
    if not rows:
        raise RuntimeError("Guide index contains no selectable row.")
    guide_id = str(rows[0][0])
    rss_before = current_rss_mb()
    event_start = len(_EVENTS)
    started = time.perf_counter()
    page._on_guide_requested(guide_id)
    max_ui_block_ms = wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_guide_runtime_ready", False))
        and not str(getattr(page, "_pending_guide_id", "") or "")
        and page.guides_view is not None
        and str(getattr(page.guides_view, "current_guide_id", "") or "") == guide_id
        and tab_is_visible(window, GUIDES_TAB),
        90.0,
        f"Guide detail {guide_id}",
    )
    pump_events(app, 0.1)
    rss_after = current_rss_mb()
    return {
        "guide_id": guide_id,
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "max_ui_block_ms": max_ui_block_ms,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": _delta(rss_after, rss_before),
        "events": event_summary(event_start),
        "resources_after": resource_snapshot("after_first_guide"),
    }


def endurance(app: QApplication, window: AtlasWindow) -> dict[str, object]:
    page = current_encyclopedia_page(window)
    if page is None or page.quest_page is None or page.guides_view is None:
        raise RuntimeError("Rich Encyclopedia views are not ready for endurance diagnostic.")
    success_view = page.get_achievements_view()
    if success_view is None:
        raise RuntimeError("Success view is not ready for endurance diagnostic.")

    quest_ids = _quest_ids(page.quest_page, 50)
    success_ids = _success_ids(success_view, 50)
    guide_ids = _guide_ids(page.guides_view)
    if not quest_ids or not success_ids or not guide_ids:
        raise RuntimeError("Endurance diagnostic requires non-empty Quest/Success/Guide samples.")

    checkpoints: dict[str, object] = {}
    max_ui_block_ms = 0.0
    event_start = len(_EVENTS)
    for cycle in range(1, 51):
        window.open_encyclopedia_tab(QUESTS_TAB)
        wait_until(app, lambda: tab_is_visible(window, QUESTS_TAB), 10.0, "endurance Quests tab")
        quest_id = quest_ids[(cycle - 1) % len(quest_ids)]
        page.quest_page.select_quest(quest_id)
        block = wait_until_with_ui_block(
            app,
            lambda qid=quest_id: (
                not bool(getattr(page.quest_page, "_detail_pending", False))
                and int(getattr(page.quest_page.quest_detail_view, "current_quest_id", 0) or 0) == qid
            ),
            20.0,
            f"endurance quest {quest_id}",
        )
        max_ui_block_ms = max(max_ui_block_ms, block)

        window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
        wait_until(app, lambda: tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "endurance Success tab")
        achievement_id = success_ids[(cycle - 1) % len(success_ids)]
        success_view.select_achievement(achievement_id)
        block = wait_until_with_ui_block(
            app,
            lambda aid=achievement_id: int(getattr(success_view, "current_achievement_id", 0) or 0) == aid
            and bool(getattr(success_view, "_detail_open", False)),
            10.0,
            f"endurance achievement {achievement_id}",
        )
        max_ui_block_ms = max(max_ui_block_ms, block)

        window.open_encyclopedia_tab(GUIDES_TAB)
        wait_until(app, lambda: tab_is_visible(window, GUIDES_TAB), 10.0, "endurance Guide tab")
        guide_id = guide_ids[(cycle - 1) % len(guide_ids)]
        page.guides_view.select_guide(guide_id)
        block = wait_until_with_ui_block(
            app,
            lambda gid=guide_id: str(getattr(page.guides_view, "current_guide_id", "") or "") == gid,
            10.0,
            f"endurance guide {guide_id}",
        )
        max_ui_block_ms = max(max_ui_block_ms, block)

        if cycle in CHECKPOINTS:
            pump_events(app, 0.25)
            checkpoints[str(cycle)] = resource_snapshot(f"after_{cycle}_cycles")

    success_view.close_detail_panel()
    page.guides_view.show_home()
    window.open_encyclopedia_tab(QUESTS_TAB)
    wait_until(app, lambda: tab_is_visible(window, QUESTS_TAB), 10.0, "post-endurance Quests tab")
    pump_events(app, 1.0)
    after_idle = resource_snapshot("after_50_cycles_idle")

    gc_before = resource_snapshot("before_explicit_gc")
    collected = gc.collect()
    pump_events(app, 0.25)
    gc_after = resource_snapshot("after_explicit_gc")

    return {
        "distinct_quest_ids": len(set(quest_ids)),
        "distinct_success_ids": len(set(success_ids)),
        "distinct_guide_ids": len(set(guide_ids)),
        "max_ui_block_ms": round(max_ui_block_ms, 2),
        "checkpoints": checkpoints,
        "after_idle": after_idle,
        "explicit_gc": {
            "collected_objects": collected,
            "before": gc_before,
            "after": gc_after,
            "rss_delta_mb": _delta(gc_after.get("rss_mb"), gc_before.get("rss_mb")),
        },
        "events": event_summary(event_start),
    }


def measure() -> dict[str, object]:
    app = QApplication.instance() or QApplication([])
    install_instrumentation()
    startup_started = time.perf_counter()
    window = AtlasWindow()
    constructor_ms = round((time.perf_counter() - startup_started) * 1000.0, 2)
    window.show()
    app.processEvents()
    first_paint_ms = round((time.perf_counter() - startup_started) * 1000.0, 2)
    pump_events(app, 0.25)
    startup_ms = round((time.perf_counter() - startup_started) * 1000.0, 2)

    result: dict[str, object] = {
        "startup": {
            "constructor_ms": constructor_ms,
            "first_paint_ms": first_paint_ms,
            "stabilized_ms": startup_ms,
            "resources": resource_snapshot("startup"),
        }
    }

    try:
        result["quests_index"] = measure_index(app, window, QUESTS_TAB)
        result["after_quests_index"] = resource_snapshot("after_quests_index")
        result["success_index"] = measure_index(app, window, ACHIEVEMENTS_TAB)
        result["after_success_index"] = resource_snapshot("after_success_index")
        result["guide_index"] = measure_index(app, window, GUIDES_TAB)
        result["after_guide_index"] = resource_snapshot("after_guide_index")

        window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
        wait_until(app, lambda: tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "Success index revisit")
        result["first_success"] = first_success_detail(app, window)

        window.open_encyclopedia_tab(GUIDES_TAB)
        wait_until(app, lambda: tab_is_visible(window, GUIDES_TAB), 10.0, "Guide index revisit")
        result["first_guide"] = first_guide_detail(app, window)

        result["endurance"] = endurance(app, window)
        result["all_instrumented_events"] = event_summary(0)
        result["event_count"] = len(_EVENTS)
        result["raw_events"] = list(_EVENTS)
    finally:
        window._shutdown_background_services()
        window.hide()
        window.deleteLater()
        pump_events(app, 0.1)
        result["after_shutdown"] = resource_snapshot("after_shutdown")
        restore_instrumentation()
    return result


def main() -> int:
    head = git_head()
    payload = {
        "schema_version": 1,
        "diagnostic_only": True,
        "reference_sha": REFERENCE_SHA,
        "environment": {
            "git_head": head,
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pyside": PYSIDE_VERSION,
            "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
            "notes": (
                "Temporary Phase 7B diagnostic instrumentation only. Product behavior is not changed. "
                "Method wrappers measure wall time, UI-thread attribution, RSS and widget deltas. "
                "Endurance visits distinct Quest/Success/Guide content and records RSS/resources at 5/20/50 cycles."
            ),
        },
        "measurements": measure(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
