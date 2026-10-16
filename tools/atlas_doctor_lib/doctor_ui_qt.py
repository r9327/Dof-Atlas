from __future__ import annotations

"""Vetted real Guide/Encyclopedia scenario, invoked only by Doctor UI.

Application imports deliberately occur after the coordinator has isolated all
mutable paths. There is one scene, one Qt thread and one evidence directory.
"""

import json
import os
import platform
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from tools.atlas_doctor_lib.doctor_ui import required_assertions, verdict, write_json


def settle(predicate=lambda: True, timeout=3.0) -> bool:
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    end = time.monotonic() + timeout
    # DeferredDelete is not delivered by a processEvents-only loop.
    while True:
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QTest.qWait(10)
        if predicate():
            return True
        if time.monotonic() >= end:
            return False


def widget_tree(root) -> list[dict]:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

    nodes = []

    def visit(widget, parent_id=None, rank=0):
        if len(nodes) >= 5000:
            raise RuntimeError("Widget inventory exceeds bounded V1 scene")
        name = widget.objectName() or type(widget).__name__
        key = f"{parent_id}/{name}[{rank}]" if parent_id else name
        point = widget.mapTo(root, QPoint(0, 0))
        rect = [point.x(), point.y(), widget.width(), widget.height()]
        # Some production widgets expose a `layout` attribute that shadows the
        # QWidget method. Use the actual Qt descriptor for the inventory.
        layout = QWidget.layout(widget)
        row = {"id": key, "parent": parent_id, "rank": rank,
               "overlay_index": len(nodes),
               "class": type(widget).__name__, "objectName": widget.objectName(),
               "visible": widget.isVisible(), "hidden": widget.isHidden(),
               "enabled": widget.isEnabled(), "rect": rect,
               "layout": type(layout).__name__ if layout else None,
               "layout_count": layout.count() if layout else 0,
               "accessible_name": widget.accessibleName(),
               "tooltip": widget.toolTip()[:160],
               "source": type(widget).__module__ + "." + type(widget).__qualname__}
        owner = widget
        while owner is not None:
            card = getattr(owner, "card", None)
            if isinstance(card, dict) and card.get("manual_stage_id"):
                row["business_anchor"] = {"stage_id": card["manual_stage_id"],
                                          "guide_id": getattr(getattr(owner, "service", None), "guide_id", "guide_complet")}
                break
            owner = owner.parentWidget()
        # Only the isolated public-data scene is exported, never an arbitrary window.
        if isinstance(widget, (QLabel, QAbstractButton)):
            row["text"] = widget.text()[:240]
        if isinstance(widget, QAbstractButton):
            row.update(checkable=widget.isCheckable(), checked=widget.isChecked())
            family = {"GuideManualQuestInlineButton": "quest-navigation",
                      "GuideManualPageCheck": "manual-page-progress",
                      "GuideManualCombatCheck": "combat-objective-progress",
                      "GuideManualPrev": "page-navigation", "GuideManualNextButton": "page-navigation",
                      "GuideManualGuideButton": "catalog-navigation",
                      "GuideManualProgressLock": "route-lock"}.get(widget.objectName())
            row.update(control_family=family or "unmapped",
                       oracle_provider="Doctor V1 scenario assertions" if family else None,
                       coverage="CONTRACT_AVAILABLE" if family else "NOT_COVERED")
        nodes.append(row)
        for i, child in enumerate(widget.children()):
            if isinstance(child, QWidget):
                visit(child, key, i)

    visit(root)
    return nodes


