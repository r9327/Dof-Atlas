from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, ENCYCLOPEDIA_TABS, QUESTS_TAB
from app.modules.encyclopedia.models import Achievement
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService
from app.modules.encyclopedia.views import EncyclopediaPage, EncyclopediaPlaceholderView, GuidesView
from app.modules.encyclopedia.widgets import AchievementDetailWidget
from app.quest_catalog import QuestCatalog, QuestCharacter, QuestRecord, QuestStep


class AchievementProviderPhase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = AchievementProvider()
        cls.achievements = cls.provider.load_all()

    def test_provider_loads_non_empty_list_and_keeps_original_ids(self):
        self.assertGreater(len(self.achievements), 0)
        sample = self.achievements[0]
        self.assertIsInstance(sample, Achievement)
        self.assertEqual(sample.id, sample.original_id)

    def test_categories_are_resolved(self):
        categories = self.provider.get_categories()
        self.assertGreater(len(categories), 0)
        self.assertTrue(any(category.parent_id == 0 for category in categories))
        self.assertTrue(any(category.name for category in categories))

    def test_objectives_are_attached_to_their_achievement(self):
        achievement = next(item for item in self.achievements if item.objectives)
        self.assertGreater(len(achievement.objectives), 0)
        self.assertTrue(all(objective.achievement_id == achievement.id for objective in achievement.objectives))

    def test_rewards_parse_without_exception(self):
        achievement = next(item for item in self.achievements if item.rewards)
        self.assertGreater(len(achievement.rewards), 0)
        self.assertTrue(all(reward.name for reward in achievement.rewards))

    def test_search_finds_known_achievement(self):
        results = self.provider.search("bouftou")
        self.assertTrue(any("Bouftou" in item.name for item in results))

    def test_search_ignores_accents_and_case(self):
        results = self.provider.search("MAIRE DENIE")
        self.assertTrue(any(item.id == 551 and item.name == "La maire dénie" for item in results))

    def test_link_methods_return_reliable_relations(self):
        linked_achievement = next(item for item in self.achievements if item.linked_quests)
        self.assertEqual(self.provider.get_linked_quests(linked_achievement.id), list(linked_achievement.linked_quests))
        self.assertIn(linked_achievement.id, [item.id for item in self.provider.get_by_quest(linked_achievement.linked_quests[0].entity_id)])
        dungeon_achievement = next(item for item in self.achievements if item.linked_dungeons)
        self.assertEqual(self.provider.get_linked_dungeons(dungeon_achievement.id), list(dungeon_achievement.linked_dungeons))
        monster_achievement = next(item for item in self.achievements if item.linked_monsters)
        self.assertEqual(self.provider.get_linked_monsters(monster_achievement.id), list(monster_achievement.linked_monsters))


class AchievementProgressPhase2Tests(unittest.TestCase):
    def test_progress_is_independent_for_two_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            service = AchievementProgressService(path)

            service.set_achievement_completed("character:1", 37, True)

            self.assertTrue(service.is_achievement_completed("character:1", 37))
            self.assertFalse(service.is_achievement_completed("character:2", 37))

    def test_progress_can_be_saved_and_read_again_without_touching_quest_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            achievement_path = tmp_path / "achievement_progress.json"
            quest_path = tmp_path / "quest_progress.json"
            quest_payload = {"version": 1, "characters": {"character:1": {"done": {"101": True}}}}
            quest_path.write_text(json.dumps(quest_payload), encoding="utf-8")

            service = AchievementProgressService(achievement_path)
            service.set_achievement_completed("character:1", 37, True)
            service.set_objective_completed("character:1", 37, 901, True)

            reloaded = AchievementProgressService(achievement_path)
            self.assertTrue(reloaded.is_achievement_completed("character:1", 37))
            self.assertTrue(reloaded.is_objective_completed("character:1", 37, 901))
            self.assertEqual(json.loads(quest_path.read_text(encoding="utf-8")), quest_payload)


