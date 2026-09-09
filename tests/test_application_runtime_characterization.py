from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QStackedWidget, QWidget

import main as app_main
from app.modules.encyclopedia import views
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB


_BESTIARY_TABS = ("DONJONS", "MONSTRES", "ARCHIMONSTRES", "AVIS DE RECHERCHE")
_ALL_NAVIGATION_TABS = (GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB, *_BESTIARY_TABS, "AUTRE")


class _NavigationTabBar:
    def __init__(self) -> None:
        self.visible: dict[int, bool] = {}

    def setTabVisible(self, index: int, visible: bool) -> None:
        self.visible[int(index)] = bool(visible)


class _NavigationTabs:
    def __init__(self, page: "_NavigationPage") -> None:
        self.page = page
        self.index = 1
        self.blocked = False
        self.bar = _NavigationTabBar()

    def blockSignals(self, blocked: bool) -> bool:
        previous = self.blocked
        self.blocked = bool(blocked)
        return previous

    def setCurrentIndex(self, index: int) -> None:
        self.index = int(index)
        if not self.blocked:
            self.page.on_tab_changed(self.index)

    def currentIndex(self) -> int:
        return self.index

    def tabBar(self) -> _NavigationTabBar:
        return self.bar


class _NavigationPage:
    def __init__(self, *, move_on_activation: str = "") -> None:
        self.labels = list(_ALL_NAVIGATION_TABS)
        self.tabs = _NavigationTabs(self)
        self.move_on_activation = move_on_activation
        self.activations: list[str] = []
        self.character_keys: list[str] = []

    def set_character_key(self, character_key: str) -> None:
        self.character_keys.append(character_key)

    def tab_labels(self) -> list[str]:
        return list(self.labels)

    def on_tab_changed(self, index: int) -> None:
        label = self.labels[index]
        self.activations.append(label)
        if label == self.move_on_activation:
            self.move_on_activation = ""
            self.labels.remove(label)
            self.labels.append(label)
            self.tabs.index = self.labels.index(QUESTS_TAB)


class _NavigationShell:
    def __init__(self, page: _NavigationPage, target: str) -> None:
        self.pending_encyclopedia_tab = target
        self.page_widgets = {"Quetes": page}
        self.current_character_key = "character:42"
        self.page_nav_group = {"Quetes": "Encyclopédie"}
        self.nav_refreshes: list[str] = []

    def refresh_nav_selection(self, group: str) -> None:
        self.nav_refreshes.append(group)


class ApplicationRuntimeCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_canonical_bootstrap_preserves_deferred_encyclopedia_targets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from PySide6.QtWidgets import QApplication
import main as app_main
from app.modules.encyclopedia import views
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB

payload = {"application_before_entry": QApplication.instance() is None}

class TabBar:
    def __init__(self):
        self.visible = {}
    def setTabVisible(self, index, visible):
        self.visible[index] = bool(visible)

class Tabs:
    def __init__(self):
        self.index = 0
        self.blocked = False
        self.bar = TabBar()
    def blockSignals(self, blocked):
        previous = self.blocked
        self.blocked = bool(blocked)
        return previous
    def setCurrentIndex(self, index):
        self.index = int(index)
    def currentIndex(self):
        return self.index
    def tabBar(self):
        return self.bar

class Page:
    labels = [GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB]
    def __init__(self):
        self.tabs = Tabs()
        self.character_keys = []
        self.activations = []
    def set_character_key(self, key):
        self.character_keys.append(key)
    def tab_labels(self):
        return list(self.labels)
    def on_tab_changed(self, index):
        self.activations.append(self.labels[index])
        self.tabs.index = self.labels.index(QUESTS_TAB)

views._REAL_ENCYCLOPEDIA_PAGE = Page

class Shell:
    def __init__(self, target):
        self.pending_encyclopedia_tab = target
        self.page_widgets = {"Quetes": object()}
        self.current_character_key = "character:1"
        self.page_nav_group = {"Quetes": "Encyclopédie"}
        self.nav_refreshes = []
    def refresh_nav_selection(self, group):
        self.nav_refreshes.append(group)

