from __future__ import annotations

import gc
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.constants import ROOT_DIR
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
import app.modules.encyclopedia.providers.achievement_provider as achievement_provider_module
import app.modules.encyclopedia.services.guide_ultime_manual_runtime_service as manual_runtime_module
from app.quest_catalog_details import QuestDetails
from app.modules.encyclopedia.tools.diagnose_phase7b_performance import (
    _delta,
    _guide_ids,
    _quest_ids,
    _success_ids,
    current_encyclopedia_page,
    current_rss_mb,
    first_guide_detail,
    first_success_detail,
    index_is_ready,
    install_instrumentation,
    patch_method,
    pump_events,
    resource_snapshot,
    restore_instrumentation,
    tab_is_visible,
    wait_until,
)
from main import AtlasWindow

OUTPUT = ROOT_DIR / "artifacts" / "phase7b_lifecycle_retention.json"
REFERENCE_SHA = "a278dc7ae462d0a05ddad8a22ba664b179b5ccca"
CHECKPOINTS = {5, 20, 50}

_SOURCE_EVENTS: list[dict[str, object]] = []
_SOURCE_PATCHES: list[tuple[object, str, object]] = []


def git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def drain_deferred(app: QApplication, passes: int = 4) -> None:
    """Mimic normal event-loop returns so deleteLater() is actually serviced."""
    for _ in range(max(1, int(passes))):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def _patch_source_function(owner: object, name: str, label: str) -> None:
    original = getattr(owner, name)

    def wrapped(path, *args, **kwargs):
        rss_before = current_rss_mb()
        started = time.perf_counter()
        result = original(path, *args, **kwargs)
        rss_after = current_rss_mb()
        try:
            rows = len(result)
        except TypeError:
            rows = None
        _SOURCE_EVENTS.append(
            {
                "name": label,
                "path": str(path),
                "basename": Path(path).name,
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                "rss_before_mb": rss_before,
                "rss_after_mb": rss_after,
                "rss_delta_mb": _delta(rss_after, rss_before),
                "rows": rows,
                "thread": threading.current_thread().name,
            }
        )
        return result

    _SOURCE_PATCHES.append((owner, name, original))
    setattr(owner, name, wrapped)


def install_source_instrumentation() -> None:
    _patch_source_function(
        achievement_provider_module,
        "doduda_rows",
        "achievement_provider.doduda_rows",
    )
    _patch_source_function(
        achievement_provider_module,
        "read_json_file",
        "achievement_provider.read_json_file",
    )


def restore_source_instrumentation() -> None:
    while _SOURCE_PATCHES:
        owner, name, original = _SOURCE_PATCHES.pop()
        setattr(owner, name, original)


def deep_size_bytes(value: object, seen: set[int] | None = None) -> int:
    """Diagnostic-only retained Python graph estimate; excludes Qt/native buffers."""
    if seen is None:
        seen = set()
    ident = id(value)
    if ident in seen:
        return 0
    seen.add(ident)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        for key, item in value.items():
            size += deep_size_bytes(key, seen)
            size += deep_size_bytes(item, seen)
        return size
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            size += deep_size_bytes(item, seen)
        return size
    slots = getattr(type(value), "__slots__", ())
    if isinstance(slots, str):
        slots = (slots,)
    for slot in slots:
        if slot.startswith("__"):
            continue
        try:
            item = getattr(value, slot)
        except (AttributeError, RuntimeError):
            continue
        if slot in {"quest_provider", "achievement_provider", "guide_provider", "_coordinator"}:
            continue
        size += deep_size_bytes(item, seen)
    return size


