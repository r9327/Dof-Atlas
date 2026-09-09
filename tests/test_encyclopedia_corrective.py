from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QSpinBox

from app.constants import KEY_SESSION_ORDER
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, ENCYCLOPEDIA_TABS, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, GuideProgressService, QuestGraphService
from app.modules.encyclopedia.views import EncyclopediaPage
from app.modules.encyclopedia.views.guides_view import QuestLine
from app.modules.encyclopedia.widgets import GUIDE_GROUP_ROLE
from app.quest_catalog import QuestCatalog, QuestRecord, QuestStep, load_quest_progress, set_quest_done
from app.storage import AtlasButton

TURQUOISE_ACHIEVEMENT_ID = 1385
TURQUOISE_GUIDE_ID = "dofus_turquoise"
TURQUOISE_QUESTS = [
    (1653, "Plongeon et dragon"),
    (1654, "Extinction des feux"),
    (1656, "On dirait le Sud"),
    (1657, "La méchante sorcière de l'Est"),
    (1658, "Autel du Nord"),
    (1659, "Il était une foi dans l'Ouest"),
    (1660, "La bénédiction de Viti"),
    (1661, "La bénédiction de Thomahon"),
    (1662, "La bénédiction de Foluk"),
    (1663, "Une âme en colère"),
]


class EncyclopediaCorrectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_catalog(self) -> QuestCatalog:
        return QuestCatalog(
            [
                QuestRecord(
                    id=quest_id,
                    name=name,
                    category="Quêtes mondiales",
                    level_min=160,
                    level_max=200,
                    start_criterion="",
                    zones=["Dofus Turquoise"],
                    achievements=["Bleu turquoise"],
                    steps=[QuestStep(id=quest_id, name=name, description="Donnée locale de test.")],
                )
                for quest_id, name in TURQUOISE_QUESTS
            ]
        )

    def temp_paths(self, tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
        profile_path = tmp_path / "client_profiles.json"
        client_index_path = tmp_path / "client_index.json"
        quest_progress_path = tmp_path / "quest_progress.json"
        achievement_progress_path = tmp_path / "achievement_progress.json"
        guide_progress_path = tmp_path / "guide_progress.json"
        owned_items_path = tmp_path / "craft_selection.json"
        profile_path.write_text(
            json.dumps({KEY_SESSION_ORDER: ["alpha", "beta", "", "", "", "", "", ""]}),
            encoding="utf-8",
        )
        client_index_path.write_text(
            json.dumps({"clients": [{"index": 1, "name": "Alpha", "handle": 1001}]}),
            encoding="utf-8",
        )
        quest_progress_path.write_text(json.dumps({"version": 1, "characters": {}}), encoding="utf-8")
        owned_items_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        return profile_path, client_index_path, quest_progress_path, achievement_progress_path, guide_progress_path, owned_items_path

    def make_page(self, tmp_path: Path) -> EncyclopediaPage:
        profile, client_index, quest_progress, achievement_progress, guide_progress, owned = self.temp_paths(tmp_path)
        quest_provider = QuestProvider()
        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(quest_provider=quest_provider, achievement_provider=achievement_provider)
        page = EncyclopediaPage(
            lambda _text: None,
            quest_provider=quest_provider,
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
            progress_path=quest_progress,
            achievement_progress_path=achievement_progress,
            guide_progress_path=guide_progress,
            profile_path=profile,
            client_index_path=client_index,
            owned_items_path=owned,
        )
        page.show()
        self.app.processEvents()
        page.set_character_key("character:1")
        return page

    def test_visible_tabs_and_global_character_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))

            self.assertEqual(page.tab_labels(), list(ENCYCLOPEDIA_TABS))
            self.assertEqual(page.tab_labels(), ["GUIDES", "QUÊTES", ACHIEVEMENTS_TAB, "DONJONS", "MONSTRES", "ARCHIMONSTRES", "AVIS DE RECHERCHE"])
            self.assertEqual(page.current_tab_label(), QUESTS_TAB)
            visible_combos = [combo for combo in page.findChildren(QComboBox) if combo.isVisibleTo(page)]
            self.assertNotIn("EncyclopediaCharacterCombo", [combo.objectName() for combo in visible_combos])
            self.assertFalse(page.quest_page.character_combo.isVisibleTo(page))

            page.set_character_key("character:2")
            self.app.processEvents()
            self.assertEqual(page.current_character_key, "character:2")
            self.assertEqual(page.quest_page.current_character_key, "character:2")

            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            self.app.processEvents()
            assert page.guides_view is not None
            self.assertEqual(page.guides_view.current_character_key, "character:2")
            page.tabs.setCurrentIndex(page.tab_labels().index(QUESTS_TAB))
            self.app.processEvents()
            self.assertEqual(page.current_character_key, "character:2")

            page.deleteLater()
            self.app.processEvents()

    def test_preloaded_related_data_updates_quests_without_rebuilding_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile, client_index, quest_progress, achievement_progress, guide_progress, owned = self.temp_paths(tmp_path)
            guide_dir = tmp_path / "guides"
            guide_dir.mkdir()
            quest_provider = QuestProvider(catalog=self.make_catalog())
            achievement_provider = AchievementProvider(quest_provider=quest_provider)
            guide_provider = GuideProvider(
                guides_dir=guide_dir,
                quest_provider=quest_provider,
                achievement_provider=achievement_provider,
            )
            graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
            page = EncyclopediaPage(
                lambda _text: None,
                quest_provider=quest_provider,
                progress_path=quest_progress,
                achievement_progress_path=achievement_progress,
                guide_progress_path=guide_progress,
                profile_path=profile,
                client_index_path=client_index,
                owned_items_path=owned,
            )
            page.show()
            self.app.processEvents()

            original_quest_page = page.quest_page
            self.assertIsNotNone(original_quest_page)

            page.apply_preloaded_related_data(
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
                quest_graph=graph,
            )

            self.assertIs(page.quest_page, original_quest_page)
            assert page.quest_page is not None
            self.assertIs(page.quest_page.graph, graph)
            self.assertIs(page.service.achievement_provider, achievement_provider)
            self.assertIs(page.service.guide_provider, guide_provider)
            self.assertIsNone(page.guides_view)
            page.on_tab_changed(page.tab_labels().index(GUIDES_TAB))
            self.app.processEvents()
            self.assertIsNotNone(page.guides_view)
            assert page.guides_view is not None
            self.assertIs(page.guides_view.graph, graph)
            page.deleteLater()
            self.app.processEvents()

    def test_guides_layout_filters_and_burger_width_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            view = page.guides_view
            assert view is not None

            self.assertEqual(view.splitter.count(), 3)
            self.assertFalse(hasattr(view, "filter_panel"))
            self.assertFalse(view.findChildren(QSpinBox))
            self.assertFalse(hasattr(view, "state_combo"))
            self.assertFalse(hasattr(view, "min_level"))
            self.assertFalse(hasattr(view, "category_buttons"))
            self.assertFalse(hasattr(view, "set_category"))
            self.assertFalse(hasattr(view, "hide_completed"))
            groups = [
                view.result_model.data(view.result_model.index(row, 0), GUIDE_GROUP_ROLE)
                for row in range(view.result_model.rowCount())
            ]
            self.assertIn("AVENTURE", groups)
            self.assertIn("DOFUS", groups)
            self.assertIn("ALIGNEMENTS", groups)

            open_content_width = 900 - 190
            closed_content_width = 900 - 44
            page.resize(open_content_width, 560)
            self.app.processEvents()
            open_center_width = view.splitter.sizes()[1]
            page.resize(closed_content_width, 560)
            self.app.processEvents()
            closed_sizes = view.splitter.sizes()
            closed_center_width = closed_sizes[1]
            self.assertGreaterEqual(closed_center_width, open_center_width)
            self.assertGreater(closed_center_width, closed_sizes[0])
            self.assertGreater(closed_center_width, closed_sizes[2])

            page.deleteLater()
            self.app.processEvents()

    def test_guide_cards_statuses_turquoise_image_and_contextual_achievement(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            view = page.guides_view
            assert view is not None
            guide = view.provider.get_by_id(TURQUOISE_GUIDE_ID)
            assert guide is not None

            self.assertEqual(guide.reward_item_id, 739)
            self.assertEqual(guide.illustration_item_id, 739)
            self.assertEqual(guide.reward_item.name, "Dofus Turquoise")
            self.assertTrue(Path(guide.image_path).exists())
            self.assertEqual(Path(guide.image_path).name, "23003.png")
            self.assertEqual([ref.entity_id for ref in guide.context_entities if ref.entity_type == "achievement"], [TURQUOISE_ACHIEVEMENT_ID])
            self.assertFalse([step for step in guide.steps if step.step_type == "achievement"])

            view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()
            labels = [label.text() for label in view.findChildren(QLabel)]
            self.assertFalse(any(text in {"NEXT", "LOCK", "OPT"} for text in labels))
            self.assertFalse(any("Prochaine étape" in text for text in labels))
            self.assertTrue(any(text == "Informations du guide" for text in labels))
            self.assertTrue(any(text.casefold() == "récompenses" for text in labels))
            self.assertFalse(any("Bloquée" in text for text in labels))
            self.assertFalse(any("Disponible" in text for text in labels))
            self.assertFalse(any(button.text() == "Continuer le parcours" for button in view.findChildren(AtlasButton)))

            page.navigate_to_entity("achievement", TURQUOISE_ACHIEVEMENT_ID)
            self.app.processEvents()
            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            self.assertEqual(view.current_guide_id, TURQUOISE_GUIDE_ID)

            page.deleteLater()
            self.app.processEvents()

    def test_hide_completed_steps_and_cross_navigation_still_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            self.app.processEvents()
            view = page.guides_view
            assert view is not None
            guide = view.provider.get_by_id(TURQUOISE_GUIDE_ID)
            assert guide is not None

            progress = load_quest_progress(view.quest_progress_path)
            for step in guide.required_steps:
                if step.step_type != "quest" or step.entity_id is None:
                    continue
                set_quest_done(progress, "character:1", step.entity_id, True, view.quest_progress_path)
                progress = load_quest_progress(view.quest_progress_path)
            view.refresh_external_progress()
            self.assertEqual(view.guide_state(guide), "Terminé")
            self.assertTrue(any(item.id == TURQUOISE_GUIDE_ID for item in view.visible_guides))

            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()
            quest_line = next(
                line
                for line in view.findChildren(QuestLine)
                if line.step.step_type == "quest" and line.step.entity_id == 1653
            )
            quest_line.selected.emit(1653)
            self.app.processEvents()
            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            self.assertEqual(view.current_quest_id, 1653)
            self.assertEqual(view.quest_detail_view.current_quest_id, 1653)
            labels = [label.text() for label in view.quest_detail_view.findChildren(QLabel)]
            self.assertTrue(any(text == "Informations de quête" for text in labels))
            linked_successes = [
                button.text()
                for button in view.quest_detail_view.findChildren(AtlasButton)
            ]
            self.assertTrue(any("Bleu turquoise" in text for text in linked_successes))

            page.navigate_to_entity("guide", TURQUOISE_GUIDE_ID)
            self.app.processEvents()
            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            self.assertEqual(view.current_guide_id, TURQUOISE_GUIDE_ID)

            page.deleteLater()
            self.app.processEvents()

    def test_invalid_object_reference_and_dofus_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            guide_dir = Path(tmp) / "guides"
            guide_dir.mkdir()
            (guide_dir / "bad_item.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "bad_item",
                        "title": "Bad item",
                        "category": "Dofus",
                        "reward_item_id": 999999,
                        "illustration_item_id": 999999,
                        "sections": [],
                    }
                ),
                encoding="utf-8",
            )
            provider = GuideProvider(guides_dir=guide_dir, quest_provider=QuestProvider(catalog=QuestCatalog([])))
            guides = provider.load_all()
            self.assertEqual(len(guides), 1)
            self.assertTrue(any("reward_item_id invalide" in error for error in provider.validation_errors))
            self.assertTrue(any("illustration_item_id invalide" in error for error in provider.validation_errors))

        result = subprocess.run(
            [sys.executable, "-m", "app.modules.encyclopedia.tools.list_dofus_items"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("739 | Dofus Turquoise | 160 | Dofus | OK | dofus_turquoise", result.stdout)

    def test_provider_uses_no_network(self):
        original_socket = socket.socket

        def forbidden_socket(*_args, **_kwargs):
            raise AssertionError("network call forbidden")

        socket.socket = forbidden_socket
        try:
            provider = GuideProvider(quest_provider=QuestProvider(catalog=self.make_catalog()))
            self.assertGreater(len(provider.load_all()), 0)
        finally:
            socket.socket = original_socket


if __name__ == "__main__":
    unittest.main()
