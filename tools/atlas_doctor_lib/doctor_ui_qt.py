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
    from PySide6.QtWidgets import QApplication

    end = time.monotonic() + timeout
    # DeferredDelete is not delivered by a processEvents-only loop.
    while True:
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        # The production event loop releases the GIL while it waits.  QTest's
        # nested qWait can retain it on Windows and starve Atlas' Python detail
        # workers, turning a sub-second load into a false UI timeout.
        time.sleep(0.01)
        # Deliver layout, scroll and timer work that became ready while the
        # thread scheduler was yielded, matching the next real event-loop turn.
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
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



def configure_validation_fonts(app) -> dict:
    """Register Windows fonts for Qt's isolated offscreen scene, without app changes."""
    from PySide6.QtGui import QFont, QFontDatabase

    font_dir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows") / "Fonts"
    registered = []
    for filename in ("segoeui.ttf", "arial.ttf", "tahoma.ttf", "calibri.ttf"):
        path = font_dir / filename
        if path.is_file():
            token = QFontDatabase.addApplicationFont(str(path))
            if token >= 0:
                families = list(QFontDatabase.applicationFontFamilies(token))
                registered.append({"file": filename, "families": families})
    if registered and registered[0]["families"]:
        app.setFont(QFont(registered[0]["families"][0], 10))
    return {"windows_font_dir": font_dir.is_dir(), "loaded": registered,
            "application_font_family": app.font().family()}


def _glyph_signature(font, letter: str) -> str:
    import hashlib
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage, QPainter

    canvas = QImage(96, 72, QImage.Format_ARGB32)
    canvas.fill(Qt.white)
    painter = QPainter(canvas)
    try:
        painter.setPen(Qt.black)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, 96, 72), Qt.AlignCenter, letter)
    finally:
        painter.end()
    return hashlib.sha256(canvas.bits().tobytes()).hexdigest()


def glyph_legibility_probe(page, *, screenshots=()) -> dict:
    """Reject square/tofu substitutions for text in actual live widget fonts."""
    from PySide6.QtGui import QFont, QFontInfo, QFontMetrics
    from PySide6.QtWidgets import QLabel

    labels = [label for label in page.findChildren(QLabel)
              if label.isVisible() and label.text().strip()]
    title = next((label for label in labels if label.objectName() == "AchievementDetailTitle"), None)
    chosen = ([title] if title is not None else []) + [label for label in labels if label is not title][:3]
    samples = ("A", "W", "m", "é", "ç", "8")
    results = []
    for label in chosen:
        font = QFont(label.font())
        font.setPixelSize(34)
        metrics = QFontMetrics(font)
        signatures = {char: _glyph_signature(font, char) for char in samples}
        coverage = {char: bool(metrics.inFontUcs4(ord(char))) for char in samples}
        results.append({
            "widget": label.objectName(), "requested_font": font.family(),
            "resolved_font": QFontInfo(font).family(),
            "unique_raster_glyphs": len(set(signatures.values())),
            "glyph_coverage": coverage, "raster_sha256": signatures,
            "passed": all(coverage.values()) and len(set(signatures.values())) == len(samples),
        })
    # Actual PNG pixels are authoritative. Qt can report distinct available
    # glyphs while its live stylesheet still paints hundreds of identical
    # fallback squares, as observed in the old success screenshots.
    from PySide6.QtGui import QImage
    from tools.atlas_doctor_lib.ui_raster_oracle import detect_replacement_squares

    files = list(dict.fromkeys(Path(name) for name in screenshots))
    # Exactly the PNGs actually attached to all prior assertions: a clean
    # final screen must not hide an earlier unreadable capture.
    if not files:
        frames = [("live-grab", page.grab().toImage())]
    else:
        frames = [(path.name, QImage(str(path))) for path in files]
    raster_checks = []
    for name, image in frames:
        if image.isNull():
            raster = {"status": "BLOCKED", "reason": "MISSING_OR_INVALID_PNG"}
        else:
            image = image.convertToFormat(QImage.Format_Grayscale8)
            raster = detect_replacement_squares(
                image.bits().tobytes(), image.width(), image.height(),
                image.bytesPerLine(),
            )
        raster_checks.append({"capture": name, **raster})
    failed_captures = [row for row in raster_checks if row["status"] != "PASS"]
    font_passed = bool(results) and all(r["passed"] for r in results)
    passed = font_passed and not failed_captures
    raster = {"status": "FAIL" if failed_captures else "PASS",
              "captures_checked": len(raster_checks),
              "total_hollow_boxes": sum(row.get("box_count", 0) for row in raster_checks),
              "bad_captures": failed_captures[:20],
              "captures": raster_checks}
    return {"status": "PASS" if passed else "FAIL",
            "reason": ("REPEATED_SCREENSHOT_TOFU" if raster["status"] != "PASS"
                       else "FONT_RASTER_OK" if font_passed
                       else "MISSING_OR_SQUARE_FONT_GLYPHS"),
            "sample_chars": list(samples), "labels": results,
            "screenshot_raster": raster,
            "limits": "Actual rendered raster plus sampled Qt font glyphs; not OCR or full visual/contrast certification."}