class AchievementContextPhase2Tests(unittest.TestCase):
    @staticmethod
    def app() -> QApplication:
        return QApplication.instance() or QApplication([])

    def make_temp_paths(self, tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
        profile_path = tmp_path / "client_profiles.json"
        client_index_path = tmp_path / "client_index.json"
        quest_progress_path = tmp_path / "quest_progress.json"
        achievement_progress_path = tmp_path / "achievement_progress.json"
        owned_items_path = tmp_path / "craft_selection.json"
        profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index_path.write_text(
            json.dumps({"clients": [{"index": 1, "name": "Alpha", "handle": 1001}]}),
            encoding="utf-8",
        )
        quest_progress_path.write_text(
            json.dumps({"version": 1, "characters": {"character:1": {"done": {"999": True}}}}),
            encoding="utf-8",
        )
        owned_items_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        return profile_path, client_index_path, quest_progress_path, achievement_progress_path, owned_items_path

    def make_quest_catalog(self, linked_quest_id: int) -> QuestCatalog:
        return QuestCatalog(
            [
                QuestRecord(
                    id=linked_quest_id,
                    name="Les quatre volontés",
                    category="Quêtes principales",
                    level_min=1,
                    level_max=1,
                    start_criterion="",
                    zones=["Amakna"],
                    achievements=["La chevauchée fantastique"],
                    steps=[QuestStep(id=1, name="Départ", description="Objectif local.")],
                ),
                QuestRecord(
                    id=101,
                    name="Bouftou royal",
                    category="Quêtes principales",
                    level_min=10,
                    level_max=10,
                    start_criterion="",
                    zones=["Tainéla"],
                    achievements=["Succès Bouftou"],
                ),
            ]
        )

    def make_empty_guide_provider(self, tmp_path: Path, quest_provider: QuestProvider) -> GuideProvider:
        empty_guides_dir = tmp_path / "guides"
        empty_guides_dir.mkdir(exist_ok=True)
        return GuideProvider(guides_dir=empty_guides_dir, quest_provider=quest_provider)

    def test_achievement_detail_widget_loads_in_qt_offscreen(self):
        app = self.app()
        provider = AchievementProvider()
        achievement = next(item for item in provider.load_all() if item.objectives)
        with tempfile.TemporaryDirectory() as tmp:
            service = AchievementProgressService(Path(tmp) / "achievement_progress.json")
            widget = AchievementDetailWidget(achievement, service, "character:1")
            app.processEvents()

            self.assertIn(achievement.name, [label.text() for label in widget.findChildren(QLabel)])
            self.assertTrue(widget.findChildren(QLabel))
            widget.deleteLater()
            app.processEvents()

    def test_visible_achievements_tab_and_other_placeholders_remain(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            profile, client_index, quest_progress, achievement_progress, owned = self.make_temp_paths(Path(tmp))
            quest_provider = QuestProvider(catalog=self.make_quest_catalog(2122))
            achievement_provider = AchievementProvider(quest_provider=quest_provider)
            verified_characters = [QuestCharacter("character:201", "Alpha", 1, True)]
            with patch(
                "app.modules.encyclopedia.views.encyclopedia_page.load_quest_characters",
                return_value=verified_characters,
            ):
                page = EncyclopediaPage(
                    lambda _text: None,
                    quest_provider=quest_provider,
                    guide_provider=self.make_empty_guide_provider(Path(tmp), quest_provider),
                    achievement_provider=achievement_provider,
                    progress_path=quest_progress,
                    achievement_progress_path=achievement_progress,
                    profile_path=profile,
                    client_index_path=client_index,
                    owned_items_path=owned,
                )

            self.assertEqual(page.tab_labels(), list(ENCYCLOPEDIA_TABS))
            self.assertFalse(hasattr(page, "achievements_view"))
            self.assertIsInstance(page.tabs.widget(page.tab_labels().index("GUIDES")), EncyclopediaPlaceholderView)
            page.tabs.setCurrentIndex(page.tab_labels().index("GUIDES"))
            app.processEvents()
            self.assertIsInstance(page.tabs.widget(page.tab_labels().index("GUIDES")), GuidesView)
            page.tabs.setCurrentIndex(page.tab_labels().index(QUESTS_TAB))
            app.processEvents()
            self.assertIsInstance(page.tabs.widget(page.tab_labels().index(ACHIEVEMENTS_TAB)), EncyclopediaPlaceholderView)
            page.tabs.setCurrentIndex(page.tab_labels().index(ACHIEVEMENTS_TAB))
            app.processEvents()
            self.assertEqual(page.current_tab_label(), ACHIEVEMENTS_TAB)
            self.assertNotIsInstance(
                page.tabs.widget(page.tab_labels().index(ACHIEVEMENTS_TAB)),
                EncyclopediaPlaceholderView,
            )
            page.tabs.setCurrentIndex(page.tab_labels().index(QUESTS_TAB))
            app.processEvents()
            placeholder_tabs = {"DONJONS", "MONSTRES", "ARCHIMONSTRES", "AVIS DE RECHERCHE"}
            for index in range(page.tabs.count()):
                label = page.tabs.tabText(index)
                if label in placeholder_tabs:
                    self.assertIsInstance(page.tabs.widget(index), EncyclopediaPlaceholderView)

            self.assertEqual(page.current_tab_label(), QUESTS_TAB)
            assert page.quest_page is not None
            page.quest_page.search.setText("bouft")
            app.processEvents()
            self.assertEqual(page.quest_page.quest_list.count(), 1)
            self.assertIn("Bouftou royal", page.quest_page.quest_list.item(0).text())

            page.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
