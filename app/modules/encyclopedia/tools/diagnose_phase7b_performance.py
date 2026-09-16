from __future__ import annotations

import gc
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from typing import Any, Callable

from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtWidgets import QApplication

from app.constants import ROOT_DIR
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import GuideProgressCalculator
from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE, ImageService
from app.modules.encyclopedia.tools import benchmark_guides_performance as bench
from app.modules.encyclopedia.views import EncyclopediaPage
from app.modules.encyclopedia.views.achievements_view import AchievementsView
from app.modules.encyclopedia.views.guides_view import GuidesView
from app.pages.lazy_quests_page import LazyQuestsPage
from main import AtlasWindow

REFERENCE_HEAD = "a278dc7ae462d0a05ddad8a22ba664b179b5ccca"
OUTPUT = ROOT_DIR / "artifacts" / "phase_certification" / "07_phase7b_performance_diagnostic.json"
DISTINCT_CONTENT = 12


def rss() -> float | None:
    return bench.current_rss_mb()


def delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return round(after - before, 2)


def settle(milliseconds: int = 100) -> None:
    loop = QEventLoop()
    QTimer.singleShot(max(0, int(milliseconds)), loop.quit)
    loop.exec()


def is_ui_thread(app: QApplication) -> bool:
    return bool(QThread.currentThread() == app.thread())


def widget_counts(app: QApplication) -> dict[str, Any]:
    widgets = list(app.allWidgets())
    types = Counter(type(widget).__name__ for widget in widgets)
    timer_ids: set[int] = {id(timer) for timer in app.findChildren(QTimer)}
    thread_ids: set[int] = {id(thread) for thread in app.findChildren(QThread)}
    for widget in widgets:
        timer_ids.update(id(timer) for timer in widget.findChildren(QTimer))
        thread_ids.update(id(thread) for thread in widget.findChildren(QThread))
    interesting = (
        "QLabel",
        "QFrame",
        "QTreeWidget",
        "QListWidget",
        "QScrollArea",
        "QuestLine",
        "GuideHomeCard",
        "GuideStructureRow",
        "AchievementDetailWidget",
        "QWebEngineView",
    )
    return {
        "total": len(widgets),
        "visible": sum(1 for widget in widgets if widget.isVisible()),
        "timers": len(timer_ids),
        "qthreads": len(thread_ids),
        "interesting_types": {name: types.get(name, 0) for name in interesting},
        "top_types": dict(types.most_common(15)),
    }


def python_counts() -> dict[str, Any]:
    objects = gc.get_objects()
    types = Counter(type(obj).__name__ for obj in objects)
    interesting = (
        "Guide",
        "QuestRecord",
        "Achievement",
        "Reward",
        "EntityRef",
        "Future",
        "Thread",
        "QThread",
        "QTimer",
        "QPixmap",
        "QImage",
    )
    threads = threading.enumerate()
    return {
        "gc_objects": len(objects),
        "allocated_blocks": sys.getallocatedblocks(),
        "gc_counts": list(gc.get_count()),
        "interesting_types": {name: types.get(name, 0) for name in interesting},
        "python_threads": len(threads),
        "python_thread_names": [thread.name for thread in threads],
    }


def provider_counts() -> dict[str, int]:
    counts = {"QuestProvider": 0, "AchievementProvider": 0, "GuideProvider": 0}
    for obj in gc.get_objects():
        name = type(obj).__name__
        if name in counts:
            counts[name] += 1
    return counts


def snapshot(app: QApplication) -> dict[str, Any]:
    return {
        "rss_mb": rss(),
        "widgets": widget_counts(app),
        "python": python_counts(),
        "providers": provider_counts(),
        "image_cache": ENCYCLOPEDIA_IMAGE_SERVICE.info(),
    }