def provider_stats(provider) -> dict[str, object]:
    achievements = list(getattr(provider, "_achievements", ()) or ())
    retained_fields = {
        name: getattr(provider, name, None)
        for name in (
            "_achievements",
            "_by_id",
            "_categories",
            "_by_category",
            "_linked_quests",
            "_linked_monsters",
            "_linked_dungeons",
            "_linked_achievements",
            "_by_quest",
            "_image_indexes",
        )
    }
    image_indexes = getattr(provider, "_image_indexes", {}) or {}
    return {
        "type": type(provider).__name__,
        "loaded": bool(getattr(provider, "_loaded", False)),
        "achievements": len(achievements),
        "categories": len(getattr(provider, "_categories", {}) or {}),
        "by_category_keys": len(getattr(provider, "_by_category", {}) or {}),
        "by_category_refs": sum(len(rows) for rows in (getattr(provider, "_by_category", {}) or {}).values()),
        "by_quest_keys": len(getattr(provider, "_by_quest", {}) or {}),
        "by_quest_refs": sum(len(rows) for rows in (getattr(provider, "_by_quest", {}) or {}).values()),
        "objective_count": sum(len(getattr(row, "objectives", ()) or ()) for row in achievements),
        "reward_count": sum(len(getattr(row, "rewards", ()) or ()) for row in achievements),
        "resolved_quest_refs": sum(len(getattr(row, "resolved_linked_quests", ()) or ()) for row in achievements),
        "resolved_monster_refs": sum(len(getattr(row, "resolved_linked_monsters", ()) or ()) for row in achievements),
        "resolved_dungeon_refs": sum(len(getattr(row, "resolved_linked_dungeons", ()) or ()) for row in achievements),
        "raw_payloads": sum(bool(getattr(row, "raw", None)) for row in achievements),
        "raw_dict_entries": sum(len(getattr(row, "raw", {}) or {}) for row in achievements),
        "image_index_groups": len(image_indexes),
        "image_index_entries": sum(len(rows) for rows in image_indexes.values()),
        "retained_python_graph_mb": round(deep_size_bytes(retained_fields) / (1024.0 * 1024.0), 2),
        "raw_payload_graph_mb": round(
            deep_size_bytes([getattr(row, "raw", {}) for row in achievements]) / (1024.0 * 1024.0), 2
        ),
    }


def quest_detail_cache_info(page) -> dict[str, object]:
    catalog = page.quest_provider.get_catalog()
    getter = getattr(catalog, "detail_cache_info", None)
    return dict(getter()) if callable(getter) else {}


def manual_runtime_stats(view) -> dict[str, object]:
    service = getattr(view, "guide_ultime_service", None)
    cache = getattr(manual_runtime_module, "_MANUAL_BUNDLE_CACHE", {}) or {}
    audit = service.manual_audit() if service is not None and hasattr(service, "manual_audit") else {}
    contract = getattr(service, "auto_validation_contract", None) if service is not None else None
    return {
        "service_present": service is not None,
        "card_count": int(audit.get("card_count") or 0) if isinstance(audit, dict) else 0,
        "chapter_count": int(audit.get("chapter_count") or 0) if isinstance(audit, dict) else 0,
        "service_route_python_mb": round(
            deep_size_bytes(getattr(service, "route", {})) / (1024.0 * 1024.0), 2
        ) if service is not None else 0.0,
        "manual_bundle_cache_entries": len(cache),
        "manual_bundle_cache_python_mb": round(deep_size_bytes(cache) / (1024.0 * 1024.0), 2),
        "auto_validation_contract_python_mb": round(
            deep_size_bytes(contract) / (1024.0 * 1024.0), 2
        ) if contract is not None else 0.0,
    }


def open_indexes(app: QApplication, window: AtlasWindow) -> dict[str, object]:
    result = {}
    for label in (QUESTS_TAB, ACHIEVEMENTS_TAB, GUIDES_TAB):
        before = current_rss_mb()
        started = time.perf_counter()
        window.open_encyclopedia_tab(label)
        wait_until(app, lambda label=label: index_is_ready(window, label), 30.0, f"{label} index")
        drain_deferred(app)
        after = current_rss_mb()
        result[label] = {
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
            "rss_before_mb": before,
            "rss_after_mb": after,
            "rss_delta_mb": _delta(after, before),
        }
    return result