def application_entry():
    payload["application_in_entry"] = QApplication.instance() is None
    results = {}
    for target in (GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB):
        shell = Shell(target)
        app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)
        retained_while_cold = shell.pending_encyclopedia_tab == target
        page = Page()
        shell.page_widgets["Quetes"] = page
        app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)
        app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)
        results[target] = {
            "retained_while_cold": retained_while_cold,
            "pending": shell.pending_encyclopedia_tab,
            "final": page.labels[page.tabs.currentIndex()],
            "activations": page.activations,
            "character_keys": page.character_keys,
            "nav_refreshes": shell.nav_refreshes,
        }
    payload["targets"] = results

    import os
    import tempfile
    from pathlib import Path
    import app.constants as constants
    import app.modules.encyclopedia.services as services
    from app.modules.encyclopedia.services import GuideProgressService

    class Value:
        def __init__(self, value=0):
            self.value_ = value
        def setValue(self, value):
            self.value_ = int(value)
        def value(self):
            return self.value_

    class Text:
        def __init__(self):
            self.value_ = ""
        def setText(self, value):
            self.value_ = str(value)
        def text(self):
            return self.value_

    class Button(Text):
        def setEnabled(self, enabled):
            self.enabled = bool(enabled)

    heavy_operations = {
        "rich_refresh": 0,
        "achievement_load_all": 0,
        "guide_load_all": 0,
        "encyclopedia_create": 0,
    }

    class Home:
        def __init__(self, character_key):
            self.character_key = character_key
            self.catalog = None
            self.guide_provider = None
            self.progress_bar = Value()
            self.progress_percent = Text()
            self.character_progress = Text()
            self.chapter_value = Text()
            self.step_value = Text()
            self.zone_value = Text()
            self.continue_button = Button()
            self.current_guide_id = ""
            self.current_quest_id = None
        def _reset_tracking(self):
            return None
        def _refresh_rich_progress(self):
            heavy_operations["rich_refresh"] += 1

    def counted_load_all(name):
        def load_all(*_args, **_kwargs):
            heavy_operations[name] += 1
            return []
        return load_all

    refresh = app_main.HomePage.refresh_progress
    refresh_globals = refresh.__globals__
    refresh_globals["AchievementProvider"].load_all = counted_load_all("achievement_load_all")
    refresh_globals["GuideProvider"].load_all = counted_load_all("guide_load_all")
    app_main.AtlasWindow.create_encyclopedia_page = counted_load_all("encyclopedia_create")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        quest_path = root / "quest.json"
        achievement_path = root / "achievement.json"
        guide_path = root / "guide.json"
        cache_path = root / "home-cache.json"
        manifest_path = root / "manifest.json"
        quest_path.write_text("{}", encoding="utf-8")
        achievement_path.write_text("{}", encoding="utf-8")
        manifest_path.write_text(
            json.dumps({"canonical": {"chapters": [{"stage_count": 4}]}}),
            encoding="utf-8",
        )
        progress_guide_id = refresh_globals.get("_GUIDE_PROGRESS_ID", "guide_complet")
        GuideProgressService(guide_path).set_manual_step_completed(
            "character:1", progress_guide_id, "page:first", True
        )
        refresh_globals["_HOME_PROGRESS_CACHE_PATH"] = cache_path
        refresh_globals["_MANUAL_ROUTE_MANIFEST_PATH"] = manifest_path
        refresh_globals["GUIDE_PROGRESS_FILE"] = guide_path
        constants.QUEST_PROGRESS_FILE = quest_path
        services.ACHIEVEMENT_PROGRESS_FILE = achievement_path

        first = Home("character:1")
        refresh(first)

        signature = [
            [path.stat().st_mtime_ns, path.stat().st_size]
            for path in (quest_path, achievement_path, guide_path)
        ]
        cache_path.write_text(
            json.dumps({
                "version": 1,
                "characters": {
                    "character:2": {
                        "progress_signature": signature,
                        "percent": 75,
                        "chapter": "Bonta",
                        "step": "Étape sauvegardée",
                        "zone": "[1,2]",
                        "guide_id": "guide_complet",
                    },
                    "character:3": {
                        "progress_signature": signature,
                        "percent": 175,
                    }
                },
            }),
            encoding="utf-8",
        )
        second = Home("character:2")
        refresh(second)

        bounded = Home("character:3")
        refresh(bounded)

        quest_path.write_text('{"generation": 2}', encoding="utf-8")
        after_stale_cache = Home("character:2")
        refresh(after_stale_cache)

        cache_path.write_text("{broken", encoding="utf-8")
        after_corruption = Home("character:2")
        refresh(after_corruption)

        payload["home"] = {
            "persisted_percent": first.progress_bar.value(),
            "cached_percent": second.progress_bar.value(),
            "cached_chapter": second.chapter_value.text(),
            "bounded_percent": bounded.progress_bar.value(),
            "stale_percent": after_stale_cache.progress_bar.value(),
            "corrupt_percent": after_corruption.progress_bar.value(),
            "guide_progress_still_present": GuideProgressService(guide_path).is_manual_step_completed(
                "character:1", progress_guide_id, "page:first"
            ),
            "heavy_operations": heavy_operations,
            "manual_runtime_loaded": (
                "app.modules.encyclopedia.services.guide_ultime_manual_runtime_service"
                in sys.modules
            ),
        }
    return 23