def light_state(app: QApplication) -> dict[str, Any]:
    state: dict[str, Any] = {
        "rss_mb": rss(),
        "image_cache": ENCYCLOPEDIA_IMAGE_SERVICE.info(),
    }
    if is_ui_thread(app):
        state["widgets"] = len(app.allWidgets())
    return state


def wrap_method(cls: type, method_name: str, records: list[dict[str, Any]], app: QApplication) -> None:
    original = getattr(cls, method_name, None)
    if original is None:
        return

    def wrapped(self, *args, **kwargs):
        before = light_state(app)
        started = time.perf_counter()
        value = original(self, *args, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000.0, 2)
        after = light_state(app)
        records.append(
            {
                "name": f"{cls.__name__}.{method_name}",
                "thread": threading.current_thread().name,
                "ui_thread": is_ui_thread(app),
                "total_ms": elapsed,
                "ui_ms": elapsed if is_ui_thread(app) else 0.0,
                "rss_before_mb": before["rss_mb"],
                "rss_after_mb": after["rss_mb"],
                "rss_delta_mb": delta(before["rss_mb"], after["rss_mb"]),
                "widgets_before": before.get("widgets"),
                "widgets_after": after.get("widgets"),
                "widgets_delta": (
                    after.get("widgets") - before.get("widgets")
                    if before.get("widgets") is not None and after.get("widgets") is not None
                    else None
                ),
                "image_cache_before": before["image_cache"],
                "image_cache_after": after["image_cache"],
            }
        )
        return value

    setattr(cls, method_name, wrapped)