def endurance_with_deferred_drain(app: QApplication, window: AtlasWindow) -> dict[str, object]:
    page = current_encyclopedia_page(window)
    if page is None or page.quest_page is None or page.guides_view is None:
        raise RuntimeError("Encyclopedia rich views are not ready.")
    success_view = page.get_achievements_view()
    if success_view is None:
        raise RuntimeError("Success rich view is not ready.")

    quest_ids = _quest_ids(page.quest_page, 50)
    success_ids = _success_ids(success_view, 50)
    guide_ids = _guide_ids(page.guides_view)
    checkpoints: dict[str, object] = {}
    first_guide_ultime: dict[str, object] | None = None

    for cycle in range(1, 51):
        window.open_encyclopedia_tab(QUESTS_TAB)
        wait_until(app, lambda: tab_is_visible(window, QUESTS_TAB), 10.0, "endurance Quests")
        quest_id = quest_ids[(cycle - 1) % len(quest_ids)]
        page.quest_page.select_quest(quest_id)
        wait_until(
            app,
            lambda qid=quest_id: (
                not bool(getattr(page.quest_page, "_detail_pending", False))
                and int(getattr(page.quest_page.quest_detail_view, "current_quest_id", 0) or 0) == qid
            ),
            20.0,
            f"quest {quest_id}",
        )
        drain_deferred(app)

        window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
        wait_until(app, lambda: tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "endurance Success")
        achievement_id = success_ids[(cycle - 1) % len(success_ids)]
        success_view.select_achievement(achievement_id)
        drain_deferred(app)

        window.open_encyclopedia_tab(GUIDES_TAB)
        wait_until(app, lambda: tab_is_visible(window, GUIDES_TAB), 10.0, "endurance Guide")
        guide_id = guide_ids[(cycle - 1) % len(guide_ids)]
        rss_before_guide = current_rss_mb()
        started = time.perf_counter()
        page.guides_view.select_guide(guide_id)
        guide_elapsed = round((time.perf_counter() - started) * 1000.0, 2)
        rss_after_guide = current_rss_mb()

        if guide_id == "guide_complet" and first_guide_ultime is None:
            first_guide_ultime = {
                "cycle": cycle,
                "elapsed_ms": guide_elapsed,
                "rss_before_mb": rss_before_guide,
                "rss_after_mb_before_deferred_drain": rss_after_guide,
                "rss_delta_mb_before_deferred_drain": _delta(rss_after_guide, rss_before_guide),
                "resources_before_deferred_drain": resource_snapshot("guide_ultime_before_deferred_drain"),
                "manual_runtime": manual_runtime_stats(page.guides_view),
            }

        if cycle in CHECKPOINTS:
            before_drain = resource_snapshot(f"cycle_{cycle}_before_deferred_drain")
            drain_deferred(app)
            after_drain = resource_snapshot(f"cycle_{cycle}_after_deferred_drain")
            checkpoints[str(cycle)] = {
                "guide_id": guide_id,
                "before_deferred_drain": before_drain,
                "after_deferred_drain": after_drain,
                "rss_released_by_deferred_drain_mb": _delta(after_drain.get("rss_mb"), before_drain.get("rss_mb")),
                "widgets_released_by_deferred_drain": int(before_drain["widgets"]) - int(after_drain["widgets"]),
            }
        else:
            drain_deferred(app)

        if first_guide_ultime is not None and "resources_after_deferred_drain" not in first_guide_ultime:
            first_guide_ultime["resources_after_deferred_drain"] = resource_snapshot(
                "guide_ultime_after_deferred_drain"
            )

    success_view.close_detail_panel()
    page.guides_view.show_home()
    window.open_encyclopedia_tab(QUESTS_TAB)
    wait_until(app, lambda: tab_is_visible(window, QUESTS_TAB), 10.0, "post-endurance Quests")
    drain_deferred(app, passes=8)
    pump_events(app, 1.0)
    after_idle = resource_snapshot("after_50_cycles_idle_deferred_drained")

    before_gc = resource_snapshot("before_explicit_gc_after_deferred_drain")
    collected = gc.collect()
    drain_deferred(app, passes=4)
    after_gc = resource_snapshot("after_explicit_gc_after_deferred_drain")

    return {
        "distinct_quest_ids": len(set(quest_ids)),
        "distinct_success_ids": len(set(success_ids)),
        "distinct_guide_ids": len(set(guide_ids)),
        "checkpoints": checkpoints,
        "first_guide_ultime": first_guide_ultime,
        "after_idle": after_idle,
        "explicit_gc": {
            "collected_objects": collected,
            "before": before_gc,
            "after": after_gc,
            "rss_delta_mb": _delta(after_gc.get("rss_mb"), before_gc.get("rss_mb")),
        },
    }