app_main.main = application_entry
import launch
payload["exit_code"] = launch.main()
payload["home_patch_loaded"] = "app.pages.home_progress_runtime_patch" in sys.modules
payload["navigation_patch_loaded"] = (
    "app.pages.encyclopedia_navigation_runtime_patch" in sys.modules
)
print(json.dumps(payload, ensure_ascii=False))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"},
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertTrue(payload["application_before_entry"])
        self.assertTrue(payload["application_in_entry"])
        self.assertEqual(payload["exit_code"], 23)
        for target, state in payload["targets"].items():
            self.assertTrue(state["retained_while_cold"], target)
            self.assertEqual(state["pending"], "", target)
            self.assertEqual(state["final"], target)
            self.assertEqual(state["activations"], [target])
            self.assertEqual(state["character_keys"], ["character:1"])
            self.assertEqual(state["nav_refreshes"], ["Encyclopédie"])
        self.assertEqual(payload["home"]["persisted_percent"], 25)
        self.assertEqual(payload["home"]["cached_percent"], 75)
        self.assertEqual(payload["home"]["cached_chapter"], "Bonta")
        self.assertEqual(payload["home"]["bounded_percent"], 100)
        self.assertEqual(payload["home"]["stale_percent"], 0)
        self.assertEqual(payload["home"]["corrupt_percent"], 0)
        self.assertTrue(payload["home"]["guide_progress_still_present"])
        self.assertEqual(
            payload["home"]["heavy_operations"],
            {
                "rich_refresh": 0,
                "achievement_load_all": 0,
                "guide_load_all": 0,
                "encyclopedia_create": 0,
            },
        )
        self.assertFalse(payload["home"]["manual_runtime_loaded"])
        self.assertFalse(payload["home_patch_loaded"])
        self.assertFalse(payload["navigation_patch_loaded"])

    def test_page_factory_constructs_once_and_reuses_the_page(self) -> None:
        placeholder = QWidget()
        created: list[QWidget] = []

        def factory() -> QWidget:
            page = QWidget()
            created.append(page)
            return page

        class Shell:
            def __init__(self) -> None:
                self.stack = QStackedWidget()
                self.stack.addWidget(placeholder)
                self.page_widgets = {"Quetes": placeholder}
                self.page_indexes = {"Quetes": 0}
                self.pages = [("Quetes", placeholder)]
                self.page_factories = {"Quetes": factory}

        shell = Shell()
        first = app_main.AtlasWindow.ensure_page_loaded(shell, "Quetes")
        second = app_main.AtlasWindow.ensure_page_loaded(shell, "Quetes")

        self.assertIs(first, second)
        self.assertEqual(len(created), 1)
        self.assertIs(shell.page_widgets["Quetes"], first)
        first.deleteLater()
        placeholder.deleteLater()
        shell.stack.deleteLater()
        self.app.processEvents()

    def test_canonical_navigation_is_atomic_across_tab_groups(self) -> None:
        previous_real_page = views._REAL_ENCYCLOPEDIA_PAGE
        page = _NavigationPage()
        shell = _NavigationShell(page, GUIDES_TAB)
        guide_tabs = {GUIDES_TAB, QUESTS_TAB, ACHIEVEMENTS_TAB}
        bestiary_tabs = set(_BESTIARY_TABS)
        targets = (
            GUIDES_TAB,
            ACHIEVEMENTS_TAB,
            QUESTS_TAB,
            *_BESTIARY_TABS,
            "AUTRE",
            GUIDES_TAB,
        )
        try:
            views._REAL_ENCYCLOPEDIA_PAGE = _NavigationPage
            for target in targets:
                shell.pending_encyclopedia_tab = target
                before = len(page.activations)

                app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)

                self.assertEqual(page.activations[before:], [target], target)
                self.assertEqual(page.labels[page.tabs.currentIndex()], target)
                self.assertEqual(shell.pending_encyclopedia_tab, "")
                expected_visible = {
                    index: (
                        label in guide_tabs
                        if target in guide_tabs
                        else label in bestiary_tabs
                        if target in bestiary_tabs
                        else True
                    )
                    for index, label in enumerate(page.labels)
                }
                self.assertEqual(page.tabs.bar.visible, expected_visible, target)

            self.assertEqual(page.character_keys, ["character:42"] * len(targets))
            self.assertEqual(shell.nav_refreshes, ["Encyclopédie"] * len(targets))
            self.assertFalse(page.tabs.blocked)
        finally:
            views._REAL_ENCYCLOPEDIA_PAGE = previous_real_page

    def test_lazy_replacement_keeps_target_without_second_activation(self) -> None:
        previous_real_page = views._REAL_ENCYCLOPEDIA_PAGE
        page = _NavigationPage(move_on_activation=GUIDES_TAB)
        page.tabs.blocked = True
        shell = _NavigationShell(page, GUIDES_TAB)
        try:
            views._REAL_ENCYCLOPEDIA_PAGE = _NavigationPage

            app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)

            self.assertEqual(page.activations, [GUIDES_TAB])
            self.assertEqual(page.labels[page.tabs.currentIndex()], GUIDES_TAB)
            self.assertEqual(shell.pending_encyclopedia_tab, "")
            self.assertTrue(page.tabs.blocked)
        finally:
            views._REAL_ENCYCLOPEDIA_PAGE = previous_real_page

    def test_unknown_encyclopedia_label_fails_closed(self) -> None:
        previous_real_page = views._REAL_ENCYCLOPEDIA_PAGE
        page = _NavigationPage()
        shell = _NavigationShell(page, "INCONNU")
        try:
            views._REAL_ENCYCLOPEDIA_PAGE = _NavigationPage

            app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)

            self.assertEqual(shell.pending_encyclopedia_tab, "")
            self.assertEqual(page.character_keys, ["character:42"])
            self.assertEqual(page.activations, [])
            self.assertEqual(page.tabs.bar.visible, {})
            self.assertEqual(shell.nav_refreshes, [])
        finally:
            views._REAL_ENCYCLOPEDIA_PAGE = previous_real_page

    def test_guide_target_survives_tab_materialization(self) -> None:
        previous_real_page = views._REAL_ENCYCLOPEDIA_PAGE
        page = _NavigationPage(move_on_activation=GUIDES_TAB)
        shell = _NavigationShell(page, GUIDES_TAB)
        shell.pending_guide_target = ("guide-ultime", 987)
        try:
            views._REAL_ENCYCLOPEDIA_PAGE = _NavigationPage

            app_main.AtlasWindow.finish_pending_encyclopedia_tab(shell)

            self.assertEqual(shell.pending_guide_target, ("guide-ultime", 987))
            self.assertEqual(page.activations, [GUIDES_TAB])
            self.assertEqual(page.labels[page.tabs.currentIndex()], GUIDES_TAB)
        finally:
            views._REAL_ENCYCLOPEDIA_PAGE = previous_real_page

    def test_character_changes_reach_created_pages_without_creating_cold_pages(self) -> None:
        previous_real_page = views._REAL_ENCYCLOPEDIA_PAGE

        class EncyclopediaPageStub:
            def __init__(self) -> None:
                self.refresh_calls = 0
                self.character_keys: list[str] = []

            def refresh_characters(self) -> None:
                self.refresh_calls += 1

            def set_character_key(self, key: str) -> None:
                self.character_keys.append(key)

        class HomeStub:
            def __init__(self) -> None:
                self.characters: list[tuple[str, str, str]] = []

            def set_character(self, key: str, label: str, icon_path: str) -> None:
                self.characters.append((key, label, icon_path))

        class Shell:
            def __init__(self) -> None:
                self.current_character_key = "character:1"
                self.current_character_label = "Alpha"
                self.character_combo = QComboBox()
                self.character_combo.addItem("Beta", SimpleNamespace(key="character:2", label="Beta"))
                self.home_page = HomeStub()
                self.page_widgets: dict[str, object] = {}
                self.persist_calls = 0

            def character_icon_path(self, _label: str) -> str:
                return ""

            def persist_selected_character(self) -> None:
                self.persist_calls += 1

            def sync_selected_character_to_pages(self) -> None:
                app_main.AtlasWindow.sync_selected_character_to_pages(self)

        try:
            views._REAL_ENCYCLOPEDIA_PAGE = EncyclopediaPageStub
            shell = Shell()

            shell.sync_selected_character_to_pages()
            self.assertEqual(shell.page_widgets, {})

            page = EncyclopediaPageStub()
            shell.page_widgets["Quetes"] = page
            app_main.AtlasWindow.on_global_character_changed(shell)

            self.assertEqual(shell.current_character_key, "character:2")
            self.assertEqual(shell.persist_calls, 1)
            self.assertEqual(page.refresh_calls, 1)
            self.assertEqual(page.character_keys, ["character:2"])
            self.assertEqual(shell.home_page.characters, [("character:2", "Beta", "")])

            app_main.AtlasWindow.on_global_character_changed(shell)
            self.assertEqual(shell.persist_calls, 1)
            self.assertEqual(page.refresh_calls, 1)
            self.assertEqual(page.character_keys, ["character:2"])

            shell.current_character_key = ""
            shell.sync_selected_character_to_pages()
            self.assertEqual(page.refresh_calls, 2)
            self.assertEqual(page.character_keys, ["character:2", ""])
        finally:
            views._REAL_ENCYCLOPEDIA_PAGE = previous_real_page
            shell.character_combo.deleteLater()
            self.app.processEvents()

    def test_character_sync_updates_only_pages_already_materialized(self) -> None:
        previous_real_page = views._REAL_ENCYCLOPEDIA_PAGE
        previous_character_page = app_main.CharacterPage

        class EncyclopediaPageStub:
            def __init__(self) -> None:
                self.refresh_calls = 0
                self.character_keys: list[str] = []

            def refresh_characters(self) -> None:
                self.refresh_calls += 1

            def set_character_key(self, character_key: str) -> None:
                self.character_keys.append(character_key)

        class CharacterPageStub:
            constructed = 0

            def __init__(self) -> None:
                self.__class__.constructed += 1
                self.character_keys: list[str] = []

            def refresh_from_sources(self, character_key: str) -> None:
                self.character_keys.append(character_key)

        class Shell:
            def __init__(self) -> None:
                self.current_character_key = "character:42"
                self.page_widgets: dict[str, object] = {}

            def sync_selected_character_to_pages(self) -> None:
                app_main.AtlasWindow.sync_selected_character_to_pages(self)

        try:
            views._REAL_ENCYCLOPEDIA_PAGE = EncyclopediaPageStub
            app_main.CharacterPage = CharacterPageStub
            shell = Shell()

            shell.sync_selected_character_to_pages()
            self.assertEqual(CharacterPageStub.constructed, 0)
            self.assertEqual(shell.page_widgets, {})

            encyclopedia = EncyclopediaPageStub()
            shell.page_widgets["Quetes"] = encyclopedia
            shell.sync_selected_character_to_pages()
            self.assertEqual(encyclopedia.refresh_calls, 1)
            self.assertEqual(encyclopedia.character_keys, ["character:42"])
            self.assertEqual(CharacterPageStub.constructed, 0)

            shell.page_widgets.pop("Quetes")
            character_page = CharacterPageStub()
            shell.page_widgets["Personnage"] = character_page
            shell.sync_selected_character_to_pages()
            self.assertEqual(character_page.character_keys, ["character:42"])

            shell.page_widgets["Quetes"] = encyclopedia
            shell.sync_selected_character_to_pages()
            self.assertEqual(encyclopedia.refresh_calls, 2)
            self.assertEqual(character_page.character_keys, ["character:42", "character:42"])

            shell.current_character_key = "character:84"
            shell.sync_selected_character_to_pages()
            self.assertEqual(encyclopedia.character_keys[-1], "character:84")
            self.assertEqual(character_page.character_keys[-1], "character:84")
            self.assertEqual(CharacterPageStub.constructed, 1)
        finally:
            views._REAL_ENCYCLOPEDIA_PAGE = previous_real_page
            app_main.CharacterPage = previous_character_page


if __name__ == "__main__":
    unittest.main()