def build_scene(temp: Path):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
    from app.modules.encyclopedia.services import QuestGraphService
    from app.modules.encyclopedia.views import EncyclopediaPage
    from app.quest_catalog_details import (
        ensure_detail_source_offsets,
        ensure_lazy_catalog_cache,
    )
    from app.ui.theme import atlas_stylesheet

    app = QApplication.instance() or QApplication([])
    app._doctor_font_registration = configure_validation_fonts(app)
    if QThread.currentThread() != app.thread():
        raise RuntimeError("Doctor UI must run on the Qt application thread")
    app.setStyleSheet(atlas_stylesheet())
    # Production blocks on the reconstructible startup cache domains before
    # exposing Encyclopedia.  Keep the Doctor scene equally cold and honest:
    # prepare only disk indexes, never the rich record asserted below.
    ensure_lazy_catalog_cache()
    ensure_detail_source_offsets()
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
    initial = view.service.page_checked("character:990000001", card, 0)
    expected_manual = not initial
    click = click_target(page, button)
    view.service.reload_progress()
    saved = view.service.page_checked("character:990000001", card, 0)
    session.check("manual-persist", "QTest Valider then reload canonical services", "Page 1 toggle persisted",
                  {"click": click, "initial": initial, "saved": saved},
                  click["accessible"] and saved == expected_manual, page)
    view.set_character_key("character:990000002")
    isolated = not view.service.page_checked("character:990000002", card, 0)
    view.set_character_key("character:990000001")
    view._show_index(0)
    settle()
    restored = view.findChild(QPushButton, "GuideManualPageCheck").isChecked()
    session.check("character-isolation", "Switch character, reload then return", "Other character clear; original state restored",
                  {"other_clear": isolated, "original_checked": restored,
                   "expected_original_checked": expected_manual},
                  isolated and restored == expected_manual, page)
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



