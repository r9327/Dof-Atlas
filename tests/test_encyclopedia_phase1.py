from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.constants import ENCYCLOPEDIA_TABS, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.views import EncyclopediaPage
from app.pages.quests_page import QuestsPage
from app.quest_catalog import QuestCatalog, QuestObjective, QuestRecord, QuestReward, QuestStep


class EncyclopediaPhase1Tests(unittest.TestCase):
    def make_catalog(self) -> QuestCatalog:
        return QuestCatalog(
            [
                QuestRecord(
                    id=101,
                    name="Bouftou royal",
                    category="Quetes principales",
                    level_min=10,
                    level_max=10,
                    start_criterion="",
                    zones=["Tainela"],
                    achievements=["Succes Bouftou"],
                    prerequisites=["Parler au berger"],
                    rewards=[QuestReward("Laine royale", 2, item_id=1001)],
                    steps=[
                        QuestStep(
                            id=1,
                            name="Entrer dans l'enclos",
                            description="Aller en [1,-32].",
                            objectives=[
                                QuestObjective(
                                    id=1,
                                    text="Rapporter une laine",
                                    type_id=2,
                                    item_id=1001,
                                    item_quantity=2,
                                    image_label="Laine royale",
                                )
                            ],
                        )
                    ],
                ),
                QuestRecord(
                    id=102,
                    name="Frigost d'abord",
                    category="Quetes principales",
                    level_min=50,
                    level_max=50,
                    start_criterion="Qf=101",
                    zones=["Ile de Frigost"],
                    achievements=["Succes Frigost"],
                    steps=[
                        QuestStep(
                            id=2,
                            name="La traversee",
                            description="Parler au capitaine.",
                        )
                    ],
                ),
            ]
        )

    def make_page(self, tmp_path: Path) -> tuple[QApplication, EncyclopediaPage, list[str], Path]:
        app = QApplication.instance() or QApplication([])
        profile_path = tmp_path / "client_profiles.json"
        client_index_path = tmp_path / "client_index.json"
        progress_path = tmp_path / "quest_progress.json"
        owned_items_path = tmp_path / "craft_selection.json"
        profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index_path.write_text(
            json.dumps({"clients": [{"index": 1, "name": "Alpha", "handle": 1234}]}),
            encoding="utf-8",
        )
        progress_path.write_text(
            json.dumps({"version": 1, "characters": {"character:1": {"done": {"999": True}}}}),
            encoding="utf-8",
        )
        owned_items_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        statuses: list[str] = []
        quest_provider = QuestProvider(catalog=self.make_catalog())
        # This UI navigation test must not accidentally launch the 1,976-quest
        # production Successes/Guide ingest. Cold catalogue lifecycle has its
        # own dedicated tests; here both background workers use a real, small
        # per-test provider and finish before Windows removes the temp directory.
        raw_dir = tmp_path / "achievement_sources"
        (raw_dir / "languages").mkdir(parents=True)
        (raw_dir / "languages" / "fr.json").write_text(
            json.dumps({"entries": {"1": "Succès de test"}}), encoding="utf-8"
        )
        def rows(*values):
            return {"references": {"RefIds": [{"data": value} for value in values]}}
        fixtures = {
            "achievements.json": rows({
                "id": 10, "nameId": 1, "descriptionId": -1, "categoryId": 8,
                "level": 1, "points": 5, "objectiveIds": [], "rewardIds": [],
            }),
            "achievement_categories.json": rows({
                "id": 8, "nameId": 1, "parentId": 0, "achievementIds": [10],
            }),
        }
        for name in ("achievement_objectives.json", "quests.json", "monsters.json",
                     "dungeons.json", "achievement_rewards.json", "items.json",
                     "spells.json", "titles.json", "emoticons.json", "ornaments.json",
                     "alterations.json"):
            fixtures[name] = rows()
        for name, payload in fixtures.items():
            (raw_dir / name).write_text(json.dumps(payload), encoding="utf-8")
        achievement_provider = AchievementProvider(
            data_dir=raw_dir, quest_provider=quest_provider,
        )
        guides_dir = tmp_path / "guides"
        guides_dir.mkdir()
        (guides_dir / "fixture.json").write_text(json.dumps({
            "schema_version": 1, "id": "fixture", "title": "Guide de test",
            "category": "aventure", "completeness_status": "complete",
            "sections": [{"id": "intro", "title": "Départ", "steps": [
                {"id": "read", "type": "info", "title": "Présentation"},
            ]}],
        }), encoding="utf-8")
        page = EncyclopediaPage(
            statuses.append,
            quest_provider=quest_provider,
            achievement_provider=achievement_provider,
            guide_provider=GuideProvider(
                guides_dir=guides_dir, quest_provider=quest_provider,
                achievement_provider=achievement_provider,
            ),
            achievement_progress_path=tmp_path / "achievement_progress.json",
            guide_progress_path=tmp_path / "guide_progress.json",
            progress_path=progress_path,
            profile_path=profile_path,
            client_index_path=client_index_path,
            owned_items_path=owned_items_path,
        )
        page.set_character_key("character:1")
        return app, page, statuses, progress_path

    def test_tabs_are_exact_and_quests_is_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, page, _statuses, _progress_path = self.make_page(Path(tmp))

            self.assertEqual(page.tab_labels(), list(ENCYCLOPEDIA_TABS))
            self.assertEqual(page.current_tab_label(), QUESTS_TAB)
            self.assertIsInstance(page.quest_page, QuestsPage)
            self.assertIs(page.tabs.currentWidget(), page.quest_page)

            page.deleteLater()
            app.processEvents()

    def test_quest_tab_loads_and_searches_current_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, page, _statuses, _progress_path = self.make_page(Path(tmp))
            quest_page = page.quest_page
            self.assertIsNotNone(quest_page)

            assert quest_page is not None
            self.assertEqual(len(quest_page.catalog.quests), 2)
            self.assertEqual(quest_page.quest_list.count(), 0)
            self.assertEqual(quest_page.detail.toHtml(), "")

            quest_page.search.setText("bouft")
            quest_page._flush_search_refresh()

            self.assertEqual(quest_page.quest_list.count(), 1)
            self.assertIn("Bouftou royal", quest_page.quest_list.item(0).text())
            self.assertIn("Niveau 10", quest_page.quest_list.item(0).text())
            quest_page.quest_list.setCurrentItem(quest_page.quest_list.item(0))
            app.processEvents()
            self.assertIn("Laine royale", quest_page.detail.toHtml())
            self.assertEqual(quest_page.search.text(), "")
            self.assertFalse(quest_page.quest_list.isVisible())
            self.assertEqual(quest_page.quest_list.count(), 0)

            page.deleteLater()
            app.processEvents()

    def test_character_selection_and_progress_save_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, page, _statuses, progress_path = self.make_page(Path(tmp))
            quest_page = page.quest_page
            self.assertIsNotNone(quest_page)

            assert quest_page is not None
            self.assertEqual(quest_page.current_character_key, "character:1")
            quest_page.search.setText("bouft")
            quest_page._flush_search_refresh()
            first = quest_page.quest_list.item(0)
            first.setCheckState(Qt.Checked)
            app.processEvents()

            saved = json.loads(progress_path.read_text(encoding="utf-8"))
            self.assertTrue(saved["characters"]["character:1"]["done"]["101"])
            self.assertTrue(saved["characters"]["character:1"]["done"]["999"])

            page.deleteLater()
            app.processEvents()

    def test_tab_changes_do_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, page, statuses, _progress_path = self.make_page(Path(tmp))

            for index in range(page.tabs.count()):
                page.tabs.setCurrentIndex(index)
                app.processEvents()

            self.assertEqual(page.tabs.count(), len(ENCYCLOPEDIA_TABS))
            self.assertEqual(page.tab_labels(), list(ENCYCLOPEDIA_TABS))
            self.assertTrue(statuses)
            self.assertEqual(page.current_tab_label(), ENCYCLOPEDIA_TABS[-1])

            # Tab changes deliberately kick off Guide/Achievement background
            # progress readers. On Windows an active quest_progress.json.lock
            # cannot be deleted by TemporaryDirectory cleanup. Wait for the
            # actual workers to finish instead of ignoring a leaked lock.
            deadline = time.monotonic() + 15
            busy_names = (
                "_quest_load_started",
                "_related_preload_started",
                "_achievement_load_started",
            )
            while time.monotonic() < deadline:
                app.processEvents()
                if not any(bool(getattr(page, flag, False)) for flag in busy_names):
                    break
                time.sleep(0.02)
            self.assertFalse(
                any(bool(getattr(page, flag, False)) for flag in busy_names),
                "Encyclopedia background worker remains active at test teardown: "
                + repr({flag: getattr(page, flag, False) for flag in busy_names}),
            )
            self.assertFalse(
                any("impossible" in message.lower() for message in statuses),
                statuses,
            )
            page.close()
            page.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
