from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QUrl
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QProgressBar, QScrollArea, QSpinBox, QToolButton

from app.constants import DATA_DIR, KEY_SESSION_ORDER
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import (
    AchievementProgressService,
    GuideProgressService,
    build_related_encyclopedia_data,
    related_data_build_count,
)
from app.modules.encyclopedia.views import EncyclopediaPage, GuidesView
from app.modules.encyclopedia.views.guides_view import (
    DOFUS_CARD_HEIGHT,
    DOFUS_CARD_MAX_WIDTH,
    DofusGuideGrid,
    CollapsibleInfoSection,
    GuideCollapsedStepsRail,
    GuideHomeCard,
    QuestLine,
    SolutionImageLabel,
    activity_icon_key,
    item_row,
)
from app.modules.encyclopedia.widgets.achievement_entity_section import AchievementEntityRow
from app.modules.encyclopedia.services.guide_quest_view_model import (
    DisplayItem,
    clean_requirement_line,
    guide_rewards,
    quest_activity_labels,
    quest_rewards,
    reward_label,
    quest_solution_blocks,
)
from app.storage import AtlasButton
from app.quest_catalog import QuestCatalog, QuestRecord, QuestSolutionBlock, QuestStep, load_quest_progress, normalize_text, quest_done, set_quest_done

TURQUOISE_ACHIEVEMENT_ID = 1385
TURQUOISE_GUIDE_ID = "dofus_turquoise"
ADVENTURE_GUIDE_ID = "guide_complet"
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


class FakeAchievementProvider:
    def __init__(self, ids: set[int] | None = None) -> None:
        self.ids = ids or set()

    def get_by_id(self, achievement_id: int):
        if int(achievement_id) not in self.ids:
            return None
        return type("AchievementStub", (), {"id": int(achievement_id), "name": f"Succès {achievement_id}"})()