def achievement_outcome(page, view, expected_id: int, expected_name: str) -> dict:
    """Observe the final *visible* result, not the selection signal alone."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QLabel, QFrame
    from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB

    body = view.detail_content.findChild(QFrame, "AchievementDetailBody")
    title = body.findChild(QLabel, "AchievementDetailTitle") if body else None
    stack = view.detail_stack
    scroll = view.detail_scroll
    viewport = scroll.viewport()
    title_hit = None
    if title is not None and title.isVisible():
        hit = page.childAt(title.mapTo(page, title.rect().center()))
        title_hit = bool(hit is title or (hit is not None and title.isAncestorOf(hit)))
    return {
        "active_tab": page.current_tab_label(),
        "expected_tab": ACHIEVEMENTS_TAB,
        "expected_id": int(expected_id),
        "current_achievement_id": view.current_achievement_id,
        "detail_open": view._detail_open,
        "detail_stack_active": stack.currentWidget() is scroll,
        "stack_visible": stack.isVisible(),
        "stack_width": stack.width(), "stack_height": stack.height(),
        "scroll_visible": scroll.isVisible(), "viewport_visible": viewport.isVisible(),
        "viewport_width": viewport.width(), "viewport_height": viewport.height(),
        "detail_body_count": len(view.detail_content.findChildren(QFrame, "AchievementDetailBody")),
        "body_visible": bool(body and body.isVisible()),
        "body_achievement_id": getattr(getattr(body, "achievement", None), "id", None),
        "title": title.text() if title else None,
        "expected_title": expected_name,
        "title_visible": bool(title and title.isVisible()),
        "title_hit": title_hit,
    }


def first_achievement_failure(observed: dict) -> str | None:
    """First failed transition in the real list -> selected detail pipeline."""
    checks = (
        (observed.get("active_tab") == observed.get("expected_tab"), "SUCCES_TAB"),
        (observed.get("current_achievement_id") == observed.get("expected_id"), "selected_achievement_id"),
        (observed.get("detail_open") is True, "detail_open"),
        (observed.get("detail_stack_active") is True, "detail_stack_active"),
        (observed.get("stack_visible") is True and observed.get("scroll_visible") is True
         and observed.get("viewport_visible") is True, "detail_visible"),
        (observed.get("stack_width", 0) >= 160 and observed.get("stack_height", 0) >= 100
         and observed.get("viewport_width", 0) >= 150, "detail_geometry"),
        (observed.get("detail_body_count") == 1 and observed.get("body_visible") is True
         and observed.get("body_achievement_id") == observed.get("expected_id"), "detail_body"),
        (observed.get("title") == observed.get("expected_title")
         and observed.get("title_visible") is True and observed.get("title_hit") is True,
         "detail_title"),
    )
    return next((reason for passed, reason in checks if not passed), None)



def achievement_layout_observations(page, view) -> dict:
    """Measure the rendered Success title and actually exposed controls.

    Only the visible portion of the detail viewport is actionable. Controls
    legitimately below the fold aren't failures until scrolled into view.
    """
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtWidgets import QAbstractButton, QLabel

    scroll = view.detail_scroll
    viewport = scroll.viewport()
    content = view.detail_content
    title = content.findChild(QLabel, "AchievementDetailTitle")
    if title is None:
        return {"status": "BLOCKED", "reason": "MISSING_ACHIEVEMENT_TITLE"}
    title_rect = title.contentsRect()
    available_width = max(1, title_rect.width())
    flags = Qt.TextWordWrap if title.wordWrap() else Qt.TextSingleLine
    required = title.fontMetrics().boundingRect(
        QRect(0, 0, available_width, 4096), flags, title.text()
    )
    required_height = required.height()
    clipped_title = bool(
        not title.text().strip() or available_width < 40
        or required_height > title_rect.height() + 5
        or (not title.wordWrap() and title.fontMetrics().horizontalAdvance(title.text())
            > available_width + 5)
    )
    viewport_top_left = viewport.mapTo(page, QPoint(0, 0))
    viewport_rect = QRect(viewport_top_left, viewport.size())

    # Scrolling containers are allowed to clip offscreen children. Use
    # visibleRegion(), never bare QWidget.isVisible(), to avoid spurious
    # inaccessible-button reports for legitimate below-fold objectives.
    controls = []
    for button in content.findChildren(QAbstractButton):
        if not button.isVisible() or not button.isEnabled():
            continue
        clipped = button.visibleRegion().boundingRect()
        if clipped.width() < 8 or clipped.height() < 8:
            continue
        top_left = button.mapTo(page, clipped.topLeft())
        region = QRect(top_left, clipped.size()).intersected(viewport_rect)
        if region.width() < 8 or region.height() < 8:
            continue
        local = button.mapFrom(page, region.center())
        hit = page.childAt(button.mapTo(page, local))
        reachable = bool(
            hit is button or (hit is not None and button.isAncestorOf(hit))
        )
        controls.append({
            "name": button.objectName() or type(button).__name__,
            "rect": [region.x(), region.y(), region.width(), region.height()],
            "reachable": reachable,
            "hit": hit.objectName() if hit else None,
            "source": type(button).__module__ + "." + type(button).__qualname__,
        })
    inaccessible = [c["name"] for c in controls if not c["reachable"]]
    overlaps = []
    for i, left in enumerate(controls):
        a = QRect(*left["rect"])
        for right in controls[i + 1:]:
            b = QRect(*right["rect"])
            intersection = a.intersected(b)
            if intersection.width() > 2 and intersection.height() > 2:
                overlaps.append({
                    "left": left["name"], "right": right["name"],
                    "intersection": [intersection.x(), intersection.y(),
                                     intersection.width(), intersection.height()],
                })
    horizontal_overflow = scroll.horizontalScrollBar().maximum() > 2
    return {
        "status": "OBSERVED", "title": title.text()[:160],
        "title_word_wrap": title.wordWrap(),
        "title_available_width": available_width,
        "title_available_height": title_rect.height(),
        "title_required_height": required_height,
        "title_clipped": clipped_title,
        "horizontal_overflow": horizontal_overflow,
        "horizontal_scroll_max": scroll.horizontalScrollBar().maximum(),
        "control_count_in_viewport": len(controls),
        "visible_controls": controls[:48],
        "inaccessible_controls": inaccessible,
        "overlaps": overlaps[:24],
        "viewport": [viewport_rect.x(), viewport_rect.y(),
                     viewport_rect.width(), viewport_rect.height()],
        "limits": "Title and visible detail controls; below-fold controls, rich HTML and full pixel contrast not certified.",
    }



def achievement_title_contrast(page, view) -> dict:
    """Measure actual visible title RGB pixels, not QPalette promises.

    Intentionally scoped to a single plain-text QLabel. Other text, disabled
    controls and rich HTML are NOT_COVERED until they have real pixel oracles.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QLabel
    from tools.atlas_doctor_lib.ui_contrast_oracle import inspect_label_pixels

    label = view.detail_content.findChild(QLabel, "AchievementDetailTitle")
    if label is None or not label.isVisible() or not label.text().strip():
        return {"status": "BLOCKED", "reason": "MISSING_VISIBLE_TITLE"}
    if label.textFormat() == Qt.RichText or "<" in label.text():
        return {"status": "BLOCKED", "reason": "RICH_TEXT_REQUIRES_SEPARATE_ORACLE"}
    top = label.mapTo(page, QPoint(0, 0))
    image = page.grab().toImage()
    if image.isNull() or page.width() <= 0 or page.height() <= 0:
        return {"status": "BLOCKED", "reason": "INVALID_REAL_SCREENSHOT"}
    scale_x = image.width() / page.width()
    scale_y = image.height() / page.height()
    # Never accidentally certify other widgets/borders behind this title.
    x0 = max(0, int((top.x() + 2) * scale_x))
    y0 = max(0, int((top.y() + 1) * scale_y))
    x1 = min(image.width(), int((top.x() + min(label.width() - 2, 500)) * scale_x))
    y1 = min(image.height(), int((top.y() + min(label.height() - 1, 100)) * scale_y))
    if x1 - x0 < 40 or y1 - y0 < 12:
        return {"status": "BLOCKED", "reason": "TITLE_CROP_TOO_SMALL",
                "crop": [x0, y0, x1, y1]}
    rgb = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            pixel = image.pixelColor(x, y)
            rgb.append((pixel.red(), pixel.green(), pixel.blue()))
    outcome = inspect_label_pixels(rgb, minimum_ratio=4.5)
    return {
        **outcome, "widget": "AchievementDetailTitle",
        "expected_visible_text": label.text()[:160],
        "crop": [x0, y0, x1 - x0, y1 - y0],
        "capture_pixel_size": [image.width(), image.height()],
        "coverage": "one visible plain-text Success title in actual Qt screenshot",
        "not_covered": ["body rich text", "other tabs", "below-fold text", "color vision accessibility"],
    }




