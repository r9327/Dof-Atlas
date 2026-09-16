from __future__ import annotations

import gc
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from app.constants import ROOT_DIR
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.tools import benchmark_guides_performance as bench
from app.modules.encyclopedia.views.achievements_view import AchievementsView
from app.modules.encyclopedia.views.guides_view import GuidesView
from app.modules.encyclopedia.views import EncyclopediaPage
from main import AtlasWindow

OUTPUT = ROOT_DIR / "artifacts" / "phase7b_performance_diagnostic.json"


def rss() -> float | None:
    return bench.current_rss_mb()


def delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return round(after - before, 2)


def qt_counts(app: QApplication) -> dict[str, int]:
    widgets = app.allWidgets()
    return {
        "widgets": len(widgets),
        "visible_widgets": sum(1 for item in widgets if item.isVisible()),
        "threads": len(app.findChildren(QThread)),
        "timers": len(app.findChildren(QTimer)),
    }


def python_counts() -> dict[str, int]:
    counts = Counter(type(obj).__name__ for obj in gc.get_objects())
    names = (
        "QPixmap", "QImage", "Future", "Thread", "QThread", "QTimer",
        "Guide", "Quest", "Achievement", "QuestLine", "AchievementDetailWidget",
    )
    return {name: counts.get(name, 0) for name in names}


def snapshot(app: QApplication) -> dict[str, Any]:
    return {"rss_mb": rss(), "qt": qt_counts(app), "python": python_counts()}


def timed_call(app: QApplication, name: str, fn: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    before = snapshot(app)
    started = time.perf_counter()
    value = fn()
    elapsed = round((time.perf_counter() - started) * 1000.0, 2)
    after = snapshot(app)
    return value, {
        "name": name,
        "total_ms": elapsed,
        "ui_ms": elapsed,
        "rss_before_mb": before["rss_mb"],
        "rss_after_mb": after["rss_mb"],
        "rss_delta_mb": delta(before["rss_mb"], after["rss_mb"]),
        "qt_before": before["qt"],
        "qt_after": after["qt"],
        "python_before": before["python"],
        "python_after": after["python"],
    }


def wrap_method(cls: type, method_name: str, records: list[dict[str, Any]], app: QApplication) -> None:
    original = getattr(cls, method_name, None)
    if original is None:
        return

    def wrapped(self, *args, **kwargs):
        value, record = timed_call(app, f"{cls.__name__}.{method_name}", lambda: original(self, *args, **kwargs))
        records.append(record)
        return value

    setattr(cls, method_name, wrapped)


def first_distinct_ids(rows: list[Any], limit: int) -> list[Any]:
    result: list[Any] = []
    for row in rows:
        value = row[0]
        if value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def measure() -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    records: list[dict[str, Any]] = []

    for method in ("collect_related_preload", "ensure_guides_view", "open_pending_lazy_tab"):
        wrap_method(EncyclopediaPage, method, records, app)
    for method in ("hydrate_runtime", "refresh_home", "select_guide", "show_guide_overview", "_populate_guide_left", "_populate_series_quests", "_populate_guide_info", "_render_header"):
        wrap_method(GuidesView, method, records, app)
    for method in ("hydrate_runtime", "select_achievement", "_populate_categories", "_populate_achievements", "_show_achievement_detail"):
        wrap_method(AchievementsView, method, records, app)

    startup_started = time.perf_counter()
    window = AtlasWindow()
    window.show()
    app.processEvents()
    bench.pump_events(app, 0.25)
    checkpoints: dict[str, Any] = {
        "startup": {"elapsed_ms": bench.milliseconds(startup_started), **snapshot(app)}
    }

    checkpoints["quests_index_ms"] = bench.open_index(app, window, QUESTS_TAB)
    checkpoints["after_quests_index"] = snapshot(app)
    checkpoints["achievements_index_ms"] = bench.open_index(app, window, ACHIEVEMENTS_TAB)
    checkpoints["after_achievements_index"] = snapshot(app)
    checkpoints["guide_index_ms"] = bench.open_index(app, window, GUIDES_TAB)
    checkpoints["after_guide_index"] = snapshot(app)

    page = bench.current_encyclopedia_page(window)
    if page is None:
        raise RuntimeError("Encyclopedia page unavailable")

    window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
    bench.wait_until(app, lambda: bench.tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "Success index")
    achievement_index = getattr(page, "_achievement_index_view", None)
    achievement_ids = first_distinct_ids(list(getattr(achievement_index, "_rows", []) or []), 12)
    achievement_started = time.perf_counter()
    page._on_achievement_requested(int(achievement_ids[0]))
    achievement_block = bench.wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_achievement_ready", False)) and getattr(page, "_pending_achievement_id", None) is None,
        60.0,
        "first Success detail",
    )
    checkpoints["first_achievement"] = {
        "total_ms": bench.milliseconds(achievement_started),
        "max_process_events_ms": achievement_block,
        **snapshot(app),
    }

    window.open_encyclopedia_tab(GUIDES_TAB)
    bench.wait_until(app, lambda: bench.tab_is_visible(window, GUIDES_TAB), 10.0, "Guide index")
    guide_index = getattr(page, "_guide_index_view", None)
    guide_ids = [str(value) for value in first_distinct_ids(list(getattr(guide_index, "_rows", []) or []), 12)]
    guide_started = time.perf_counter()
    page._on_guide_requested(guide_ids[0])
    guide_block = bench.wait_until_with_ui_block(
        app,
        lambda: bool(getattr(page, "_guide_runtime_ready", False)) and not str(getattr(page, "_pending_guide_id", "") or ""),
        60.0,
        "first Guide detail",
    )
    checkpoints["first_guide"] = {
        "total_ms": bench.milliseconds(guide_started),
        "max_process_events_ms": guide_block,
        **snapshot(app),
    }

    endurance: dict[str, Any] = {}
    distinct_achievement_ids = achievement_ids or [getattr(page, "_pending_achievement_id", 0)]
    distinct_guide_ids = guide_ids or [str(getattr(page.guides_view, "current_guide_id", ""))]
    for cycle in range(1, 51):
        bench.open_hot_tab(app, window, QUESTS_TAB)
        bench.open_hot_tab(app, window, ACHIEVEMENTS_TAB)
        if page.achievements_view is not None and distinct_achievement_ids:
            page.achievements_view.select_achievement(int(distinct_achievement_ids[(cycle - 1) % len(distinct_achievement_ids)]))
        bench.open_hot_tab(app, window, GUIDES_TAB)
        if page.guides_view is not None and distinct_guide_ids:
            page.guides_view.select_guide(distinct_guide_ids[(cycle - 1) % len(distinct_guide_ids)])
        app.processEvents()
        if cycle in (5, 20, 50):
            bench.pump_events(app, 0.1)
            endurance[str(cycle)] = snapshot(app)

    bench.pump_events(app, 0.5)
    before_gc = snapshot(app)
    gc.collect()
    bench.pump_events(app, 0.1)
    after_gc = snapshot(app)

    window._shutdown_background_services()
    window.hide()
    window.deleteLater()
    bench.pump_events(app, 0.1)
    after_shutdown = snapshot(app)

    return {
        "reference_head": bench.git_head(),
        "checkpoints": checkpoints,
        "instrumented_calls": records,
        "distinct_achievement_ids": distinct_achievement_ids,
        "distinct_guide_ids": distinct_guide_ids,
        "endurance": endurance,
        "retention": {"before_gc": before_gc, "after_gc": after_gc, "after_shutdown": after_shutdown},
    }


def main() -> int:
    payload = {"schema_version": 1, "diagnostic_only": True, "result": measure()}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