class GuidePhase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.guide_provider = GuideProvider(
            quest_provider=cls.quest_provider,
            achievement_provider=cls.achievement_provider,
        )
        cls.guides = cls.guide_provider.load_all()

    @staticmethod
    def make_catalog() -> QuestCatalog:
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

    def make_view(self, tmp_path: Path) -> GuidesView:
        profile, client_index, quest_progress, achievement_progress, guide_progress, _owned = self.temp_paths(tmp_path)
        view = GuidesView(
            lambda _text: None,
            provider=self.guide_provider,
            achievement_progress_service=AchievementProgressService(achievement_progress),
            guide_progress_service=GuideProgressService(guide_progress),
            quest_progress_path=quest_progress,
            profile_path=profile,
            client_index_path=client_index,
        )
        view.set_character_key("character:1")
        return view

    def make_page(self, tmp_path: Path) -> EncyclopediaPage:
        profile, client_index, quest_progress, achievement_progress, guide_progress, owned = self.temp_paths(tmp_path)
        return EncyclopediaPage(
            lambda _text: None,
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
            guide_provider=self.guide_provider,
            progress_path=quest_progress,
            achievement_progress_path=achievement_progress,
            guide_progress_path=guide_progress,
            profile_path=profile,
            client_index_path=client_index,
            owned_items_path=owned,
        )

    def test_guide_provider_loads_valid_guide(self):
        guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)

        self.assertIsNotNone(guide)
        assert guide is not None
        self.assertEqual(guide.title, "Dofus Turquoise")
        self.assertEqual(self.guide_provider.validation_errors, [])

    def test_invalid_guide_does_not_crash_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 1, "guides": ["bad.json"]}), encoding="utf-8")
            (tmp_path / "bad.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "bad",
                        "title": "Bad",
                        "category": "Dofus",
                        "sections": [{"id": "s", "steps": [{"id": "bad_step", "type": "quest", "entity_id": 999999}]}],
                    }
                ),
                encoding="utf-8",
            )
            provider = GuideProvider(
                guides_dir=tmp_path,
                quest_provider=QuestProvider(catalog=QuestCatalog([])),
                achievement_provider=FakeAchievementProvider(),
            )

            guides = provider.load_all()

            self.assertEqual(len(guides), 1)
            self.assertTrue(provider.validation_errors)

    def test_quest_ids_are_resolved(self):
        guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
        assert guide is not None

        quest_steps = [step for step in guide.steps if step.step_type == "quest"]

        quest_ids = [step.entity_id for step in quest_steps]
        self.assertTrue({quest_id for quest_id, _name in TURQUOISE_QUESTS}.issubset(quest_ids))
        self.assertEqual(len(quest_ids), len(set(quest_ids)))
        self.assertTrue(all(step.entity_ref is not None for step in quest_steps))

    def test_achievement_ids_are_resolved(self):
        guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
        assert guide is not None

        achievement_refs = [ref for ref in guide.context_entities if ref.entity_type == "achievement"]

        self.assertEqual([ref.entity_id for ref in achievement_refs], [TURQUOISE_ACHIEVEMENT_ID])
        self.assertEqual(achievement_refs[0].label, "Bleu turquoise")
        self.assertFalse([step for step in guide.steps if step.step_type == "achievement"])

    def test_missing_reference_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "bad.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "missing_ref",
                        "title": "Missing",
                        "category": "Dofus",
                        "sections": [{"id": "s", "steps": [{"id": "bad_step", "type": "quest", "entity_id": 999999}]}],
                    }
                ),
                encoding="utf-8",
            )
            provider = GuideProvider(
                guides_dir=tmp_path,
                quest_provider=QuestProvider(catalog=QuestCatalog([])),
                achievement_provider=FakeAchievementProvider(),
            )
            provider.load_all()

            self.assertTrue(any("quete inexistante: 999999" in error for error in provider.validation_errors))

    def test_categories_are_built_from_guide_files(self):
        self.assertEqual(self.guide_provider.get_categories(), ["aventure", "dofus", "alignements"])
        self.assertEqual([self.guide_provider.get_category_label(category) for category in self.guide_provider.get_categories()], ["Aventure", "Dofus", "Alignements"])

    def test_search_finds_guide_by_title(self):
        results = self.guide_provider.search("turquoise")

        self.assertTrue(any(guide.id == TURQUOISE_GUIDE_ID for guide in results))

    def test_technical_local_conditions_are_hidden_from_display_models(self):
        quest = QuestRecord(
            id=999001,
            name="Critere technique",
            category="Test",
            level_min=1,
            level_max=1,
            start_criterion="PZ=1",
            prerequisites=["PZ=1", "BT=1&PZ=1", "Niveau 20+"],
            solution_blocks=[
                QuestSolutionBlock(order=1, block_type="text", content="PZ=1"),
                QuestSolutionBlock(order=2, block_type="text", content="Aller en [1,2]."),
            ],
        )

        self.assertEqual(clean_requirement_line("PZ=1"), "")
        self.assertEqual(clean_requirement_line("BT=1&PZ=1"), "")
        self.assertEqual(clean_requirement_line("Pz = 1"), "")
        self.assertEqual(clean_requirement_line("Niveau 20+"), "Niveau 20 et plus")
        self.assertEqual([block.content for block in quest_solution_blocks(quest)], ["Aller en [1,2]."])

    def test_quest_preparation_uses_dpln_source_and_icons(self):
        quest = self.quest_provider.get_quest(2154)
        assert quest is not None

        labels = quest_activity_labels(None, quest)

        self.assertEqual(
            labels,
            (
                "1 x Donjon : Fabrique de foux d'artifice",
                "1 x combat solo",
                "1 x combat en groupe",
                "Drop : combats de zone à 12%",
            ),
        )
        self.assertEqual(activity_icon_key("1 x combat solo"), "solo")
        self.assertEqual(activity_icon_key("1 x combat en groupe"), "group")
        self.assertEqual(activity_icon_key("1 x Donjon : Fabrique de foux d'artifice"), "dungeon")
        self.assertEqual(activity_icon_key("Drop : combats de zone à 12%"), "drop")
        self.assertEqual(activity_icon_key("1 x combat tactique"), "tactical")

    def test_quest_preparation_prefers_richer_dpln_combat_info(self):
        quest = self.quest_provider.get_quest(1908)
        assert quest is not None

        labels = quest_activity_labels(None, quest)

        self.assertEqual(labels, ("2 x combats en groupe", "1 x Donjon : Palais du roi Nidas"))

    def test_guide_rewards_dedupe_guide_item_and_achievement_reward(self):
        guide = self.guide_provider.get_by_id("dofus_pourpre")
        assert guide is not None

        rewards = guide_rewards(guide, self.achievement_provider)
        labels = [reward_label(reward) for reward in rewards]

        self.assertEqual(labels.count("Dofus Pourpre"), 1)
        self.assertNotIn("x2 Dofus Pourpre", labels)
        self.assertIn("50 points de succès", labels)

    def test_quest_rewards_do_not_include_linked_achievement_rewards(self):
        quest = self.quest_provider.get_quest(1524)
        assert quest is not None

        rewards = guide_rewards(self.guide_provider.get_by_id("dofus_pourpre"), self.achievement_provider)
        guide_labels = [reward_label(reward) for reward in rewards]
        quest_labels = [
            reward_label(reward)
            for reward in quest_rewards(quest, self.achievement_provider.get_by_quest(quest.id))
        ]

        self.assertIn("Dofus Pourpre", guide_labels)
        self.assertIn("50 points de succès", guide_labels)
        self.assertNotIn("Dofus Pourpre", quest_labels)
        self.assertNotIn("50 points de succès", quest_labels)
        self.assertIn("15 600 Kamas", quest_labels)
        self.assertIn("x2 Feuille de Blop Multicolore Royal", quest_labels)

    def test_quest_rewards_hide_technical_reward_names(self):
        quest = self.quest_provider.get_quest(2103)
        assert quest is not None

        labels = [reward_label(reward) for reward in quest_rewards(quest, self.achievement_provider.get_by_quest(quest.id))]

        self.assertNotIn("Dofus 15 ans - Qf=2103", labels)
        self.assertIn("x30 Kama d'Ankama", labels)

    def test_search_finds_guide_by_linked_quest(self):
        results = self.guide_provider.search("plongeon dragon")

        self.assertTrue(any(guide.id == TURQUOISE_GUIDE_ID for guide in results))

    def test_quest_progress_is_reflected_in_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
            assert guide is not None
            quest_step = next(step for step in guide.steps if step.entity_id == 1653)

            progress = load_quest_progress(view.quest_progress_path)
            set_quest_done(progress, "character:1", 1653, True, view.quest_progress_path)
            view.refresh_external_progress()

            self.assertTrue(view.step_completed(guide, quest_step))
            view.deleteLater()
            self.app.processEvents()

    def test_achievement_progress_is_contextual_not_counted_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
            assert guide is not None

            view.achievement_progress_service.set_achievement_completed("character:1", TURQUOISE_ACHIEVEMENT_ID, True)

            self.assertEqual([ref.entity_id for ref in guide.context_entities if ref.entity_type == "achievement"], [TURQUOISE_ACHIEVEMENT_ID])
            self.assertEqual(view.guide_state(guide), "Non commencé")
            view.deleteLater()
            self.app.processEvents()

    def test_optional_steps_do_not_block_guide_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
            assert guide is not None
            progress = load_quest_progress(view.quest_progress_path)
            for step in guide.required_steps:
                if step.step_type != "quest" or step.entity_id is None:
                    continue
                set_quest_done(progress, "character:1", step.entity_id, True, view.quest_progress_path)
                progress = load_quest_progress(view.quest_progress_path)
            view.refresh_external_progress()

            self.assertEqual(view.guide_state(guide), "Terminé")
            self.assertFalse([step for step in guide.steps if step.step_type in {"achievement", "info"}])
            view.deleteLater()
            self.app.processEvents()

    def test_manual_step_service_can_still_store_info_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))

            view.set_manual_step(TURQUOISE_GUIDE_ID, "future_info_step", True)

            self.assertTrue(
                view.guide_progress_service.is_manual_step_completed(
                    "character:1",
                    TURQUOISE_GUIDE_ID,
                    "future_info_step",
                )
            )
            view.deleteLater()
            self.app.processEvents()

    def test_manual_progress_is_independent_between_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GuideProgressService(Path(tmp) / "guide_progress.json")

            service.set_manual_step_completed("character:1", TURQUOISE_GUIDE_ID, "future_info_step", True)

            self.assertTrue(service.is_manual_step_completed("character:1", TURQUOISE_GUIDE_ID, "future_info_step"))
            self.assertFalse(service.is_manual_step_completed("character:2", TURQUOISE_GUIDE_ID, "future_info_step"))

    def test_continue_path_and_tracked_state_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()

            self.assertFalse(hasattr(view, "continue_path"))
            self.assertFalse(hasattr(view, "next_available_steps"))
            self.assertFalse(hasattr(view, "first_blocked_step"))
            self.assertFalse(hasattr(view, "active_guide_id"))
            self.assertFalse(any(button.text() == "Continuer le parcours" for button in view.findChildren(AtlasButton)))
            view.deleteLater()
            self.app.processEvents()

    def test_blocked_step_displays_missing_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide(TURQUOISE_GUIDE_ID)
            view.show_quest_detail(1654)
            self.app.processEvents()

            texts = [label.text() for label in view.findChildren(QLabel)]
            texts.extend(button.text() for button in view.findChildren(AtlasButton))

            self.assertEqual(view.state, view.QUEST_DETAIL)
            self.assertTrue(any(text == "Prérequis" for text in texts))
            self.assertTrue(any("Plongeon et dragon" in text for text in texts))
            view.deleteLater()
            self.app.processEvents()

    def test_guide_to_quest_stays_in_guide_and_uses_shared_quest_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            assert page.guides_view is not None
            page.guides_view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()

            line = next(
                child
                for child in page.guides_view.findChildren(QuestLine)
                if child.step.step_type == "quest" and child.step.entity_id == 1653
            )
            line.selected.emit(1653)
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            self.assertEqual(page.guides_view.current_quest_id, 1653)
            self.assertEqual(page.guides_view.quest_detail_view.current_quest_id, 1653)
            self.assertEqual(page.guides_view.quest_detail_view.context.host, "guide")
            self.assertEqual(page.guides_view.quest_detail_view.context.guide_id, TURQUOISE_GUIDE_ID)
            page.deleteLater()
            self.app.processEvents()

    def test_achievement_quest_opens_quests_tab_and_preserves_success_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(ACHIEVEMENTS_TAB))
            self.app.processEvents()
            achievements_view = page.ensure_achievements_view()
            self.assertTrue(achievements_view.select_achievement(TURQUOISE_ACHIEVEMENT_ID))

            linked_quest = next(
                row
                for row in achievements_view.findChildren(AchievementEntityRow)
                if row.entity.entity_type == "quest" and int(row.entity.entity_id) == 1653
            )
            QTest.mouseClick(linked_quest, Qt.LeftButton)
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), QUESTS_TAB)
            self.assertEqual(page.quest_page.selected_quest_id, 1653)
            self.assertEqual(achievements_view.current_achievement_id, TURQUOISE_ACHIEVEMENT_ID)
            guides_view = page.ensure_guides_view()
            self.assertIs(page.quest_page.quest_provider, guides_view.quest_provider)
            self.assertIs(page.quest_page.quest_provider, achievements_view.quest_provider)
            page.deleteLater()
            self.app.processEvents()

    def test_show_quest_from_achievement_redirects_to_quests_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(ACHIEVEMENTS_TAB))
            self.app.processEvents()
            achievements_view = page.ensure_achievements_view()
            self.assertTrue(achievements_view.select_achievement(TURQUOISE_ACHIEVEMENT_ID))
            self.assertTrue(achievements_view.show_quest(1654))
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), QUESTS_TAB)
            self.assertEqual(page.quest_page.selected_quest_id, 1654)
            self.assertEqual(achievements_view.current_achievement_id, TURQUOISE_ACHIEVEMENT_ID)
            page.deleteLater()
            self.app.processEvents()

    def test_guide_quest_prerequisite_opens_quest_tab_and_preserves_guide_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            assert page.guides_view is not None
            page.guides_view.select_guide(TURQUOISE_GUIDE_ID)
            page.guides_view.show_quest_detail(1654)
            self.app.processEvents()

            prerequisite = next(
                button
                for button in page.guides_view.findChildren(AtlasButton)
                if button.text() == "Plongeon et dragon"
            )
            prerequisite.click()
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), QUESTS_TAB)
            assert page.quest_page is not None
            self.assertEqual(page.quest_page.selected_quest_id, 1653)

            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            self.app.processEvents()
            self.assertEqual(page.guides_view.current_guide_id, TURQUOISE_GUIDE_ID)
            self.assertEqual(page.guides_view.current_quest_id, 1654)
            self.assertEqual(page.guides_view.state, page.guides_view.QUEST_DETAIL)
            page.deleteLater()
            self.app.processEvents()

    def test_quest_completion_toggle_is_per_character_and_stays_in_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
            assert guide is not None
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()
            before_done, total, _state = view.guide_progress_tuple(guide)

            line = next(
                child
                for child in view.findChildren(QuestLine)
                if child.step.step_type == "quest" and child.step.entity_id == 1653
            )
            marker = line.findChild(QToolButton, "GuideQuestState")
            assert marker is not None
            self.assertEqual(marker.property("state"), "todo")
            marker.click()
            self.app.processEvents()

            self.assertEqual(view.state, view.GUIDE_OVERVIEW)
            self.assertIsNone(view.current_quest_id)
            self.assertTrue(quest_done(load_quest_progress(view.quest_progress_path), "character:1", 1653))
            after_done, after_total, _state = view.guide_progress_tuple(guide)
            self.assertEqual(after_total, total)
            self.assertEqual(after_done, before_done + 1)

            view.set_character_key("character:2")
            self.app.processEvents()
            self.assertFalse(quest_done(load_quest_progress(view.quest_progress_path), "character:2", 1653))
            line = next(
                child
                for child in view.findChildren(QuestLine)
                if child.step.step_type == "quest" and child.step.entity_id == 1653
            )
            marker = line.findChild(QToolButton, "GuideQuestState")
            assert marker is not None
            self.assertEqual(marker.property("state"), "todo")

            view.set_character_key("character:1")
            self.app.processEvents()
            line = next(
                child
                for child in view.findChildren(QuestLine)
                if child.step.step_type == "quest" and child.step.entity_id == 1653
            )
            marker = line.findChild(QToolButton, "GuideQuestState")
            assert marker is not None
            self.assertEqual(marker.property("state"), "done")
            view.deleteLater()
            self.app.processEvents()

    def test_quest_solution_is_selectable_document_and_click_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.resize(1000, 600)
            view.show()
            view.select_guide(TURQUOISE_GUIDE_ID)
            view.show_quest_detail(1653)
            self.app.processEvents()

            documents = view.findChildren(QLabel, "QuestSolutionDocument")
            self.assertTrue(documents)
            document = documents[0]
            self.assertTrue(document.textInteractionFlags() & Qt.TextSelectableByMouse)
            self.assertFalse(view.findChildren(QToolButton, "QuestObjectiveState"))
            self.assertFalse(hasattr(view, "set_quest_objective_completed"))

            scroll_bar = view.center_scroll.verticalScrollBar()
            scroll_bar.setValue(min(25, scroll_bar.maximum()))
            self.app.processEvents()
            scroll_before = scroll_bar.value()
            splitter_before = view.splitter.sizes()
            quest_before = view.current_quest_id
            progress_before = view.quest_progress_path.read_text(encoding="utf-8")

            QTest.mouseClick(document, Qt.LeftButton, pos=document.rect().center())
            self.app.processEvents()

            self.assertEqual(scroll_bar.value(), scroll_before)
            self.assertEqual(view.splitter.sizes(), splitter_before)
            self.assertEqual(view.current_quest_id, quest_before)
            self.assertEqual(view.quest_progress_path.read_text(encoding="utf-8"), progress_before)
            self.assertFalse(view.quest_detail_view.done_button.isHidden())
            view.deleteLater()
            self.app.processEvents()

    def test_quests_tab_solution_click_preserves_scroll_layout_and_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.resize(1100, 650)
            page.show()
            assert page.quest_page is not None
            quest_page = page.quest_page
            quest_page.select_quest(1653, persist=False)
            self.app.processEvents()

            document = quest_page.findChildren(QLabel, "QuestSolutionDocument")[0]
            self.assertTrue(document.textInteractionFlags() & Qt.TextSelectableByMouse)
            self.assertFalse(quest_page.findChildren(QToolButton, "QuestObjectiveState"))
            self.assertEqual(len(quest_page.findChildren(QToolButton, "QuestGlobalDoneButton")), 1)

            scroll_bar = quest_page.center_scroll.verticalScrollBar()
            scroll_bar.setValue(min(25, scroll_bar.maximum()))
            self.app.processEvents()
            before = (scroll_bar.value(), quest_page.splitter.sizes(), quest_page.selected_quest_id)
            QTest.mouseClick(document, Qt.LeftButton, pos=document.rect().center())
            self.app.processEvents()
            after = (scroll_bar.value(), quest_page.splitter.sizes(), quest_page.selected_quest_id)
            self.assertEqual(after, before)
            page.deleteLater()
            self.app.processEvents()

    def test_solution_images_decode_after_document_render(self):
        image_path = DATA_DIR / "encyclopedia" / "images" / "quests" / "1653" / "step_01.webp"
        self.assertTrue(image_path.exists())
        image = SolutionImageLabel(str(image_path))
        loaded = QSignalSpy(image.imageLoaded)
        self.assertTrue(image.source.isNull())
        image.start_image_load()
        image._image_load_future.result(timeout=3)
        self.app.processEvents()
        self.assertEqual(loaded.count(), 1)
        self.assertFalse(image.source.isNull())
        image.deleteLater()
        self.app.processEvents()

    def test_steps_and_prerequisites_can_collapse_without_disappearing(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.resize(900, 560)
            view.show()
            view.select_guide("alignement_bonta")
            self.app.processEvents()
            labels = [label.text() for label in view.findChildren(QLabel)]
            self.assertTrue(any(normalize_text(text) == "etapes" for text in labels))
            self.assertNotIn("PARTIES", labels)

            collapse_button = view.findChild(QToolButton, "GuideStepsCollapseButton")
            self.assertIsNotNone(collapse_button)
            assert collapse_button is not None
            self.assertFalse(collapse_button.isHidden())
            collapse_button.click()
            self.app.processEvents()
            self.assertTrue(view.steps_collapsed)
            self.assertTrue(view.findChildren(GuideCollapsedStepsRail))
            self.assertEqual(view.splitter.handleWidth(), 0)
            self.assertLessEqual(view.left_panel.maximumWidth(), 44)

            rail = view.findChild(GuideCollapsedStepsRail)
            self.assertIsNotNone(rail)
            assert rail is not None
            expand_button = rail.findChild(QToolButton, "GuideStepsCollapseButton")
            self.assertIsNotNone(expand_button)
            assert expand_button is not None
            self.assertFalse(expand_button.isHidden())
            expand_button.click()
            self.app.processEvents()
            self.assertFalse(view.steps_collapsed)
            self.assertEqual(view.splitter.handleWidth(), 0)
            self.assertGreaterEqual(view.left_panel.minimumWidth(), 170)

            view.select_guide(TURQUOISE_GUIDE_ID)
            self.assertTrue(view.show_quest_detail(1654))
            self.app.processEvents()
            section = next(iter(view.findChildren(CollapsibleInfoSection)))
            section.set_expanded(True)
            self.assertFalse(section.body.isHidden())
            section.set_expanded(False)
            self.assertTrue(section.body.isHidden())
            section.set_expanded(True)
            self.assertFalse(section.body.isHidden())
            view.deleteLater()
            self.app.processEvents()

    def test_dofus_guide_overview_uses_quests_and_info_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()

            labels = [label.text() for label in view.findChildren(QLabel)]
            breadcrumb_labels = [label.text() for label in view.breadcrumb.findChildren(QLabel)]

            self.assertTrue(view.left_panel.isHidden())
            self.assertEqual(view.left_panel.maximumWidth(), 0)
            self.assertEqual(view.splitter.handleWidth(), 0)
            self.assertFalse(any(button.text() == "Masquer" for button in view.findChildren(QToolButton, "GuideStepsCollapseButton")))
            self.assertFalse(any(normalize_text(text) == "etapes" for text in labels))
            self.assertEqual(view.detail_header_title.text(), "Dofus Turquoise")
            self.assertEqual(view.detail_header_meta.text(), "Niveau 160 à 200")
            self.assertTrue(any(button.text() == "Guides" for button in view.breadcrumb.findChildren(AtlasButton)))
            self.assertNotIn("Dofus", breadcrumb_labels)
            self.assertEqual(breadcrumb_labels.count(">"), 1)
            view.deleteLater()
            self.app.processEvents()

    def test_home_dofus_grid_renders_only_real_guides(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.resize(900, 560)
            view.show()
            self.app.processEvents()

            expected_ids = {guide.id for guide in self.guides if guide.category == "dofus"}
            cards = [card for card in view.findChildren(GuideHomeCard) if card.variant == "dofus"]
            alignment_cards = [card for card in view.findChildren(GuideHomeCard) if card.variant == "alignment"]
            labels = [label.text() for card in cards for label in card.findChildren(QLabel)]

            self.assertEqual({card.guide.id for card in cards}, expected_ids)
            self.assertFalse(view.findChildren(QScrollArea, "GuidesHomeScroll"))
            self.assertEqual(len(view.findChildren(QFrame, "GuidesHomeProgressionColumn")), 1)
            self.assertEqual(len(view.findChildren(QFrame, "GuidesHomeSubCategory")), 2)
            self.assertTrue(view.findChildren(DofusGuideGrid))
            self.assertFalse(any("a_venir" in normalize_text(text) or "placeholder" in normalize_text(text) for text in labels))
            self.assertTrue(all(card.findChild(QProgressBar, "GuideDofusHomeBar") is not None for card in cards))
            self.assertEqual({card.guide.id for card in alignment_cards}, {"alignement_bonta", "alignement_brakmar"})
            if len(alignment_cards) == 2:
                self.assertFalse(alignment_cards[0].geometry().intersects(alignment_cards[1].geometry()))
            view.deleteLater()
            self.app.processEvents()

    def test_dofus_grid_reflows_inside_viewport_width(self):
        dofus_guides = [guide for guide in self.guides if guide.category == "dofus"]
        cards = [GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo")) for guide in dofus_guides[:12]]
        grid = DofusGuideGrid(cards)
        grid.show()
        self.app.processEvents()

        columns_seen: list[int] = []
        for width in (640, 520, 420, 300):
            grid.resize(width, 260)
            self.app.processEvents()
            grid.reflow_now()
            self.app.processEvents()

            columns_seen.append(grid.current_columns)
            self.assertEqual(grid.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertEqual(grid.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(grid.current_card_width, DOFUS_CARD_MAX_WIDTH)
            self.assertTrue(all(card.height() == DOFUS_CARD_HEIGHT for card in cards))
            card_rects = [card.geometry() for card in cards if card.isVisible()]
            for index, rect in enumerate(card_rects):
                for other in card_rects[index + 1 :]:
                    self.assertFalse(rect.intersects(other))
            for card in cards:
                count = card.findChild(QLabel, "GuideDofusProgress")
                bar = card.findChild(QProgressBar, "GuideDofusHomeBar")
                assert count is not None
                assert bar is not None
                self.assertLessEqual(count.geometry().bottom(), card.rect().bottom())
                self.assertLessEqual(bar.geometry().bottom(), card.rect().bottom())
            visible_right_edges = [card.geometry().right() for card in cards if card.isVisible()]
            if visible_right_edges:
                self.assertLess(max(visible_right_edges), grid.viewport().width())

        self.assertGreater(columns_seen[0], columns_seen[-1])
        self.assertEqual(columns_seen, sorted(columns_seen, reverse=True))
        grid.deleteLater()
        self.app.processEvents()

    def test_guide_to_achievement_opens_contextual_achievement_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            assert page.guides_view is not None
            page.guides_view.select_guide(TURQUOISE_GUIDE_ID)
            self.app.processEvents()

            page.navigate_to_entity("achievement", TURQUOISE_ACHIEVEMENT_ID)
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            self.assertFalse(hasattr(page, "achievements_view"))
            self.assertEqual(page.guides_view.current_guide_id, TURQUOISE_GUIDE_ID)
            page.deleteLater()
            self.app.processEvents()

    def test_contextual_guide_navigation_does_not_switch_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.tabs.setCurrentIndex(page.tab_labels().index(GUIDES_TAB))
            self.app.processEvents()

            page.navigate_to_entity(
                "quest",
                1653,
                source="guide",
                guide_id=TURQUOISE_GUIDE_ID,
                guide_title="Dofus Turquoise",
            )
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            self.assertEqual(page.guides_view.current_quest_id, 1653)
            self.assertEqual(page.guides_view.quest_detail_view.current_quest_id, 1653)
            page.deleteLater()
            self.app.processEvents()

    def test_quest_to_associated_guide_opens_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            assert page.quest_page is not None
            page.quest_page.select_quest(1653)
            self.app.processEvents()

            self.assertIn("Guides associés", page.quest_page.detail.toHtml())
            page.quest_page.on_detail_link_clicked(QUrl(f"atlas-guide:{TURQUOISE_GUIDE_ID}"))
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            assert page.guides_view is not None
            self.assertEqual(page.guides_view.current_guide_id, TURQUOISE_GUIDE_ID)
            page.deleteLater()
            self.app.processEvents()

    def test_achievement_navigation_opens_associated_guide_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self.make_page(Path(tmp))
            page.navigate_to_entity("achievement", TURQUOISE_ACHIEVEMENT_ID)
            self.app.processEvents()

            self.assertEqual(page.current_tab_label(), GUIDES_TAB)
            assert page.guides_view is not None
            self.assertEqual(page.guides_view.current_guide_id, TURQUOISE_GUIDE_ID)
            self.assertFalse(hasattr(page, "achievements_view"))
            page.deleteLater()
            self.app.processEvents()

    def test_guides_view_instantiates_offscreen(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            self.app.processEvents()

            self.assertGreater(view.result_model.rowCount(), 0)
            self.assertFalse(hasattr(view, "character_combo"))
            self.assertFalse(view.findChildren(QSpinBox))
            view.deleteLater()
            self.app.processEvents()

    def test_turquoise_dofus_item_and_image_are_resolved(self):
        guide = self.guide_provider.get_by_id(TURQUOISE_GUIDE_ID)
        assert guide is not None

        self.assertEqual(guide.reward_item_id, 739)
        self.assertEqual(guide.illustration_item_id, 739)
        self.assertIsNotNone(guide.reward_item)
        assert guide.reward_item is not None
        self.assertEqual(guide.reward_item.name, "Dofus Turquoise")
        self.assertEqual(guide.reward_item.level, 160)
        self.assertTrue(Path(guide.image_path).exists())
        self.assertNotIn("logo", Path(guide.image_path).name.lower())

    def test_provider_does_not_use_network(self):
        original_socket = socket.socket

        def forbidden_socket(*_args, **_kwargs):
            raise AssertionError("network call forbidden")

        socket.socket = forbidden_socket
        try:
            provider = GuideProvider(
                quest_provider=self.quest_provider,
                achievement_provider=self.achievement_provider,
            )
            self.assertGreater(len(provider.load_all()), 0)
        finally:
            socket.socket = original_socket

    def test_related_data_cache_reuses_providers_and_graph_for_the_session_catalog(self):
        catalog = self.quest_provider.get_catalog()
        count_before = related_data_build_count()
        first = build_related_encyclopedia_data(catalog)
        count_after_first = related_data_build_count()
        second = build_related_encyclopedia_data(catalog)

        self.assertIs(second, first)
        self.assertIs(second.guide_provider, first.guide_provider)
        self.assertIs(second.quest_graph, first.quest_graph)
        self.assertIn(count_after_first - count_before, {0, 1})
        self.assertEqual(related_data_build_count(), count_after_first)

    def test_required_item_text_copies_and_only_image_toggles_line(self):
        toggles: list[bool] = []
        item = DisplayItem(item_id=42, name="Poil de Kanigrou", quantity=10)
        row = item_row(item, checked=False, on_toggle=toggles.append)
        row.resize(420, 34)
        row.show()
        self.app.processEvents()
        image = row.findChild(QToolButton, "GuideItemIcon")
        name = row.findChild(AtlasButton, "GuideItemNameButton")
        quantity = row.findChild(QLabel, "GuideItemQuantity")
        self.assertIsNotNone(image)
        self.assertIsNotNone(name)
        self.assertIsNotNone(quantity)
        self.assertIsNone(row.findChild(QCheckBox))
        assert image is not None and name is not None and quantity is not None
        self.assertLessEqual(name.geometry().left() - image.geometry().right() - 1, 3)
        self.assertLessEqual(quantity.geometry().left() - name.geometry().right() - 1, 3)

        name.click()
        self.app.processEvents()
        self.assertEqual(QApplication.clipboard().text(), "Poil de Kanigrou")
        self.assertEqual(toggles, [])
        self.assertEqual(row.property("state"), "todo")

        image.click()
        self.app.processEvents()
        self.assertEqual(toggles, [True])
        self.assertEqual(row.property("state"), "done")
        row.deleteLater()

    def test_guide_quest_info_uses_one_shared_header_and_context_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.assertTrue(view.show_quest_detail(1653))
            self.app.processEvents()

            labels = [normalize_text(label.text()) for label in view.findChildren(QLabel)]
            minimum_levels = [text for text in labels if text.startswith("niveau_minimum_")]
            self.assertEqual(len(minimum_levels), 1)
            self.assertEqual(view.quest_detail_view.current_quest_id, 1653)
            self.assertFalse(view.quest_detail_view.done_button.isHidden())
            view.deleteLater()
            self.app.processEvents()

    def test_reliable_navigation_uses_guide_order_and_never_invents_neighbors(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.assertTrue(view.show_quest_detail(1653))
            self.app.processEvents()

            previous_id, next_id = view.graph.reliable_neighbors(1653)
            previous_buttons = view.findChildren(AtlasButton, "QuestPreviousButton")
            next_buttons = view.findChildren(AtlasButton, "QuestNextButton")
            self.assertEqual(len(previous_buttons), int(previous_id is not None))
            self.assertEqual(len(next_buttons), int(next_id is not None))
            self.assertIsNotNone(next_id)
            assert next_id is not None
            next_buttons[0].click()
            self.app.processEvents()
            self.assertEqual(view.current_quest_id, next_id)

            no_relation_id = next(
                quest.id
                for quest in view.quest_catalog.quests
                if view.graph.reliable_neighbors(quest.id) == (None, None)
            )
            self.assertEqual(view.graph.reliable_neighbors(no_relation_id), (None, None))
            view.deleteLater()
            self.app.processEvents()

    def test_cawotte_final_obtention_is_documented_without_fake_completion_control(self):
        guide = self.guide_provider.get_by_id("dofus_cawotte")
        assert guide is not None
        final_step = next(step for step in guide.steps if step.id == "dofus_cawotte_obtention_finale")
        final_line = QuestLine(final_step)
        self.assertEqual(final_step.step_type, "info")
        self.assertIn("Gawdien du Dofus", final_step.content)
        self.assertTrue(any("Gawdien du Dofus" in label.text() for label in final_line.findChildren(QLabel)))
        self.assertIsNone(final_line.findChild(QToolButton, "GuideQuestState"))
        final_line.deleteLater()
        self.app.processEvents()

    def test_quest_activity_section_is_named_info_quete(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide(TURQUOISE_GUIDE_ID)
            self.assertTrue(view.show_quest_detail(1653))
            self.app.processEvents()
            labels = {normalize_text(label.text()) for label in view.findChildren(QLabel)}
            self.assertIn("info_quete", labels)
            self.assertNotIn("preparation", labels)
            self.assertNotIn("combat_activites", labels)
            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