def achievement_readable_text_observations(page, view, *, expected_description: str) -> dict:
    """Per-widget RGB legibility of *actual* screenshot text at the top of Success.

    A single title PASS is insufficient: the description, progress and the
    completion checkbox caption are independently required. Measure the text
    region, not the icon, progress bar or a neighboring bright border.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QCheckBox, QLabel, QStyle, QStyleOptionButton
    from tools.atlas_doctor_lib.ui_contrast_oracle import inspect_label_pixels

    image = page.grab().toImage()
    if image.isNull() or page.width() <= 0 or page.height() <= 0:
        return {"status": "BLOCKED", "reason": "SCREENSHOT_NOT_AVAILABLE"}
    content = view.detail_content
    title = content.findChild(QLabel, "AchievementDetailTitle")
    progress = content.findChild(QLabel, "AchievementProgressText")
    description = content.findChild(QLabel, "AchievementDescription")
    checkbox = content.findChild(QCheckBox, "AchievementDoneCheck")
    targets = [("title", title, True), ("progress", progress, True),
               ("completion_label", checkbox, True)]
    if expected_description:
        targets.insert(1, ("description", description, True))
    elif description is not None:
        # An unexpected stale description is a data mismatch, not proof.
        return {"status": "BLOCKED", "reason": "UNEXPECTED_DESCRIPTION_WIDGET"}

    viewport = view.detail_scroll.viewport()
    vtop = viewport.mapTo(page, QPoint())
    visible_vp = viewport.rect().translated(vtop)
    sx, sy = image.width() / page.width(), image.height() / page.height()
    results = []
    for role, widget, required in targets:
        if widget is None or not widget.isVisible() or not widget.text().strip():
            results.append({"role": role, "status": "BLOCKED", "reason": "MISSING_VISIBLE_TEXT"})
            continue
        if widget.textFormat() == Qt.RichText if isinstance(widget, QLabel) else False:
            results.append({"role": role, "status": "BLOCKED", "reason": "RICH_TEXT_UNSUPPORTED"})
            continue
        actual = widget.text()
        if role == "description" and actual != expected_description:
            results.append({"role": role, "status": "FAIL", "reason": "WRONG_DESCRIPTION"})
            continue
        if role == "progress" and not actual.startswith("Progression"):
            results.append({"role": role, "status": "FAIL", "reason": "WRONG_PROGRESS_TEXT"})
            continue
        if role == "completion_label" and actual != "Succès terminé":
            results.append({"role": role, "status": "FAIL", "reason": "WRONG_CHECKBOX_CAPTION"})
            continue
        if isinstance(widget, QCheckBox):
            option = QStyleOptionButton()
            option.initFrom(widget)
            option.text = actual
            region = widget.style().subElementRect(QStyle.SE_CheckBoxContents, option, widget)
        else:
            region = widget.contentsRect()
        point = widget.mapTo(page, region.topLeft())
        real_rect = region.translated(point - region.topLeft()).intersected(visible_vp)
        if real_rect.width() < 35 or real_rect.height() < 12:
            results.append({"role": role, "status": "BLOCKED", "reason": "TEXT_OUTSIDE_VIEWPORT"})
            continue
        # Crop only text advance rather than an entire right-hand pane;
        # otherwise very short, unreadable captions could go undetected.
        advance = widget.fontMetrics().horizontalAdvance(actual.splitlines()[0])
        if advance <= 0:
            results.append({"role": role, "status": "BLOCKED", "reason": "NO_TEXT_ADVANCE"})
            continue
        text_width = min(540, real_rect.width(), advance + 12)
        x0 = max(0, int(real_rect.left() * sx))
        y0 = max(0, int(real_rect.top() * sy))
        x1 = min(image.width(), int((real_rect.left() + text_width) * sx))
        y1 = min(image.height(), int((real_rect.top() + min(real_rect.height(), 100)) * sy))
        if x1 - x0 < 35 or y1 - y0 < 12 or (x1-x0)*(y1-y0) > 150000:
            results.append({"role": role, "status": "BLOCKED", "reason": "TEXT_CROP_INVALID"})
            continue
        rgb = [(image.pixelColor(x, y).red(),
                image.pixelColor(x, y).green(),
                image.pixelColor(x, y).blue())
               for y in range(y0, y1) for x in range(x0, x1)]
        checked = inspect_label_pixels(rgb, minimum_ratio=4.5)
        results.append({**checked, "role": role,
                        "widget": widget.objectName(),
                        "text": actual[:160],
                        "crop": [x0, y0, x1 - x0, y1 - y0]})
    statuses = {item["role"]: item["status"] for item in results}
    if len(results) != len(targets) or any(item["status"] == "BLOCKED" for item in results):
        status = "BLOCKED"
    elif any(item["status"] == "FAIL" for item in results):
        status = "FAIL"
    else:
        status = "PASS"
    return {
        "status": status,
        "reason": "MULTIPLE_REAL_TEXT_REGIONS_VERIFIED" if status == "PASS"
                  else "MISSING_UNREADABLE_OR_UNVERIFIABLE_TEXT",
        "expected_roles": [role for role, _, _ in targets],
        "per_widget": results, "statuses": statuses,
        "screenshot_size": [image.width(), image.height()],
        "not_covered": ["rich HTML", "below-fold text", "other modules", "icon contrast"],
    }



def first_achievement_layout_failure(observed: dict) -> str | None:
    """Distinguish an absent oracle from a genuine geometric pass."""
    if observed.get("status") != "OBSERVED":
        return observed.get("reason", "LAYOUT_ORACLE_UNAVAILABLE")
    for key, reason in (
        ("title_clipped", "TITLE_CLIPPED"),
        ("horizontal_overflow", "HORIZONTAL_OVERFLOW"),
        ("overlaps", "BUTTON_OVERLAP"),
        ("inaccessible_controls", "BUTTON_OCCLUDED"),
    ):
        if observed.get(key):
            return reason
    if observed.get("control_count_in_viewport", 0) < 1:
        return "NO_EXPOSED_DETAIL_CONTROLS"
    return None



def click_achievement_row(page, view, item) -> dict:
    """QTest click on the real QListWidget viewport, not a mocked itemClicked."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    listing = view.list_widget
    viewport = listing.viewport()
    listing.scrollToItem(item)
    settle()
    center = listing.visualItemRect(item).center()
    local_target = listing.itemAt(center)
    point = viewport.mapTo(page, center)
    hit = page.childAt(point)
    accessible = (
        view.isVisible() and listing.isEnabled() and viewport.isVisible()
        and local_target is item and viewport.rect().contains(center)
        and hit is not None and (hit is viewport or listing.isAncestorOf(hit))
    )
    result = {
        "accessible": bool(accessible), "target": listing.objectName(),
        "row": listing.row(item),
        "item_id": int(item.data(Qt.UserRole) or 0),
        "hit": hit.objectName() if hit is not None else None,
        "point": [center.x(), center.y()],
        "source_widget_path": "EncyclopediaPage/AchievementsView/QuestResultList/viewport",
    }
    if accessible:
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, center)
        settle()
    return result