def measure() -> dict[str, object]:
    app = QApplication.instance() or QApplication([])
    install_instrumentation()
    patch_method(QuestDetails, "get", "quest_details.get")
    install_source_instrumentation()

    window = AtlasWindow()
    window.show()
    drain_deferred(app)
    pump_events(app, 0.25)

    result: dict[str, object] = {
        "startup": resource_snapshot("startup_retention_run"),
        "indexes": open_indexes(app, window),
    }

    try:
        page = current_encyclopedia_page(window)
        if page is None:
            raise RuntimeError("Encyclopedia page missing.")

        window.open_encyclopedia_tab(ACHIEVEMENTS_TAB)
        wait_until(app, lambda: tab_is_visible(window, ACHIEVEMENTS_TAB), 10.0, "Success revisit")
        rss_before_success = current_rss_mb()
        result["first_success"] = first_success_detail(app, window)
        drain_deferred(app)
        result["first_success"]["rss_after_deferred_drain_mb"] = current_rss_mb()
        result["first_success"]["rss_delta_after_deferred_drain_mb"] = _delta(current_rss_mb(), rss_before_success)
        result["achievement_provider"] = provider_stats(page.service.achievement_provider)
        result["achievement_source_reads"] = list(_SOURCE_EVENTS)
        result["quest_detail_cache_after_success"] = quest_detail_cache_info(page)

        window.open_encyclopedia_tab(GUIDES_TAB)
        wait_until(app, lambda: tab_is_visible(window, GUIDES_TAB), 10.0, "Guide revisit")
        details_before = quest_detail_cache_info(page)
        result["first_guide"] = first_guide_detail(app, window)
        details_after = quest_detail_cache_info(page)
        result["quest_detail_cache_first_guide"] = {
            "before": details_before,
            "after": details_after,
            "loads_delta": int(details_after.get("loads", 0)) - int(details_before.get("loads", 0)),
            "records_delta": int(details_after.get("records", 0)) - int(details_before.get("records", 0)),
        }
        drain_deferred(app)
        result["first_guide"]["resources_after_deferred_drain"] = resource_snapshot(
            "first_guide_after_deferred_drain"
        )

        result["endurance"] = endurance_with_deferred_drain(app, window)
    finally:
        window._shutdown_background_services()
        window.hide()
        window.deleteLater()
        drain_deferred(app, passes=8)
        result["after_shutdown_deferred_drained"] = resource_snapshot("after_shutdown_deferred_drained")
        restore_source_instrumentation()
        restore_instrumentation()

    return result


def main() -> int:
    payload = {
        "schema_version": 1,
        "diagnostic_only": True,
        "reference_sha": REFERENCE_SHA,
        "environment": {
            "git_head": git_head(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pyside": PYSIDE_VERSION,
            "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
            "notes": (
                "Second Phase 7B diagnostic run. Explicit DeferredDelete draining distinguishes real lifecycle retention from "
                "processEvents-only harness artifacts. Also measures AchievementProvider source reads/retained graph, "
                "QuestDetails lazy loads, and first Guide Ultime retained runtime."
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
