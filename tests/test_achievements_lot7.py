from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel

from app.modules.encyclopedia.achievement_catalog_policy import (
    QUEST_GENERAL_PINNED_ACHIEVEMENT_IDS,
    QUEST_GENERAL_SUBCATEGORY_ID,
    QUEST_WORLD_ACHIEVEMENT_IDS,
    QUEST_WORLD_SUBCATEGORY_ID,
)
from app.modules.encyclopedia.providers import AchievementProvider
from app.modules.encyclopedia.services import AchievementProgressService, QuestProgressService
from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS
from app.modules.encyclopedia.views.achievements_view import AchievementsView
from app.modules.encyclopedia.widgets.achievement_detail_widget import AchievementDetailWidget
from app.modules.encyclopedia.widgets.achievement_entity_section import AchievementEntityRow, AchievementEntitySection
from app.modules.encyclopedia.widgets.achievement_objective_widget import AchievementObjectiveWidget
from app.modules.encyclopedia.models.entity_ref import EntityRef


class AchievementLot7ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = AchievementProvider()
        cls.achievements = cls.provider.load_all()

    def test_only_validated_categories_are_retained_in_game_order(self):
        categories = self.provider.get_retained_categories()
        self.assertEqual([category.id for category in categories], [8, 3, 25, 9])
        self.assertEqual([category.name for category in categories], ["Quêtes", "Donjons", "Monstres", "Événements"])
        # The canonical local snapshot contains exactly the four audited
        # categories below: 292 + 743 + 228 + 149 achievements.
        self.assertEqual(len(self.provider.load_retained()), 1412)

    def test_achievement_order_uses_category_membership_sequence(self):
        for category in self.provider.get_categories():
            if category.id in {QUEST_GENERAL_SUBCATEGORY_ID, QUEST_WORLD_SUBCATEGORY_ID}:
                continue
            if not category.achievement_ids:
                continue
            loaded_ids = [achievement.id for achievement in self.provider.get_by_category(category.id)]
            declared_present = [achievement_id for achievement_id in category.achievement_ids if achievement_id in loaded_ids]
            self.assertEqual(loaded_ids, declared_present)

    def test_general_starts_with_premier_temps_then_second_temps(self):
        loaded_ids = [
            achievement.id
            for achievement in self.provider.get_by_category(QUEST_GENERAL_SUBCATEGORY_ID)
        ]
        self.assertEqual(loaded_ids[:2], list(QUEST_GENERAL_PINNED_ACHIEVEMENT_IDS))

    def test_world_quests_follow_verified_current_order(self):
        loaded_ids = [
            achievement.id
            for achievement in self.provider.get_by_category(QUEST_WORLD_SUBCATEGORY_ID)
        ]
        expected = [achievement_id for achievement_id in QUEST_WORLD_ACHIEVEMENT_IDS if achievement_id in loaded_ids]
        self.assertEqual(loaded_ids[: len(expected)], expected)

    def test_objective_order_uses_achievement_objective_sequence(self):
        for achievement in self.provider.load_retained():
            loaded_ids = [objective.id for objective in achievement.objectives]
            declared_present = [objective_id for objective_id in achievement.objective_ids if objective_id in loaded_ids]
            self.assertEqual(loaded_ids, declared_present)

    def test_meta_achievement_expands_local_quest_links(self):
        achievement = self.provider.get_by_id(8520)
        self.assertIsNotNone(achievement)
        assert achievement is not None
        self.assertEqual([ref.entity_id for ref in achievement.linked_achievements], [8518, 8519])
        self.assertEqual([ref.entity_id for ref in achievement.resolved_linked_quests], [2511, 2545, 2502])