def click_target(root, target, scroll=None) -> dict:
    """Check the real stacking/clip result before sending a QTest mouse event."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QCheckBox

    if scroll is not None and scroll.isAncestorOf(target):
        scroll.ensureWidgetVisible(target, 8, 8)
        settle()
    points = [target.rect().center(), target.visibleRegion().boundingRect().center()]
    if isinstance(target, QCheckBox):
        points.insert(0, QPoint(8, target.height() // 2))
    accessible = False
    point = points[0]
    hit = None
    for candidate in points:
        candidate_hit = root.childAt(target.mapTo(root, candidate))
        if (target.isVisible() and target.isEnabled()
                and (candidate_hit is target or candidate_hit is not None and target.isAncestorOf(candidate_hit))):
            point, hit, accessible = candidate, candidate_hit, True
            break
    result = {"accessible": bool(accessible), "target": target.objectName(),
              "hit": hit.objectName() if hit else None,
              "point": [point.x(), point.y()]}
    names = []
    ancestor = target
    while ancestor is not None:
        names.append(ancestor.objectName() or type(ancestor).__name__)
        if ancestor is root:
            break
        ancestor = ancestor.parentWidget()
    result["source_widget_path"] = "/".join(reversed(names))
    if accessible:
        QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, point)
        settle()
    return result


def geometry_observations(root, view) -> dict:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QAbstractButton

    buttons = [b for b in view.findChildren(QAbstractButton) if b.isVisible()]
    collisions = []
    for i, left in enumerate(buttons):
        a = left.visibleRegion().translated(left.mapTo(root, QPoint()))
        for right in buttons[i + 1:]:
            if left.isAncestorOf(right) or right.isAncestorOf(left):
                continue
            b = right.visibleRegion().translated(right.mapTo(root, QPoint()))
            intersection = a.intersected(b).boundingRect()
            if intersection.width() > 2 and intersection.height() > 2:
                collisions.append([left.objectName(), right.objectName()])
    inaccessible = []
    old_scroll = view.scroll.verticalScrollBar().value()
    for button in buttons:
        if not button.isEnabled():
            continue
        if view.scroll.isAncestorOf(button):
            view.scroll.ensureWidgetVisible(button, 8, 8)
            settle()
        point = button.rect().center()
        hit = root.childAt(button.mapTo(root, point))
        if hit is not button and not (hit is not None and button.isAncestorOf(hit)):
            inaccessible.append(button.objectName())
    view.scroll.verticalScrollBar().setValue(old_scroll)
    settle()
    viewport = view.scroll.viewport()
    # Compare content width as well as the scrollbar; AlwaysOff can hide overflow.
    overflow = view.content.width() > viewport.width() + 2
    return {"collisions": collisions, "inaccessible": inaccessible,
            "horizontal_overflow": overflow,
            "viewport": [viewport.width(), viewport.height()],
            "content_width": view.content.width()}


class UiSession:
    def __init__(self, folder: Path, mode: str):
        self.folder = folder
        self.mode = mode
        self.assertions = []
        self.required = []
        self.evidence = []
        self.journal = []
        self.step = 0
        self.scenario = "setup"
        self.guide_id = ""
        self.card_id = ""
        self.started = time.monotonic()

    def snapshot(self, root) -> list[str]:
        from PySide6.QtGui import QColor, QPainter, QPen
        from PySide6.QtCore import QRect

        self.step += 1
        if self.step > 120:
            raise RuntimeError("Doctor UI action budget exceeded")
        prefix = f"{self.step:03d}-{self.scenario}"
        tree = widget_tree(root)
        files = [prefix + "-tree.json"]
        write_json(self.folder / files[0], tree)
        if self.mode in {"all", "capture"}:
            pixmap = root.grab()
            if pixmap.isNull() or not pixmap.save(str(self.folder / (prefix + ".png"))):
                raise RuntimeError("Qt PNG capture failed")
            files.append(prefix + ".png")
            if self.step == 1:
                overlay = pixmap.copy()
                painter = QPainter(overlay)
                painter.setPen(QPen(QColor("orange"), 1))
                for i, row in enumerate(tree):
                    if row["visible"] and row["objectName"].startswith("GuideManual"):
                        painter.drawRect(QRect(*row["rect"]))
                        painter.drawText(row["rect"][0], row["rect"][1] + 10, str(i))
                painter.end()
                overlay_name = prefix + "-blocks.png"
                if not overlay.save(str(self.folder / overlay_name)):
                    raise RuntimeError("Qt block overlay failed")
                files.append(overlay_name)
        self.evidence.extend(files)
        return files

    def check(self, key, action, expected, observed, passed, root, *, status=None):
        assertion_id = self.scenario + "/" + key
        self.required.append(assertion_id)
        row = {"assertion_id": assertion_id, "control_id": key,
               "scenario_id": self.scenario, "guide_id": self.guide_id,
               "card_id": self.card_id, "action": action, "expected": expected,
               "observed": observed, "assertion_status": status or ("PASS" if passed else "FAIL"),
               "evidence_ids": self.snapshot(root),
               "source_widget_path": observed.get("click", {}).get("source_widget_path", root.objectName())
               if isinstance(observed, dict) else root.objectName()}
        self.assertions.append(row)
        self.journal.append({"sequence": self.step, "elapsed_seconds": round(time.monotonic() - self.started, 3), **row})
        # Durable journal survives a later Qt crash or timeout.
        write_json(self.folder / "actions.json", self.journal)


def build_scene(temp: Path):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
    from app.modules.encyclopedia.services import QuestGraphService
    from app.modules.encyclopedia.views import EncyclopediaPage
    from app.ui.theme import atlas_stylesheet

    app = QApplication.instance() or QApplication([])
    if QThread.currentThread() != app.thread():
        raise RuntimeError("Doctor UI must run on the Qt application thread")
    app.setStyleSheet(atlas_stylesheet())
    quests = QuestProvider()
    if quests.count() == 0:
        raise RuntimeError("Real public Quest catalog is empty")
    achievements = AchievementProvider(quest_provider=quests)
    achievements.load_all()
    guides = GuideProvider(quest_provider=quests, achievement_provider=achievements)
    guides.load_all()
    paths = {}
    for name in ("quests", "achievements", "guides", "profiles", "clients", "items"):
        paths[name] = temp / (name + ".json")
        write_json(paths[name], {})
    page = EncyclopediaPage(
        lambda _message: None, quest_provider=quests,
        achievement_provider=achievements, guide_provider=guides,
        quest_graph=QuestGraphService(quests, guides, achievements, eager=False),
        progress_path=paths["quests"], achievement_progress_path=paths["achievements"],
        guide_progress_path=paths["guides"], profile_path=paths["profiles"],
        client_index_path=paths["clients"], owned_items_path=paths["items"])
    page.resize(1200, 800)
    page.set_character_key("character:990000001")
    # Upgrade through the production owner; no substitute Guide or navigation mock.
    owner = page.ensure_full_guides_view()
    if not owner._runtime_ready:
        owner.hydrate_runtime(graph=page._quest_graph)
    page.show()
    settle()
    return app, page, owner


def open_guide(page, owner, guide_id):
    from app.modules.encyclopedia.constants import GUIDES_TAB
    from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView

    page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
    if not owner.select_guide(guide_id):
        raise RuntimeError("Guide cannot be opened: " + guide_id)
    settle()
    view = owner.stack.currentWidget()
    if not isinstance(view, SharedGuideManualView) or not view.service.cards:
        raise RuntimeError("Real SharedGuideManualView unavailable")
    return view


def sheet_observations(view, expected_card) -> dict:
    from PySide6.QtWidgets import QFrame, QLabel

    sheets = [s for s in view.findChildren(QFrame, "GuideManualSheet") if s.isVisible()]
    result = {"sheet_count": len(sheets), "expected_stage_id": expected_card.get("manual_stage_id"),
              "stage_ids": [s.card.get("manual_stage_id") for s in sheets],
              "mounted": all(s.parentWidget() is view.content for s in sheets)}
    # Provenance-aware line oracle: reconstruct expected HTML from the canonical
    # service rows using the production formatter, then compare a multiset.
    expected = []
    if len(sheets) == 1:
        sheet = sheets[0]
        # Formatting coalesces repeated coordinates; replay that sequence from
        # its initial state and restore it so inspection cannot mutate the view.
        last_position = sheet._last_route_position_key
        sheet._last_route_position_key = ""
        sections = sheet._without_prepare_duplicates(
            view.service.manual_sections_for_card(view.character_key, expected_card))
        for section_key in ("prepare", "now", "opportunity", "keep", "boss", "before_leave"):
            rows = sections.get(section_key, [])
            for row in rows:
                text = str(row.get("text") or "").strip()
                if not text:
                    continue
                position = sheet._display_position(str(row.get("position") or ""))
                prefix = "⚠ " if row.get("kind") == "warning" else "• "
                expected.append(sheet._format_line_html(prefix, position, text,
                                sheet._npc_names(text), sheet._resource_names))
        sheet._last_route_position_key = last_position
        actual = []
        for line_row in sheet.findChildren(QFrame, "GuideManualLineRow"):
            actual.extend(label.text() for label in line_row.findChildren(QLabel)
                          if label.parentWidget() is line_row)
        result.update(missing_lines=list((Counter(expected) - Counter(actual)).elements())[:5],
                      stale_or_duplicate_lines=list((Counter(actual) - Counter(expected)).elements())[:5],
                      expected_line_count=len(expected), actual_line_count=len(actual))
    else:
        result.update(missing_lines=["No unique mounted sheet"], stale_or_duplicate_lines=[])
    return result


def check_sheet(session, page, view, key):
    card = view.service.cards[view.view_index]
    session.card_id = str(card.get("manual_stage_id") or "")
    observed = sheet_observations(view, card)
    ok = (observed["sheet_count"] == 1 and observed["mounted"]
          and observed["stage_ids"] == [card.get("manual_stage_id")]
          and not observed["missing_lines"] and not observed["stale_or_duplicate_lines"])
    session.check(key, "Inspect mounted sheet after Qt DeferredDelete", "One current canonical sheet and exact current lines",
                  observed, ok, page)


def exercise_guide(session, page, owner, guide_id, repeats, smoke=False):
    from PySide6.QtWidgets import QPushButton, QFrame, QCheckBox
    from shiboken6 import isValid

    session.guide_id = guide_id
    view = open_guide(page, owner, guide_id)
    view._show_index(0)
    settle()
    indices = (0,) if smoke else ((0, 2) if guide_id == "guide_complet" else (0, 7))
    if session.mode in {"capture", "inspect"}:
        for index in indices:
            view._show_index(index)
            settle()
            session.card_id = str(view.service.cards[index].get("manual_stage_id") or "")
            for width, height in ((1200, 800), (960, 640)):
                page.resize(width, height)
                settle()
                session.snapshot(page)
                view.scroll.verticalScrollBar().setValue(view.scroll.verticalScrollBar().maximum())
                settle()
                session.snapshot(page)
        return
    check_sheet(session, page, view, "open")
    for index in indices:
        if index >= len(view.service.cards):
            raise RuntimeError("Required canonical page missing")
        view._show_index(index)
        settle()
        for width, height in ((1200, 800), (960, 640)):
            page.resize(width, height)
            settle()
            check_sheet(session, page, view, f"page-{index + 1}-{width}")
            observed = geometry_observations(page, view)
            session.check(f"geometry-{index + 1}-{width}", "Resize, scroll each interactive target, Qt hit-test",
                          "No collision, inaccessible control or hidden horizontal overflow", observed,
                          not any(observed[k] for k in ("collisions", "inaccessible", "horizontal_overflow")), page)
            view.scroll.verticalScrollBar().setValue(view.scroll.verticalScrollBar().maximum())
            settle()
            session.snapshot(page)
            view.scroll.verticalScrollBar().setValue(0)
            settle()
    view._show_index(0)
    settle()
    for turn in range(1 if smoke else repeats):
        previous_sheet = view.findChild(QFrame, "GuideManualSheet")
        click = click_target(page, view.next_button)
        observed = {"click": click, "index": view.view_index}
        session.check(f"next-{turn}", "QTest click Suivant", "Index 1 after real click",
                      observed, click["accessible"] and view.view_index == 1, page)
        session.check(f"destroy-{turn}", "Flush DeferredDelete", "Previous sheet destroyed",
                      {"old_sheet_alive": isValid(previous_sheet)}, not isValid(previous_sheet), page)
        click = click_target(page, view.prev_button)
        session.check(f"previous-{turn}", "QTest click Précédent", "Index 0 after real click",
                      {"click": click, "index": view.view_index}, click["accessible"] and view.view_index == 0, page)
        view.refresh_external_progress()
        settle()
        check_sheet(session, page, view, f"refresh-{turn}")
    # Persisted lock and actual navigation blocking are distinct assertions.
    lock = view.route_lock_check
    trace_path = session.folder / "runtime-trace.json"
    if not trace_path.exists():
        from tools.atlas_doctor_lib.runtime_observation import RuntimeObserver

        # Reuse Doctor's bounded observer on one small real interaction. Tracing
        # provider hydration would turn a targeted UI check into a costly scan.
        observer = RuntimeObserver(Path(__file__).resolve().parents[2], max_events=200)
        with observer:
            click = click_target(page, lock)
        write_json(trace_path, observer.report())
        session.evidence.append(trace_path.name)
    else:
        click = click_target(page, lock)
    view.service.reload_progress()
    saved = view.service.manual_checked(view.character_key, view.ROUTE_LOCK_PROGRESS_KEY)
    view._jump_from_progress(1.0)
    session.check("lock", "QTest lock then attempt progress navigation", "Lock persisted, accessible label and index unchanged",
                  {"click": click, "saved": saved, "index": view.view_index, "label": lock.accessibleName()},
                  click["accessible"] and saved and view.view_index == 0 and lock.accessibleName() == "Verrouillé", page)
    click_target(page, lock)
    view.service.reload_progress()
    session.check("unlock", "QTest unlock then reload", "Unlocked in service and accessibility label",
                  {"saved": view.service.manual_checked(view.character_key, view.ROUTE_LOCK_PROGRESS_KEY),
                   "label": lock.accessibleName()},
                  not view.service.manual_checked(view.character_key, view.ROUTE_LOCK_PROGRESS_KEY)
                  and lock.accessibleName() == "Déverrouillé", page)
    # Blank temporary profile is never evidence for automatic in-game completion.
    card = view.service.cards[0]
    automatic = view.service.card_auto_complete(view.character_key, card)
    session.check("no-game-proof", "Evaluate automatic completion on blank profile", False, automatic, not automatic, page)
    button = view.findChild(QPushButton, "GuideManualPageCheck")
    click = click_target(page, button)
    view.service.reload_progress()
    saved = view.service.page_checked("character:990000001", card, 0)
    session.check("manual-persist", "QTest Valider then reload canonical services", "Page 1 persisted checked",
                  {"click": click, "saved": saved}, click["accessible"] and saved, page)
    view.set_character_key("character:990000002")
    isolated = not view.service.page_checked("character:990000002", card, 0)
    view.set_character_key("character:990000001")
    view._show_index(0)
    settle()
    restored = view.findChild(QPushButton, "GuideManualPageCheck").isChecked()
    session.check("character-isolation", "Switch character, reload then return", "Other character clear; original check restored",
                  {"other_clear": isolated, "original_checked": restored}, isolated and restored, page)
    if not smoke:
        combat = None
        # Bound scene discovery; never traverse the entire Guide or hydrate all quests.
        for combat_index in range(min(32, len(view.service.cards))):
            view._show_index(combat_index)
            settle()
            sheet = view.findChild(QFrame, "GuideManualSheet")
            checks = sheet.findChildren(QCheckBox, "GuideManualCombatCheck")
            if checks:
                combat = (combat_index, sheet, checks[0])
                break
        if combat is None:
            session.check("combat", "Find combat in first 32 canonical pages", "Real combat checkbox with public objective oracle",
                          "No combat found within V1 bound", False, page, status="BLOCKED")
        else:
            combat_index, sheet, checkbox = combat
            session.card_id = str(sheet.card.get("manual_stage_id") or "")
            # The production renderer owns objective provenance/order and labels.
            sections = sheet._without_prepare_duplicates(view.service.manual_sections_for_card(view.character_key, sheet.card))
            # Already-rendered keys are intentionally excluded by the renderer's
            # allocator. Replay allocation from its initial state, then restore.
            rendered_keys = set(sheet._rendered_combat_keys)
            sheet._rendered_combat_keys.clear()
            targets = []
            for section_key in ("prepare", "now", "opportunity", "keep", "boss", "before_leave"):
                for row in sections.get(section_key, []):
                    found = sheet._combat_targets_for_row(row, section_key)
                    targets.extend(target for target in found if sheet._combat_key(target) not in sheet._rendered_combat_keys)
                    sheet._rendered_combat_keys.update(sheet._combat_key(target) for target in found)
            sheet._rendered_combat_keys = rendered_keys
            expected_labels = []
            for target in targets:
                text = f"{int(target['quantity'])} × {target['monster']}"
                if target.get("quest_name"):
                    text += " — " + target["quest_name"]
                expected_labels.append(text)
            observed_labels = [box.text() for box in checks]
            # Two distinct objectives may legitimately have the same label.
            # Canonical allocation order + objective keys is the oracle, not
            # text uniqueness or a guessed callback target.
            if not targets or observed_labels != expected_labels:
                session.check("combat", "Resolve rendered combat objective provenance", "One canonical objective",
                              {"expected_labels": expected_labels, "observed_labels": observed_labels,
                               "rendered_targets": targets}, False, page, status="REVIEW")
            else:
                qid, oid = sheet._combat_key(targets[0])
                expected_checked = not checkbox.isChecked()
                from PySide6.QtTest import QSignalSpy

                toggled = QSignalSpy(checkbox.toggled)
                click = click_target(page, checkbox, view.scroll)
                toggled_count = toggled.count()
                session.snapshot(page)
                view.service.quest_progress.reload()
                saved = view.service.quest_progress.is_objective_completed(view.character_key, qid, oid)
                view._show_index(combat_index)
                settle()
                boxes = view.findChildren(QCheckBox, "GuideManualCombatCheck")
                restored = bool(boxes and boxes[0].text() == expected_labels[0]
                                and boxes[0].isChecked() == expected_checked
                                and boxes[0].property("state") == ("done" if expected_checked else "todo"))
                session.check("combat", "QTest combat checkbox, reload service and reopen page",
                              {"quest_id": qid, "objective_id": oid, "checked": expected_checked},
                              {"click": click, "toggled_count": toggled_count,
                               "saved": saved, "restored": restored,
                               "first_failed_transition": "checkbox-toggled" if toggled_count != 1
                               else "objective-persistence" if saved != expected_checked else None},
                              click["accessible"] and toggled_count == 1 and saved == expected_checked and restored, page)
        for width, height in ((1200, 800), (960, 640)):
            page.resize(width, height)
            settle()
            observed = geometry_observations(page, view)
            session.check(f"combat-geometry-{width}", "Resize real combat page and inspect viewport/hit-test",
                          "Combat controls fit without hidden horizontal overflow", observed,
                          not any(observed[k] for k in ("collisions", "inaccessible", "horizontal_overflow")),
                          page, status="BLOCKED" if combat is None else None)
    # Return to catalog using production Guide control, then reopen via owner.
    view.go_active()
    settle()
    click = click_target(page, view.guide_button)
    catalog_visible = owner.stack.currentWidget() is not view
    reopened = open_guide(page, owner, guide_id)
    session.check("home-reopen", "QTest Guide then reopen canonical guide", "Catalog reached and real guide restored",
                  {"click": click, "catalog": catalog_visible, "same_view": reopened is view},
                  click["accessible"] and catalog_visible and reopened is view, page)
    if not smoke:
        other_id = "dofus_sylvestre" if guide_id == "guide_complet" else "guide_complet"
        other = open_guide(page, owner, other_id)
        returned = open_guide(page, owner, guide_id)
        session.check("guide-return", "Change guide then return", "Correct renderer visible; other guide hidden",
                      {"current": returned is view, "other_visible": other.isVisible()},
                      returned is view and not other.isVisible(), page)
    check_sheet(session, page, view, "final-sheet")


def quest_outcome(page, expected_id, signal_rows) -> dict:
    from app.modules.encyclopedia.constants import QUESTS_TAB

    quests = page.quest_page
    detail = getattr(quests, "quest_detail_view", None)
    return {"signal_ids": [int(row[0]) for row in signal_rows],
            "expected_quest_id": expected_id,
            "active_tab": page.current_tab_label(), "expected_tab": QUESTS_TAB,
            "quests_initialized": quests is not None,
            "selected_quest_id": getattr(quests, "selected_quest_id", None),
            "detail_visible": detail is not None and detail.isVisible(),
            "detail_quest_id": getattr(detail, "current_quest_id", None),
            "lazy_pending": bool(getattr(quests, "_detail_pending", False))}


def first_quest_failure(observed: dict) -> str | None:
    expected = observed["expected_quest_id"]
    checks = ((observed["signal_ids"] == [expected], "questRequested"),
              (observed["active_tab"] == observed["expected_tab"], "QUESTS_TAB"),
              (observed["quests_initialized"] and not observed["lazy_pending"], "lazy-initialization"),
              (observed["selected_quest_id"] == expected, "selected_quest_id"),
              (observed["detail_visible"], "detail-visible"),
              (observed["detail_quest_id"] == expected, "detail-quest-id"))
    return next((label for ok, label in checks if not ok), None)


def exercise_quest_links(session, page, owner):
    from PySide6.QtTest import QSignalSpy
    from PySide6.QtWidgets import QFrame, QToolButton

    for guide_id in ("guide_complet", "dofus_sylvestre"):
        session.guide_id = guide_id
        view = open_guide(page, owner, guide_id)
        view._show_index(0)
        settle()
        sheet = view.findChild(QFrame, "GuideManualSheet")
        buttons = sheet.findChildren(QToolButton, "GuideManualQuestInlineButton")
        if not buttons:
            raise RuntimeError("Required canonical page has no quest link")
        button = buttons[0]
        candidates = [int(qid) for qid in sheet.card.get("manual_quest_ids", [])
                      if (quest := page.quest_provider.get_quest(int(qid))) is not None
                      and quest.name == button.toolTip()]
        if len(candidates) != 1:
            raise RuntimeError("Quest target has no unique public-data oracle")
        quest_id = candidates[0]
        session.card_id = str(sheet.card.get("manual_stage_id"))
        for iteration in range(2):
            view._show_index(0)
            settle()
            sheet = view.findChild(QFrame, "GuideManualSheet")
            button = sheet.findChildren(QToolButton, "GuideManualQuestInlineButton")[0]
            spy = QSignalSpy(sheet.questRequested)
            click = click_target(page, button, view.scroll)
            settle(lambda: first_quest_failure(quest_outcome(
                page, quest_id, [spy.at(i) for i in range(spy.count())])) is None, timeout=5)
            observed = quest_outcome(page, quest_id, [spy.at(i) for i in range(spy.count())])
            failure = first_quest_failure(observed)
            observed.update(click=click, first_failed_transition=failure)
            session.check(f"{guide_id}-quest-{iteration}", "QTest real inline link → LinkService → Encyclopedia → lazy Quest detail",
                          {"quest_id": quest_id, "detail_visible": True, "signal_count": 1},
                          observed, click["accessible"] and failure is None, page)
            open_guide(page, owner, guide_id)
            settle()


def worker(folder: Path) -> int:
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    session = UiSession(folder, request["mode"])
    report = {"schema_version": 1, "candidate_sha": manifest["candidate_sha"],
              "selected_scenarios": request["scenarios"], "status": "BLOCKED",
              "tests_executed": False, "evidence_level": "Qt offscreen",
              "not_covered": ["installed Windows EXE", "real Dofus/Npcap signals",
                              "semantic text quality", "NPC/item/travel actions"]}
    page = None
    old_exception_hook = sys.excepthook
    qt_errors = []

    def exception_hook(kind, value, tb):
        qt_errors.append("".join(traceback.format_exception(kind, value, tb)))

    try:
        if not os.environ.get("DOFUS_ATLAS_USER_ROOT") or os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            raise RuntimeError("Doctor UI requires isolated paths and explicit offscreen mode")
        sys.excepthook = exception_hook
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion
        from shiboken6 import isValid

        app, page, owner = build_scene(Path(os.environ["DOFUS_ATLAS_USER_ROOT"]))
        screen = app.primaryScreen()
        manifest.update(python=platform.python_version(), pyside=pyside_version,
                        qt=qVersion(), platform=platform.platform(), mode=request["mode"],
                        qt_platform=app.platformName(), dpi=screen.logicalDotsPerInch(),
                        device_pixel_ratio=screen.devicePixelRatio(),
                        data_source="canonical local public catalog + authored Guide data",
                        progress_source="temporary isolated canonical services")
        write_json(folder / "manifest.json", manifest)
        for name in request["scenarios"]:
            session.scenario = name
            if name == "guide-quests":
                if request["mode"] in {"all", "verify"}:
                    exercise_quest_links(session, page, owner)
                else:
                    session.snapshot(page)
            else:
                gid = "dofus_sylvestre" if name == "guides-lanyel" else "guide_complet"
                exercise_guide(session, page, owner, gid, request["repeats"], name == "validator-smoke")
        report["tests_executed"] = request["mode"] in {"all", "verify"}
        if report["tests_executed"]:
            session.scenario = "session"
            session.check("qt-exceptions", "Deliver all Qt callbacks", "No callback exception", qt_errors, not qt_errors, page)
        page.close()
        page.deleteLater()
        settle()
        destroyed = not isValid(page)
        page = None
        if not destroyed:
            raise RuntimeError("Scene still alive after DeferredDelete")
        required = required_assertions(request["scenarios"], request["repeats"])
        report["status"] = verdict(session.assertions, required) if report["tests_executed"] else "RECORDED"
        report["scene_destroyed"] = destroyed
    except Exception as exc:
        report.update(status="BLOCKED", error=f"{type(exc).__name__}: {exc}",
                      traceback=traceback.format_exc())
    finally:
        if page is not None:
            page.close()
            page.deleteLater()
            settle()
        sys.excepthook = old_exception_hook
    report.update(assertions=session.assertions,
                  tests_executed=bool(session.assertions) and request["mode"] in {"all", "verify"},
                  required_assertions=required_assertions(request["scenarios"], request["repeats"]),
                  repeats=request["repeats"],
                  required_evidence=session.evidence,
                  coverage=dict(Counter(a["assertion_status"] for a in session.assertions)))
    write_json(folder / "ui_verdict.json", report)
    return 0 if report["status"] in {"PASS", "RECORDED"} else 1


if __name__ == "__main__":
    raise SystemExit(worker(Path(sys.argv[1])))
