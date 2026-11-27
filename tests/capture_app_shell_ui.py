"""Capture real AtlasWindow module pages using the shared UI theme.

This fixture disables startup I/O and profile writes. A screenshot proves
that a genuine Qt page was painted; it is NOT a content or gameplay PASS.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import enumerate as active_threads
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# Name, displayed filename, widget type, data-readiness note.
SCENARIOS = (
    ("Home", "accueil", "HomePage", "no-game-preview"),
    ("Organizer", "organizer", "OrganizerPage", "no-native-game-sessions"),
    ("Settings", "parametres", "QWidget", "no-game-preview"),
    ("Dev UI", "bibliotheque-ui", "DevUiPage", "component-library"),
    ("Almanax", "almanax", "QWidget", "offline-calendar-no-offering-data"),
    ("Craft", "craft", "CraftPage", "deferred-local-data"),
    ("Equipement", "stuffs", "EquipmentPage", "no-user-equipment"),
    ("Scan Monde", "carte", "WorldScanPanel", "deferred-cartography"),
    ("Personnage", "personnage", "CharacterPage", "empty-personal-profile"),
    ("Quetes", "encyclopedie", "EncyclopediaPage", "empty-catalog-shell-only"),
    ("Guides", "guides", "EncyclopediaPage", "unavailable-guide-provider"),
    ("Succes", "succes", "EncyclopediaPage", "unavailable-achievement-provider"),
    ("Bestiaire", "bestiaire", "EncyclopediaPage", "unavailable-bestiary-placeholder"),
)


def _real_data_requested() -> bool:
    return os.environ.get("ATLAS_UI_REAL_DATA", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def capture(output: Path) -> dict[str, object]:
    from PySide6.QtCore import QDate
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QCalendarWidget, QLabel
    from app.ui.unity_skin import register_unity_fonts
    from app.services.almanax_service import AlmanaxDataService
    from app.quest_catalog import QuestCatalog
    from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider
    from app.modules.encyclopedia.providers.guide_provider import GuideProvider
    from app.modules.encyclopedia.providers.quest_provider import QuestProvider
    from app.modules.encyclopedia.constants import (
        ACHIEVEMENTS_TAB, DUNGEONS_TAB, GUIDES_TAB, QUESTS_TAB,
    )
    from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
    from app.constants import KEY_SESSION_ORDER
    import main as atlas_main

    app = QApplication.instance() or QApplication([])
    register_unity_fonts()
    output.mkdir(parents=True, exist_ok=True)
    real_data = _real_data_requested()
    result: dict[str, object] = {
        "candidate_sha": os.environ.get("CANDIDATE_SHA", "unknown"),
        "kind": "Windows Qt offscreen full AtlasWindow shell",
        "data_mode": "real-local-catalogs" if real_data else "empty-ci-fixture",
        "limitations": (
            "No game process, native focus, login or local Unity wallpaper. "
            + (
                "Quest, Guide and Success records come from the local repository "
                "catalogues; all player state is temporary."
                if real_data
                else "Deferred modules do not certify real data rendering."
            )
        ),
        "screenshots": [],
    }
    def unavailable_almanax_day(service, day_key: str, *, refresh: bool = False) -> bool:
        # Deliver a deterministic offline response through the real Qt signal.
        # No network access, cache hits or invented offering data in captures.
        service.dayUnavailable.emit(day_key, "offline capture fixture")
        return True

    with tempfile.TemporaryDirectory() as tmp:
        # Scan Monde initializes a writable SQLite/WAL database. Redirect it
        # before constructing AtlasWindow so a visual fixture never mutates
        # the repository's tracked data file or a user's launcher profile.
        from app.cartography.world_db import reset_database_for_tests

        reset_database_for_tests(Path(tmp) / "dofus_atlas_world.db")
        tmp_path = Path(tmp)
        profile_path = tmp_path / "profiles.json"
        client_index_path = tmp_path / "client_index.json"
        quest_progress_path = tmp_path / "quest_progress.json"
        achievement_progress_path = tmp_path / "achievement_progress.json"
        guide_progress_path = tmp_path / "guide_progress.json"
        owned_items_path = tmp_path / "craft_selection.json"
        profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["capture", "", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index_path.write_text(
            json.dumps({"clients": [{"index": 1, "name": "Capture", "handle": 1}]}),
            encoding="utf-8",
        )
        quest_progress_path.write_text(
            json.dumps({"version": 1, "characters": {}}), encoding="utf-8"
        )
        owned_items_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        with (
            patch.object(atlas_main, "PROFILE_FILE", profile_path),
            patch.object(AlmanaxDataService, "_load_cache", return_value=None),
            patch.object(AlmanaxDataService, "request_day", autospec=True, side_effect=unavailable_almanax_day),
            patch.object(atlas_main.AtlasWindow, "start_startup_preload_sequence", return_value=None),
            patch.object(atlas_main.AtlasWindow, "_start_post_preload_services", return_value=None),
            patch.object(atlas_main.AtlasWindow, "setup_tray", return_value=None),
            patch.object(atlas_main.AtlasWindow, "start_preload", return_value=None),
        ):
            window = atlas_main.AtlasWindow()
            encyclopedia = None
            try:
                if real_data:
                    quest_provider = QuestProvider()
                    catalog = quest_provider.get_catalog()
                    achievement_provider = AchievementProvider(
                        quest_provider=quest_provider
                    )
                    achievements = achievement_provider.load_all()
                    guide_provider = GuideProvider(
                        quest_provider=quest_provider,
                        achievement_provider=achievement_provider,
                    )
                    guides = guide_provider.load_all()
                    if not catalog.quests or not achievements or not guides:
                        raise RuntimeError(
                            "ATLAS_UI_REAL_DATA requires non-empty local Quest, "
                            "Achievement and Guide catalogues"
                        )
                    result["catalog_counts"] = {
                        "quests": len(catalog.quests),
                        "achievements": len(achievements),
                        "guides": len(guides),
                    }
                else:
                    quest_provider = QuestProvider(catalog=QuestCatalog([]))
                    achievement_provider = AchievementProvider(
                        data_dir=tmp_path / "empty-achievements",
                        quest_provider=quest_provider,
                    )
                    achievement_provider._loaded = True
                    guide_provider = GuideProvider(
                        guides_dir=tmp_path / "empty-guides",
                        quest_provider=quest_provider,
                        achievement_provider=achievement_provider,
                    )
                    guide_provider._loaded = True

                encyclopedia = EncyclopediaPage(
                    window.set_status,
                    quest_provider=quest_provider,
                    achievement_provider=achievement_provider,
                    guide_provider=guide_provider,
                    progress_path=quest_progress_path,
                    achievement_progress_path=achievement_progress_path,
                    guide_progress_path=guide_progress_path,
                    profile_path=profile_path,
                    client_index_path=client_index_path,
                    owned_items_path=owned_items_path,
                    initial_tab=QUESTS_TAB,
                )
                # Keep the real AtlasWindow lazy-page replacement path while
                # isolating every persistence path from the user's profile.
                window.page_factories["Quetes"] = lambda: encyclopedia
                window.resize(1380, 900)
                window.show()
                for name, slug, expected, readiness in SCENARIOS:
                    if real_data and name in {"Quetes", "Guides", "Succes"}:
                        readiness = "real-local-catalogue-temporary-player-state"
                    record: dict[str, object] = {
                        "module": name, "readiness": readiness, "status": "NOT_RUN"
                    }
                    try:
                        if name == "Personnage":
                            # Real character dressing, isolated from both user
                            # profiles and live network capture during CI.
                            character_type = atlas_main._resolve_character_page()
                            character = character_type(
                                profile_path=Path(tmp) / "character_profiles.json",
                                client_index_path=Path(tmp) / "client_index.json",
                                binding_path=Path(tmp) / "bindings.json",
                            )
                            character.refresh_from_sources("")
                            window.register_page("Personnage", character)
                            window.page_nav_group["Personnage"] = ""
                            record["fixture"] = "temporary empty player profile"
                        if name == "Quetes":
                            window.pending_encyclopedia_tab = QUESTS_TAB
                            record["fixture"] = (
                                "real local Quest catalogue; temporary player state"
                                if real_data
                                else "empty QuestCatalog; 0 quest records"
                            )
                        if name in {"Guides", "Succes", "Bestiaire"}:
                            page = window.page_widgets.get("Quetes")
                            if page is None:
                                raise RuntimeError(f"{name} needs the Encyclopedia shell")
                            target_tab = {
                                "Guides": GUIDES_TAB,
                                "Succes": ACHIEVEMENTS_TAB,
                                "Bestiaire": DUNGEONS_TAB,
                            }[name]
                            window.open_encyclopedia_tab(target_tab)
                            window.finish_pending_encyclopedia_tab()
                            record["fixture"] = (
                                f"real {target_tab} tab with unavailable provider; no fake records"
                            )
                        else:
                            if name in window.page_factories:
                                window.ensure_page_loaded(name)
                            page = window.page_widgets.get(name)
                        if page is None:
                            raise RuntimeError("module missing from AtlasWindow")
                        if expected != "QWidget" and type(page).__name__ != expected:
                            raise RuntimeError(
                                f"wrong widget: {type(page).__name__} instead of {expected}"
                            )
                        if name != "Bestiaire":
                            window.switch_to_page(name)
                        for _ in range(3):
                            app.processEvents()
                        if name == "Almanax":
                            # Real calendar, real date selection, no invented
                            # offerings: the source is explicitly unavailable.
                            calendar = page.findChild(
                                QCalendarWidget, "AlmanaxCalendar"
                            )
                            label = page.findChild(QLabel, "AlmanaxSelectedDate")
                            detail = page.findChild(QLabel, "AlmanaxDayDetails")
                            badge = page.findChild(QLabel, "StatusBadge")
                            icon = page.findChild(QLabel, "AlmanaxOfferingIcon")
                            breadcrumb = page.findChild(QLabel, "GuideBreadcrumbCurrent")
                            if any(widget is None for widget in (calendar, label, detail, badge, icon, breadcrumb)):
                                raise RuntimeError("Almanax calendar/breadcrumb missing")
                            future = QDate.currentDate().addDays(40)
                            calendar.setSelectedDate(future)
                            app.processEvents()
                            if calendar.selectedDate() != future:
                                raise RuntimeError("Almanax future-day selection failed")
                            if label.text() != future.toString("dddd d MMMM yyyy"):
                                raise RuntimeError("Almanax selected date is stale")
                            if (
                                badge.text() != "Données indisponibles"
                                or "Aucune offrande ni bonus sourcé" not in detail.text()
                                or not icon.isHidden()
                            ):
                                raise RuntimeError("Almanax claims unverified offering data")
                            record["fixture"] = "offline calendar, future selected, 0 game records"
                        if name == "Quetes":
                            catalog = page.quest_provider.get_catalog()
                            if page.current_tab_label() != QUESTS_TAB:
                                raise RuntimeError("Quests shell opened in wrong tab")
                            if real_data:
                                quest_id = 1653 if 1653 in catalog.by_id else catalog.quests[0].id
                                # A pending index worker may replace the first
                                # lightweight Quest page at the next event turn.
                                # Select on the final live page, never retain a
                                # stale Qt wrapper from before that handoff.
                                quest_page = page.quest_page
                                quest_page.select_quest(quest_id, persist=False)
                                for _attempt in range(100):
                                    app.processEvents()
                                    if page.quest_page is not quest_page:
                                        quest_page = page.quest_page
                                        quest_page.select_quest(quest_id, persist=False)
                                    detail = quest_page.quest_detail_view
                                    if (
                                        quest_page.selected_quest_id == quest_id
                                        and detail is not None
                                        and detail.current_quest_id == quest_id
                                        and not detail.isHidden()
                                    ):
                                        break
                                    QTest.qWait(20)
                                else:
                                    raise RuntimeError("real Quest selection timed out")
                                if (
                                    page.quest_page.quest_detail_view is None
                                    or page.quest_page.quest_detail_view.isHidden()
                                    or page.quest_page.quest_detail_view.current_quest_id
                                    != quest_id
                                ):
                                    detail = page.quest_page.quest_detail_view
                                    raise RuntimeError(
                                        "real Quest detail stayed hidden or stale: "
                                        f"exists={detail is not None}, "
                                        f"hidden={detail.isHidden() if detail else None}, "
                                        f"current={detail.current_quest_id if detail else None}"
                                    )
                                if page.quest_page.body_splitter.count() != 2:
                                    raise RuntimeError("Quest columns are incomplete")
                                from app.ui.components import AtlasGuideReadingHeader
                                detail = page.quest_page.quest_detail_view
                                if not isinstance(detail.header, AtlasGuideReadingHeader):
                                    raise RuntimeError("Quest header does not use the shared reader")
                                if detail.splitter.count() != 1:
                                    raise RuntimeError("Quest detail still contains a redundant third column")
                                if (detail.title_label.text() != catalog.by_id[quest_id].name
                                        or detail.title_label.toolTip() != detail.title_label.text()
                                        or detail.header.global_progress_bar.isVisible()
                                        or detail.header.guide_icon_label.isVisible()):
                                    raise RuntimeError("Quest header contains stale or unrelated data")
                                record.update(
                                    fixture=f"real local Quest catalogue; selected {quest_id}",
                                    record_count=len(catalog.quests),
                                    selected_id=quest_id,
                                    columns=page.quest_page.body_splitter.count(),
                                )
                            elif catalog.quests or catalog.by_id:
                                raise RuntimeError("Fixture must never show fake quests")
                        if name == "Guides" and real_data:
                            guide_catalog = page.ensure_guides_view()
                            if not guide_catalog._runtime_ready:
                                guide_catalog.hydrate_runtime(graph=page._quest_graph)
                            page._guide_runtime_ready = bool(guide_catalog._runtime_ready)
                            page._related_ready = page._guide_runtime_ready
                            if page._guide_runtime_ready:
                                page._related_preload_gate.mark_ready()
                            view = page.ensure_full_guides_view()
                            guide_id = (
                                "dofus_turquoise"
                                if guide_provider.get_by_id("dofus_turquoise") is not None
                                else guides[0].id
                            )
                            if not view.select_guide(guide_id):
                                raise RuntimeError("real Guide selection failed")
                            app.processEvents()
                            if view.splitter.count() != 3:
                                raise RuntimeError("Guide columns are incomplete")
                            record.update(
                                fixture=f"real local Guide catalogue; selected {guide_id}",
                                record_count=len(guides), selected_id=guide_id,
                                columns=view.splitter.count(),
                            )
                        if name == "Succes" and real_data:
                            view = page.ensure_achievements_view()
                            if not view._runtime_ready:
                                view.hydrate_runtime(quest_graph=page._quest_graph)
                            retained = achievement_provider.load_retained()
                            achievement_id = (
                                816
                                if achievement_provider.get_by_id(816) is not None
                                and achievement_provider.is_retained(816)
                                else retained[0].id
                            )
                            if not view.select_achievement(achievement_id):
                                raise RuntimeError("real Success selection failed")
                            app.processEvents()
                            if view.splitter.count() != 3:
                                raise RuntimeError("Success columns are incomplete")
                            record.update(
                                fixture=(
                                    "real local Achievement catalogue; "
                                    f"selected {achievement_id}"
                                ),
                                record_count=len(achievements),
                                selected_id=achievement_id,
                                columns=view.splitter.count(),
                            )
                        if name in {"Guides", "Succes", "Bestiaire"}:
                            expected_tab = {
                                "Guides": GUIDES_TAB,
                                "Succes": ACHIEVEMENTS_TAB,
                                "Bestiaire": DUNGEONS_TAB,
                            }[name]
                            # The shell deliberately defers a heavy tab while
                            # its runtime warms. For a deterministic capture,
                            # finish that exact real-tab transition now.
                            if page.current_tab_label() != expected_tab:
                                target_index = page.tab_labels().index(expected_tab)
                                page.tabs.setCurrentIndex(target_index)
                                page.on_tab_changed(target_index)
                                app.processEvents()
                                final_index = page.tab_labels().index(expected_tab)
                                page.tabs.setCurrentIndex(final_index)
                            allowed_tabs = (
                                {GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB}
                                if name != "Bestiaire"
                                else {
                                    DUNGEONS_TAB, "MONSTRES", "ARCHIMONSTRES",
                                    "AVIS DE RECHERCHE",
                                }
                            )
                            for index, tab_name in enumerate(page.tab_labels()):
                                page.tabs.tabBar().setTabVisible(
                                    index, tab_name in allowed_tabs
                                )
                            visible = {
                                page.tabs.tabText(index)
                                for index in range(page.tabs.count())
                                if page.tabs.tabBar().isTabVisible(index)
                            }
                            if page.current_tab_label() != expected_tab:
                                raise RuntimeError(f"{name} shell opened in wrong tab")
                            if name == "Bestiaire" and (
                                GUIDES_TAB in visible
                                or QUESTS_TAB in visible
                                or ACHIEVEMENTS_TAB in visible
                            ):
                                raise RuntimeError(
                                    "Bestiary leaked Guide, Quests or Success tabs: "
                                    + repr(sorted(visible))
                                )
                        if window.stack.currentWidget() is not page:
                            raise RuntimeError("screenshot not showing requested module")
                        if not app.styleSheet() or page.styleSheet():
                            raise RuntimeError("page overrides the shared Unity stylesheet")
                        path = output / f"{slug}-atlas-window.png"
                        shot = window.grab()
                        if shot.isNull() or not shot.save(str(path), "PNG"):
                            raise RuntimeError("Qt screenshot was not saved")
                        if path.stat().st_size < 2000:
                            raise RuntimeError("Qt screenshot unexpectedly small")
                        record.update(
                            status="CAPTURED", image=path.name,
                            widget=type(page).__name__,
                            size=[shot.width(), shot.height()],
                        )
                        if name in {"Guides", "Succes", "Bestiaire"}:
                            # Return through the *real* shell to make sure
                            # neither navigation direction leaks the other tab group.
                            window.open_encyclopedia_tab(QUESTS_TAB)
                            window.finish_pending_encyclopedia_tab()
                            app.processEvents()
                            quest_index = page.tab_labels().index(QUESTS_TAB)
                            page.tabs.setCurrentIndex(quest_index)
                            page.on_tab_changed(quest_index)
                            for index, tab_name in enumerate(page.tab_labels()):
                                page.tabs.tabBar().setTabVisible(
                                    index,
                                    tab_name
                                    in {GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB},
                                )
                            visible = {
                                page.tabs.tabText(index)
                                for index in range(page.tabs.count())
                                if page.tabs.tabBar().isTabVisible(index)
                            }
                            if (
                                page.current_tab_label() != QUESTS_TAB
                                or DUNGEONS_TAB in visible
                                or GUIDES_TAB not in visible
                                or ACHIEVEMENTS_TAB not in visible
                            ):
                                raise RuntimeError(
                                    "Return from Bestiary leaked or lost Encyclopedia tabs: "
                                    + repr(sorted(visible))
                                )
                    except Exception as error:
                        # Do not turn an unrendered page into a false PASS.
                        record.update(status="ERROR", error=f"{type(error).__name__}: {error}")
                    result["screenshots"].append(record)
                    print("ATLAS_MODULE_CAPTURE=" + json.dumps(record, ensure_ascii=False))
            finally:
                if encyclopedia is not None:
                    # Closing the parent shell does not deliver closeEvent to
                    # child pages. Stop their timers and join the Guide/Quest
                    # workers before TemporaryDirectory removes the SQLite DB.
                    encyclopedia.close()
                    app.processEvents()
                window.quit_requested = True
                window.close()
                app.processEvents()
                # The offscreen Scan Monde page starts a bounded background
                # SQLite read. Closing Qt widgets does not join its Python
                # thread; on Windows TemporaryDirectory otherwise races the
                # still-open database handle and fails with WinError 32.
                for worker in active_threads():
                    if worker.name != "DofusAtlasCartographyLoad":
                        continue
                    worker.join(timeout=10)
                    if worker.is_alive():
                        raise RuntimeError(
                            "Cartography capture worker did not stop before DB cleanup"
                        )
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    required = {entry[0] for entry in SCENARIOS}
    failed = [
        entry["module"] for entry in result["screenshots"]
        if entry["module"] in required and entry["status"] != "CAPTURED"
    ]
    if failed:
        raise RuntimeError("Real shell captures failed: " + ", ".join(failed))
    return result


if __name__ == "__main__":
    capture(Path(os.environ.get("ATLAS_UI_SHELL_DIR", "artifacts/app-shell")))