class AchievementLot7QuestSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.provider = AchievementProvider()

    @staticmethod
    def fake_alignment_guides() -> SimpleNamespace:
        bonta_steps = tuple(SimpleNamespace(step_type="quest", entity_id=50000 + index) for index in range(1, 101))
        brakmar_steps = tuple(SimpleNamespace(step_type="quest", entity_id=60000 + index) for index in range(1, 101))
        guides = {
            "alignement_bonta": SimpleNamespace(required_steps=bonta_steps),
            "alignement_brakmar": SimpleNamespace(required_steps=brakmar_steps),
        }
        return SimpleNamespace(get_by_id=lambda guide_id: guides.get(guide_id))

    def test_en_quete_thresholds_follow_shared_completed_quest_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quest_progress = QuestProgressService(root / "quest_progress.json")
            progress = AchievementProgressService(root / "achievement_progress.json")
            for quest_id in range(1, 101):
                quest_progress.set_quest_completed("character:1", quest_id, True)

            progress.sync_from_quest_progress("character:1", self.provider, quest_progress)

            self.assertTrue(progress.is_achievement_completed("character:1", 813))
            self.assertTrue(progress.is_achievement_completed("character:1", 815))
            self.assertTrue(progress.is_achievement_completed("character:1", 816))
            self.assertFalse(progress.is_achievement_completed("character:1", 817))

            achievement = self.provider.get_by_id(816)
            assert achievement is not None
            detail = AchievementDetailWidget(achievement, progress, "character:1")
            self.assertFalse(detail.findChildren(AchievementObjectiveWidget))
            self.assertNotIn("Objectifs", [label.text() for label in detail.findChildren(QLabel)])
            self.assertEqual(detail._progress_total, 1)
            detail.deleteLater()
            self.app.processEvents()

    def test_direct_quest_progress_completes_quest_successes_and_meta_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quest_progress = QuestProgressService(root / "quest_progress.json")
            progress = AchievementProgressService(root / "achievement_progress.json")
            for quest_id in (2511, 2545, 2502):
                quest_progress.set_quest_completed("character:1", quest_id, True)

            progress.sync_from_quest_progress("character:1", self.provider, quest_progress)

            self.assertTrue(progress.is_achievement_completed("character:1", 8518))
            self.assertTrue(progress.is_achievement_completed("character:1", 8519))
            self.assertTrue(progress.is_achievement_completed("character:1", 8520))

    def test_alignment_quest_count_drives_only_one_trackable_objective(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quest_progress = QuestProgressService(root / "quest_progress.json")
            progress = AchievementProgressService(root / "achievement_progress.json")
            for quest_id in range(50001, 50011):
                quest_progress.set_quest_completed("character:1", quest_id, True)

            progress.sync_from_quest_progress(
                "character:1",
                self.provider,
                quest_progress,
                self.fake_alignment_guides(),
            )

            self.assertTrue(progress.is_achievement_completed("character:1", 1203))
            self.assertFalse(progress.is_achievement_completed("character:1", 1204))
            achievement = self.provider.get_by_id(1203)
            assert achievement is not None
            detail = AchievementDetailWidget(achievement, progress, "character:1")
            self.assertEqual(detail._progress_total, 1)
            self.assertEqual(detail._progress_done, 1)
            detail.deleteLater()
            self.app.processEvents()

    def test_auto_completed_success_is_greyed_in_catalogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character_key = "character:105"
            quest_progress = QuestProgressService(root / "quest_progress.json")
            progress = AchievementProgressService(root / "achievement_progress.json")
            for quest_id in range(1, 101):
                quest_progress.set_quest_completed(character_key, quest_id, True)

            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=progress,
                character_key=character_key,
                quest_progress_service=quest_progress,
            )
            view.show()
            while view._achievement_pending_rows:
                view._render_next_achievement_batch()
            self.assertTrue(view.select_achievement(816))
            while view._achievement_pending_rows:
                view._render_next_achievement_batch()
            item = next(
                (
                    view.list_widget.item(row)
                    for row in range(view.list_widget.count())
                    if int(view.list_widget.item(row).data(Qt.UserRole)) == 816
                ),
                None,
            )
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(int(item.data(Qt.UserRole)), 816)
            self.assertTrue(item.data(Qt.UserRole + 2))
            view.deleteLater()
            self.app.processEvents()