def exercise_achievement_detail(session, page):
    """Cold-first Success tab then physical list click, real provider & PNG oracle."""
    from PySide6.QtCore import Qt
    from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB

    session.guide_id = "achievement-catalog"
    never_opened = page.get_achievements_view() is None
    tab = page.tab_labels().index(ACHIEVEMENTS_TAB)
    page.tabs.setCurrentIndex(tab)
    loaded = settle(
        lambda: bool(
            (view := page.get_achievements_view()) is not None
            and view._runtime_ready and view.list_widget.count() > 0
            and page.current_tab_label() == ACHIEVEMENTS_TAB
        ), timeout=10)
    view = page.get_achievements_view()
    if not loaded or view is None or view.list_widget.count() == 0:
        raise RuntimeError("Real Success tab did not materialize a clickable achievement")

    item = view.list_widget.item(0)
    achievement_id = int(item.data(Qt.UserRole) or 0)
    achievement = page.service.achievement_provider.get_by_id(achievement_id)
    if not achievement or not page.service.achievement_provider.is_retained(achievement_id):
        raise RuntimeError("First Success row lacks a real retained provider oracle")

    title = str(achievement.name)
    cold_state = {
        "view_absent_before_first_open": never_opened,
        "view_runtime_ready": view._runtime_ready,
        "public_catalogue_id": achievement_id,
        "public_catalogue_name": title,
        "row_count": view.list_widget.count(),
        "detail_already_open": view._detail_open,
    }
    click = click_achievement_row(page, view, item)
    settled = settle(
        lambda: first_achievement_failure(
            achievement_outcome(page, view, achievement_id, title)
        ) is None,
        timeout=5,
    )
    observed = achievement_outcome(page, view, achievement_id, title)
    failure = first_achievement_failure(observed)
    observed.update(click=click, settled=settled, first_failed_transition=failure)
    session.card_id = str(achievement_id)
    session.check(
        "first-open-lazy",
        "First Success tab open then QTest click a real first row",
        "Cold tab hydrates visible list and opens correct detail without a mock",
        {"cold": cold_state, "final": observed},
        bool(never_opened and loaded and cold_state["view_runtime_ready"]
             and not cold_state["detail_already_open"]
             and click["accessible"] and failure is None), page,
    )
    session.check(
        "click-opens-detail",
        "QTest mouse click on actual Success list item",
        {"id": achievement_id, "title": title, "visible_detail": True},
        observed, click["accessible"] and failure is None, page,
    )

    for width, height in ((1200, 800), (960, 640)):
        page.resize(width, height)
        view.detail_scroll.verticalScrollBar().setValue(0)
        settle()
        size_state = achievement_outcome(page, view, achievement_id, title)
        issue = first_achievement_failure(size_state)
        session.check(
            f"geometry-{width}",
            "Resize the real selected Success detail and hit-test the title",
            "Unclipped visible panel/title with matching ID, sufficient dimensions",
            {**size_state, "first_failed_transition": issue},
            issue is None, page,
        )
        layout_state = achievement_layout_observations(page, view)
        layout_issue = first_achievement_layout_failure(layout_state)
        session.check(
            f"layout-{width}",
            "Inspect real title wrapping, viewport and button hit-tests",
            "No clipped title, horizontal overflow, button collision or occlusion",
            {**layout_state, "first_failed_transition": layout_issue},
            layout_issue is None, page,
        )
        contrast = achievement_title_contrast(page, view)
        session.check(
            f"contrast-{width}",
            "Sample actual screenshot RGB inside the visible Success title",
            "At least 4.5:1 foreground/background contrast with visible ink",
            contrast, contrast["status"] == "PASS", page,
            status="BLOCKED" if contrast["status"] == "BLOCKED" else None,
        )
        readable = achievement_readable_text_observations(
            page, view, expected_description=str(achievement.description or ""),
        )
        session.check(
            f"text-regions-{width}",
            "Inspect RGB text regions for title, description, progress and checkbox",
            "Each required real visible text region is readable at >=4.5:1",
            readable, readable["status"] == "PASS", page,
            status="BLOCKED" if readable["status"] == "BLOCKED" else None,
        )



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
                        progress_source="temporary isolated canonical services",
                        validation_fonts=getattr(app, "_doctor_font_registration", {}))
        write_json(folder / "manifest.json", manifest)
        for name in request["scenarios"]:
            session.scenario = name
            if name == "guide-quests":
                if request["mode"] in {"all", "verify"}:
                    exercise_quest_links(session, page, owner)
                else:
                    session.snapshot(page)
            elif name == "achievement-detail":
                if request["mode"] in {"all", "verify"}:
                    exercise_achievement_detail(session, page)
                else:
                    session.snapshot(page)
            else:
                gid = "dofus_sylvestre" if name == "guides-lanyel" else "guide_complet"
                exercise_guide(session, page, owner, gid, request["repeats"], name == "validator-smoke")
        report["tests_executed"] = request["mode"] in {"all", "verify"}
        if report["tests_executed"]:
            session.scenario = "session"
            session.check("qt-exceptions", "Deliver all Qt callbacks", "No callback exception", qt_errors, not qt_errors, page)
            typography = glyph_legibility_probe(
                page,
                screenshots=[folder / name for name in session.evidence
                             if name.endswith(".png") and not name.endswith("-blocks.png")],
            )
            session.check("glyph-rendering", "Render live Qt font samples",
                          "ASCII and French glyphs distinct, without tofu squares",
                          typography, typography["status"] == "PASS", page)
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