def wrap_hot_method(cls: type, method_name: str, aggregate: dict[str, dict[str, float]]) -> None:
    original = getattr(cls, method_name, None)
    if original is None:
        return
    key = f"{cls.__name__}.{method_name}"

    def wrapped(self, *args, **kwargs):
        started = time.perf_counter()
        value = original(self, *args, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000.0
        row = aggregate[key]
        row["count"] += 1
        row["total_ms"] += elapsed
        row["max_ms"] = max(row["max_ms"], elapsed)
        return value

    setattr(cls, method_name, wrapped)


def wrap_hot_function(module: Any, function_name: str, aggregate: dict[str, dict[str, float]]) -> None:
    original = getattr(module, function_name, None)
    if original is None:
        return
    key = f"{module.__name__}.{function_name}"

    def wrapped(*args, **kwargs):
        started = time.perf_counter()
        value = original(*args, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000.0
        row = aggregate[key]
        row["count"] += 1
        row["total_ms"] += elapsed
        row["max_ms"] = max(row["max_ms"], elapsed)
        return value

    setattr(module, function_name, wrapped)


def summarize_hot(aggregate: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for key, row in aggregate.items():
        count = int(row["count"])
        result[key] = {
            "count": count,
            "total_ms": round(row["total_ms"], 2),
            "avg_ms": round(row["total_ms"] / count, 4) if count else 0.0,
            "max_ms": round(row["max_ms"], 2),
        }
    return result


def spread_ids(values: list[Any], limit: int = DISTINCT_CONTENT) -> list[Any]:
    unique = list(dict.fromkeys(values))
    if len(unique) <= limit:
        return unique
    result: list[Any] = []
    for index in range(limit):
        position = round(index * (len(unique) - 1) / (limit - 1))
        value = unique[position]
        if value not in result:
            result.append(value)
    return result


def wait_quest_detail(app: QApplication, page: EncyclopediaPage, quest_id: int) -> None:
    quest_page = page.quest_page
    if quest_page is None:
        return
    quest_page.show_quest_detail(int(quest_id))
    bench.wait_until(
        app,
        lambda: not bool(getattr(quest_page, "_detail_pending", False))
        and int(getattr(getattr(quest_page, "quest_detail_view", None), "current_quest_id", 0) or 0) == int(quest_id),
        15.0,
        f"Quest detail {quest_id}",
    )


def install_instrumentation(app: QApplication, records: list[dict[str, Any]], hot: dict[str, dict[str, float]]) -> None:
    for method in (
        "_collect_quest_runtime",
        "_build_quests_page_progressive",
        "_collect_achievement_runtime",
        "collect_related_preload",
        "ensure_guides_view",
        "ensure_achievements_view",
        "open_pending_lazy_tab",
        "_build_guide_progress_snapshot",
    ):
        wrap_method(EncyclopediaPage, method, records, app)

    for method in (
        "hydrate_runtime",
        "refresh_home",
        "select_guide",
        "show_guide_overview",
        "_ensure_detail_page",
        "build_detail_page",
        "_populate_guide_left",
        "_populate_series_quests",
        "_populate_guide_info",
        "_render_header",
    ):
        wrap_method(GuidesView, method, records, app)

    for method in (
        "hydrate_runtime",
        "populate_categories",
        "refresh",
        "_render_next_achievement_batch",
        "select_achievement",
        "show_achievement",
        "clear_detail",
    ):
        wrap_method(AchievementsView, method, records, app)

    for method in (
        "__init__",
        "rebuild_hierarchy",
        "ensure_category_series_loaded",
        "ensure_series_quests_loaded",
        "show_quest_detail",
    ):
        wrap_method(LazyQuestsPage, method, records, app)

    for cls, methods in (
        (QuestProvider, ("get_catalog",)),
        (AchievementProvider, ("_load", "load_all", "load_retained")),
        (GuideProvider, ("load_all", "reload")),
    ):
        for method in methods:
            wrap_method(cls, method, records, app)

    for method in ("guide_progress", "quest_steps_progress"):
        wrap_hot_method(GuideProgressCalculator, method, hot)
    for method in ("get_scaled", "store_scaled", "load_scaled"):
        wrap_hot_method(ImageService, method, hot)

    import app.modules.encyclopedia.views.guides_view as guides_module

    for function_name in ("_decode_guide_image", "_decode_solution_image", "_guide_pixmap"):
        wrap_hot_function(guides_module, function_name, hot)


def measure() -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    records: list[dict[str, Any]] = []
    hot: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0.0, "total_ms": 0.0, "max_ms": 0.0})
    install_instrumentation(app, records, hot)

    startup_started = time.perf_counter()
    window = AtlasWindow()
    window.show()
    app.processEvents()
    settle(250)
    checkpoints: dict[str, Any] = {
        "startup": {"elapsed_ms": bench.milliseconds(startup_started), **snapshot(app)}
    }

    checkpoints["quests_index_ms"] = bench.open_index(app, window, QUESTS_TAB)
    settle(50)
    checkpoints["after_quests_index"] = snapshot(app)

    checkpoints["achievements_index_ms"] = bench.open_index(app, window, ACHIEVEMENTS_TAB)
    settle(50)
    checkpoints["after_achievements_index"] = snapshot(app)

    checkpoints["guide_index_ms"] = bench.open_index(app, window, GUIDES_TAB)
    settle(50)
    checkpoints["after_guide_index"] = snapshot(app)

    page = bench.current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page unavailable")

    window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
    bench.wait_until(app, lambda: bench.tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "Success index")
    achievement_index = getattr(page, "_achievement_index_view", None)
    index_achievement_ids = [int(row[0]) for row in list(getattr(achievement_index, "_rows", []) or [])]
    if not index_achievement_ids:
        raise RuntimeError("Success index has no selectable rows")
    achievement_started = time.perf_counter()
    page._on_achievement_requested(index_achievement_ids[0])
    achievement_block = bench.wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_achievement_ready", False))
        and getattr(page, "_pending_achievement_id", None) is None
        and page.get_achievements_view() is not None,
        60.0,
        "first Success detail",
    )
    settle(100)
    checkpoints["first_achievement"] = {
        "total_ms": bench.milliseconds(achievement_started),
        "max_process_events_ms": achievement_block,
        **snapshot(app),
    }

    window.open_encyclopedia_tab(GUIDES_TAB)
    bench.wait_until(app, lambda: bench.tab_is_visible(window, GUIDES_TAB), 10.0, "Guide index")
    guide_index = getattr(page, "_guide_index_view", None)
    index_guide_ids = [str(row[0]) for row in list(getattr(guide_index, "_rows", []) or [])]
    if not index_guide_ids:
        raise RuntimeError("Guide index has no selectable rows")
    guide_started = time.perf_counter()
    page._on_guide_requested(index_guide_ids[0])
    guide_block = bench.wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_guide_runtime_ready", False))
        and not str(getattr(page, "_pending_guide_id", "") or "")
        and page.guides_view is not None,
        60.0,
        "first Guide detail",
    )
    settle(100)
    checkpoints["first_guide"] = {
        "total_ms": bench.milliseconds(guide_started),
        "max_process_events_ms": guide_block,
        **snapshot(app),
    }

    achievement_view = page.get_achievements_view()
    guide_view = page.guides_view
    quest_page = page.quest_page
    if achievement_view is None or guide_view is None or quest_page is None:
        raise RuntimeError("Rich Encyclopedia views did not materialize")

    quest_ids = spread_ids([int(quest.id) for quest in quest_page.catalog.quests])
    achievement_ids = spread_ids([int(item.id) for item in achievement_view.achievements])
    guide_ids = spread_ids([str(item.id) for item in guide_view.guides])

    endurance: dict[str, Any] = {}
    for cycle in range(1, 51):
        bench.open_hot_tab(app, window, QUESTS_TAB)
        wait_quest_detail(app, page, int(quest_ids[(cycle - 1) % len(quest_ids)]))

        bench.open_hot_tab(app, window, ACHIEVEMENTS_TAB)
        achievement_view.select_achievement(int(achievement_ids[(cycle - 1) % len(achievement_ids)]))

        bench.open_hot_tab(app, window, GUIDES_TAB)
        guide_view.select_guide(str(guide_ids[(cycle - 1) % len(guide_ids)]))

        settle(20)
        if cycle in (5, 20, 50):
            settle(150)
            endurance[str(cycle)] = snapshot(app)

    guide_view.show_home()
    achievement_view.close_detail_panel()
    bench.open_hot_tab(app, window, QUESTS_TAB)
    settle(500)
    after_return_home = snapshot(app)

    before_gc = snapshot(app)
    collected = gc.collect()
    settle(150)
    after_gc = snapshot(app)

    window._shutdown_background_services()
    window.hide()
    window.deleteLater()
    settle(300)
    after_shutdown = snapshot(app)

    return {
        "reference_head": REFERENCE_HEAD,
        "diagnostic_head": bench.git_head(),
        "checkpoints": checkpoints,
        "instrumented_calls": records,
        "hot_call_aggregates": summarize_hot(hot),
        "distinct_content": {
            "quest_ids": quest_ids,
            "achievement_ids": achievement_ids,
            "guide_ids": guide_ids,
        },
        "endurance": endurance,
        "retention": {
            "after_return_home": after_return_home,
            "before_gc": before_gc,
            "gc_collected_objects": collected,
            "after_gc": after_gc,
            "after_shutdown": after_shutdown,
        },
    }


def main() -> int:
    payload = {
        "schema_version": 2,
        "diagnostic_only": True,
        "notes": (
            "Instrumentation branch only. Product behavior is unchanged. Per-call wrappers use lightweight RSS/widget/cache sampling; "
            "full GC/object snapshots occur only at checkpoints. Certification timing remains the uninstrumented benchmark on the reference SHA."
        ),
        "result": measure(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 7B diagnostic written to {OUTPUT}")
    print(json.dumps({
        "reference_head": payload["result"]["reference_head"],
        "diagnostic_head": payload["result"]["diagnostic_head"],
        "checkpoints": payload["result"]["checkpoints"],
        "endurance": payload["result"]["endurance"],
        "retention": payload["result"]["retention"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