class AchievementLot7AlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.provider = AchievementProvider()

    def test_alignment_choice_is_persisted_per_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            service = AchievementProgressService(path)
            service.set_alignment_order_choice("character:1", "bonta", "Ordre du Cœur Vaillant")

            reloaded = AchievementProgressService(path)
            self.assertEqual(
                reloaded.alignment_order_choice("character:1"),
                ("bonta", "Ordre du Cœur Vaillant"),
            )
            self.assertIsNone(reloaded.alignment_order_choice("character:2"))

    def test_view_uses_exactly_the_selected_five_quest_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character_key = "character:104"
            progress = AchievementProgressService(root / "achievement_progress.json")
            quest_progress = QuestProgressService(root / "quest_progress.json")
            progress.set_alignment_order_choice(character_key, "brakmar", "Ordre de l'Œil Putride")
            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=progress,
                character_key=character_key,
                quest_progress_service=quest_progress,
            )
            self.assertTrue(view.select_achievement(1213))
            achievement = self.provider.get_by_id(1213)
            assert achievement is not None
            self.assertEqual(
                [ref.entity_id for ref in view.effective_quest_refs(achievement)],
                [ORDER_QUEST_IDS["brakmar"]["Ordre de l'Œil Putride"][0]],
            )
            combo = view.findChild(QComboBox, "AchievementAlignmentOrderCombo")
            self.assertIsNotNone(combo)
            order_links = [
                row
                for row in view.findChildren(AchievementEntityRow)
                if "Rang " in row.entity.label
            ]
            self.assertEqual(len(order_links), 5)
            self.assertEqual(
                [int(row.entity.entity_id) for row in order_links],
                list(ORDER_QUEST_IDS["brakmar"]["Ordre de l'Œil Putride"]),
            )
            view.deleteLater()
            self.app.processEvents()

    def test_selected_order_rank_progress_comes_from_quest_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character_key = "character:103"
            progress = AchievementProgressService(root / "achievement_progress.json")
            quest_progress = QuestProgressService(root / "quest_progress.json")
            side = "bonta"
            order_name = "Ordre du Cœur Vaillant"
            selected_quest_id = int(ORDER_QUEST_IDS[side][order_name][0])
            progress.set_alignment_order_choice(character_key, side, order_name)
            quest_progress.set_quest_completed(character_key, selected_quest_id, True)

            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=progress,
                character_key=character_key,
                quest_progress_service=quest_progress,
            )
            self.assertTrue(view.select_achievement(1213))
            achievement = self.provider.get_by_id(1213)
            assert achievement is not None
            self.assertEqual(
                [ref.entity_id for ref in view.effective_quest_refs(achievement)],
                [selected_quest_id],
            )
            # Quest achievements show their actual quest row instead of a duplicate
            # objective row. The five-rank alignment panel still reflects progress.
            self.assertFalse(view.findChildren(AchievementObjectiveWidget))
            rank_rows = [
                row
                for row in view.findChildren(AchievementEntityRow)
                if int(row.entity.entity_id) == selected_quest_id
            ]
            self.assertTrue(rank_rows)
            self.assertTrue(any(row.entity.label.startswith("✓ Rang 1") for row in rank_rows))
            view.deleteLater()
            self.app.processEvents()

    def test_alignment_choice_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            character_key = "character:101"
            progress = AchievementProgressService(root / "achievement_progress.json")
            progress.set_alignment_order_choice(character_key, "bonta", "Ordre du Cœur Vaillant")
            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=progress,
                character_key=character_key,
                quest_progress_service=QuestProgressService(root / "quest_progress.json"),
            )
            self.assertTrue(view.select_achievement(1213))
            combo = view.findChild(QComboBox, "AchievementAlignmentOrderCombo")
            self.assertIsNotNone(combo)
            assert combo is not None
            combo.setCurrentIndex(0)
            self.app.processEvents()
            self.assertIsNone(progress.alignment_order_choice(character_key))
            view.deleteLater()
            self.app.processEvents()

    def test_shared_entity_section_is_generic_for_lots_8_and_9(self):
        activated: list[tuple[str, int]] = []
        section = AchievementEntitySection(
            "Monstres",
            (EntityRef("monster", 42, "Monstre test"),),
            navigate_callback=lambda entity_type, entity_id: activated.append((entity_type, entity_id)) or True,
        )
        rows = section.findChildren(AchievementEntityRow)
        self.assertEqual(len(rows), 1)
        QTest.mouseClick(rows[0], Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual(activated, [("monster", 42)])
        section.deleteLater()
        self.app.processEvents()


    def test_dungeon_detail_hides_level_criteria_and_duplicate_entity_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AchievementProgressService(Path(tmp) / "achievement_progress.json")
            achievement = self.provider.get_by_id(33)
            self.assertIsNotNone(achievement)
            assert achievement is not None
            detail = AchievementDetailWidget(
                achievement,
                service,
                "character:1",
                linked_monsters=achievement.resolved_linked_monsters,
                linked_dungeons=achievement.resolved_linked_dungeons,
            )
            objectives = detail.findChildren(AchievementObjectiveWidget)
            self.assertEqual(len(objectives), 1)
            self.assertEqual(objectives[0].objective.objective_type, "Monstre")
            headings = [label.text() for label in detail.findChildren(QLabel)]
            self.assertNotIn("Donjons", headings)
            self.assertNotIn("Monstres", headings)
            self.assertFalse(any("Niveau 10" == text for text in headings))
            detail.deleteLater()
            self.app.processEvents()

    def test_vigilant_and_eyes_have_no_useless_objective_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AchievementProgressService(Path(tmp) / "achievement_progress.json")
            for achievement_id in (125, 126):
                achievement = self.provider.get_by_id(achievement_id)
                self.assertIsNotNone(achievement)
                assert achievement is not None
                detail = AchievementDetailWidget(achievement, service, "character:1")
                self.assertFalse(detail.findChildren(AchievementObjectiveWidget))
                self.assertNotIn("Objectifs", [label.text() for label in detail.findChildren(QLabel)])
                detail.deleteLater()
            self.app.processEvents()

    def test_quest_success_uses_single_quest_section_instead_of_objectives(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AchievementProgressService(Path(tmp) / "achievement_progress.json")
            achievement = next(
                item
                for item in self.provider.load_retained()
                if item.category_name == "Quêtes" and item.resolved_linked_quests
            )
            detail = AchievementDetailWidget(
                achievement,
                service,
                "character:1",
                linked_quests=achievement.resolved_linked_quests,
            )
            labels = [label.text() for label in detail.findChildren(QLabel)]
            self.assertNotIn("Objectifs", labels)
            self.assertEqual(labels.count("Quêtes"), 1)
            self.assertEqual(
                len(detail.findChildren(AchievementEntityRow)),
                len(achievement.resolved_linked_quests),
            )
            detail.deleteLater()
            self.app.processEvents()

    def test_quest_link_delegates_to_the_shared_quests_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[tuple[str, int, dict[str, object]]] = []
            achievement = next(
                item
                for item in self.provider.load_retained()
                if item.category_name == "Quêtes" and item.resolved_linked_quests
            )
            quest_id = int(achievement.resolved_linked_quests[0].entity_id)
            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=AchievementProgressService(Path(tmp) / "achievement_progress.json"),
                quest_progress_service=QuestProgressService(Path(tmp) / "quest_progress.json"),
                navigate_callback=lambda entity_type, entity_id, **context: calls.append(
                    (str(entity_type), int(entity_id), dict(context))
                ) or True,
            )
            view.current_achievement_id = achievement.id
            self.assertTrue(view.open_linked_entity("quest", quest_id))
            self.assertEqual(
                calls,
                [("quest", quest_id, {"source": "achievement_link", "achievement_id": achievement.id})],
            )
            view.deleteLater()
            self.app.processEvents()

    def test_completed_success_is_marked_as_completed_in_catalogue_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            character_key = "character:102"
            progress = AchievementProgressService(Path(tmp) / "achievement_progress.json")
            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=progress,
                character_key=character_key,
                quest_progress_service=QuestProgressService(Path(tmp) / "quest_progress.json"),
            )
            view.show()
            while view._achievement_pending_rows:
                view._render_next_achievement_batch()
            item = view.list_widget.item(0)
            self.assertIsNotNone(item)
            assert item is not None
            achievement_id = int(item.data(Qt.UserRole))
            progress.set_achievement_completed(character_key, achievement_id, True)
            view.refresh_completion_styles()
            self.assertTrue(item.data(Qt.UserRole + 2))
            progress.set_achievement_completed(character_key, achievement_id, False)
            view.refresh_completion_styles()
            self.assertFalse(item.data(Qt.UserRole + 2))
            view.deleteLater()
            self.app.processEvents()

    def test_achievement_click_toggles_integrated_right_detail_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=AchievementProgressService(root / "achievement_progress.json"),
                quest_progress_service=QuestProgressService(root / "quest_progress.json"),
            )
            view.resize(900, 650)
            view.show()
            self.app.processEvents()
            item = view.list_widget.item(0)
            self.assertIsNotNone(item)
            assert item is not None

            self.assertEqual(view.splitter.indexOf(view.detail_stack), 2)
            self.assertFalse(view._detail_open)

            view.on_achievement_clicked(item)
            self.app.processEvents()
            self.assertTrue(view._detail_open)
            self.assertTrue(view.findChildren(AchievementDetailWidget))

            view.on_achievement_clicked(item)
            self.app.processEvents()
            self.assertFalse(view._detail_open)
            self.assertFalse(view.findChildren(AchievementDetailWidget))

            view.on_achievement_clicked(item)
            self.app.processEvents()
            self.assertTrue(view._detail_open)
            self.assertEqual(view.splitter.count(), 3)
            view.deleteLater()
            self.app.processEvents()

    def test_excluded_achievement_cannot_be_reintroduced_by_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            view = AchievementsView(
                lambda _text: None,
                provider=self.provider,
                progress_service=AchievementProgressService(root / "achievement_progress.json"),
                quest_progress_service=QuestProgressService(root / "quest_progress.json"),
            )
            self.assertFalse(view.select_achievement(3))
            self.assertEqual(
                [view.category_tree.topLevelItem(index).data(0, Qt.UserRole) for index in range(view.category_tree.topLevelItemCount())],
                [8, 3, 25, 9],
            )
            view.resize(900, 650)
            view.show()
            self.app.processEvents()
            self.assertEqual(view.width(), 900)
            self.assertEqual(view.category_tree.horizontalScrollBar().maximum(), 0)
            self.assertEqual(view.list_widget.horizontalScrollBar().maximum(), 0)
            self.assertEqual(view.detail_scroll.horizontalScrollBar().maximum(), 0)
            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
