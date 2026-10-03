from __future__ import annotations

import copy
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
)

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, GuideProgressService
from app.modules.encyclopedia.views.deferred_achievement_guides_view import DeferredAchievementGuidesView
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualCard,
    SharedGuideManualView,
)


class LanyelSharedManualUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        cls.achievement_provider.load_all()
        cls.guide_provider = GuideProvider(
            quest_provider=cls.quest_provider,
            achievement_provider=cls.achievement_provider,
        )
        cls.guide_provider.load_all()

    def _view(self, root: Path) -> DeferredAchievementGuidesView:
        quest_progress = root / "quest_progress.json"
        achievement_progress = root / "achievement_progress.json"
        guide_progress = root / "guide_progress.json"
        for path in (quest_progress, achievement_progress, guide_progress):
            path.write_text("{}", encoding="utf-8")
        view = DeferredAchievementGuidesView(
            lambda _text: None,
            provider=self.guide_provider,
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
            achievement_progress_service=AchievementProgressService(achievement_progress),
            guide_progress_service=GuideProgressService(guide_progress),
            quest_progress_path=quest_progress,
        )
        view.set_character_key("character:1")
        return view

    @staticmethod
    def _layout_widget_names(frame: QFrame) -> list[str]:
        layout = frame.layout()
        assert layout is not None
        result: list[str] = []
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is not None:
                result.append(widget.objectName())
        return result

    def test_lanyel_opens_same_manual_roadbook_renderer_as_guide_succes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))

            self.assertTrue(view.select_guide("dofus_sylvestre"))
            self.app.processEvents()
            lanyel_view = view.stack.currentWidget()
            self.assertIsInstance(lanyel_view, SharedGuideManualView)
            self.assertEqual(view.current_guide_id, "dofus_sylvestre")
            service = view._catalog_manual_services["dofus_sylvestre"]
            self.assertEqual(service.guide_id, "dofus_sylvestre")
            self.assertEqual(service.guide_title, "Lanyel Sylvestre")
            self.assertEqual(service.manual_audit_data["quest_count"], 198)
            self.assertEqual(service.manual_audit_data["route_model"], "map_segments")
            self.assertGreater(len(service.cards), 0)
            self.assertTrue(all(card.get("manual_quest_ids") for card in service.cards))
            self.assertTrue(any(card.get("manual_route_position") for card in service.cards))
            self.assertTrue(
                any(
                    service.manual_sections_for_card("character:1", card)["now"]
                    for card in service.cards
                )
            )

            # A road-book is not one card per quest: at least one quest must span
            # several route positions (and equal consecutive positions may merge).
            occurrences = Counter(
                int(quest_id)
                for card in service.cards
                for quest_id in card.get("manual_quest_ids", ())
            )
            self.assertTrue(any(count > 1 for count in occurrences.values()))
            self.assertGreaterEqual(
                service.manual_audit_data["raw_segment_count"],
                service.manual_audit_data["card_count"],
            )

            self.assertTrue(view.select_guide("guide_complet"))
            self.app.processEvents()
            success_view = view.stack.currentWidget()
            self.assertIsInstance(success_view, SharedGuideManualView)
            self.assertIsNot(lanyel_view, success_view)

            view.deleteLater()
            self.app.processEvents()

    def test_prepare_rows_share_one_red_parent_instead_of_red_row_tiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            service = view._catalog_manual_services["dofus_sylvestre"]
            source = copy.deepcopy(service.cards[0])
            source["manual_sections"] = copy.deepcopy(source.get("manual_sections") or {})
            source["manual_sections"]["prepare"] = [
                {"kind": "warning", "position": "", "text": "Prépare le premier objet."},
                {"kind": "warning", "position": "", "text": "Prépare le second objet."},
            ]

            card = SharedGuideManualCard(service, "character:1", source, 0)
            self.app.processEvents()
            parent = card.findChild(QFrame, "GuideManualWarningSection")
            self.assertIsNotNone(parent)
            lines = parent.findChildren(QLabel, "GuideManualLine")
            self.assertEqual(len(lines), 2)
            self.assertFalse(parent.findChildren(QLabel, "GuideManualWarning"))

            card.deleteLater()
            view.deleteLater()
            self.app.processEvents()

    def test_location_heading_is_removed_and_positions_stay_in_route_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            service = view._catalog_manual_services["dofus_sylvestre"]
            source = copy.deepcopy(service.cards[0])
            source["manual_title"] = "Village d’Amakna"
            source["zone"] = "Village d’Amakna"
            source["subzone"] = "Village d’Amakna"
            source["destination"] = "[1,2] — Village d’Amakna"

            card = SharedGuideManualCard(service, "character:1", source, 0)
            self.app.processEvents()
            self.assertIsNone(card.findChild(QLabel, "GuideManualLocation"))
            titles = [
                label.text()
                for label in card.findChildren(QLabel, "GuideManualStageTitle")
            ]
            self.assertNotIn("Village d’Amakna", titles)

            card.deleteLater()
            view.deleteLater()
            self.app.processEvents()

    def test_quest_combats_are_inline_in_route_body_and_keep_shared_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            service = view._catalog_manual_services["dofus_sylvestre"]

            candidate_index = next(
                (
                    index
                    for index, source in enumerate(service.cards)
                    if service.manual_sections_for_card("character:1", source).get("boss")
                ),
                None,
            )
            self.assertIsNotNone(candidate_index)
            source = service.cards[int(candidate_index)]
            card = SharedGuideManualCard(
                service,
                "character:1",
                source,
                int(candidate_index),
            )
            self.app.processEvents()

            combat_checks = card.findChildren(QCheckBox, "GuideManualCombatCheck")
            self.assertTrue(combat_checks)
            self.assertTrue(
                all(
                    checkbox.parentWidget() is not None
                    and checkbox.parentWidget().objectName() == "GuideManualCombatInlineRow"
                    for checkbox in combat_checks
                )
            )
            self.assertFalse(
                any(
                    label.text().strip().upper() == "COMBATS DE QUÊTE"
                    for label in card.findChildren(QLabel)
                )
            )
            first = combat_checks[0]
            before = first.isChecked()
            first.click()
            self.app.processEvents()
            self.assertEqual(first.isChecked(), (not before))

            card.deleteLater()
            view.deleteLater()
            self.app.processEvents()

    def test_navigation_and_footer_have_the_requested_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            shared = view.stack.currentWidget()
            self.assertIsInstance(shared, SharedGuideManualView)
            self.app.processEvents()

            nav = shared.findChild(QFrame, "GuideManualNav")
            footer = shared.findChild(QFrame, "GuideManualProgressFrame")
            self.assertIsNotNone(nav)
            self.assertIsNotNone(footer)
            self.assertEqual(
                self._layout_widget_names(nav),
                [
                    "GuideManualPrev",
                    "GuideManualValidationHost",
                    "GuideManualNextButton",
                ],
            )
            self.assertEqual(
                self._layout_widget_names(footer),
                [
                    "GuideManualGuideButton",
                    "GuideManualProgress",
                    "GuideManualPercent",
                    "GuideManualProgressLock",
                    "GuideManualNavPage",
                ],
            )
            page = shared.findChild(QLabel, "GuideManualNavPage")
            self.assertIs(page.parentWidget(), footer)
            validation = shared.findChild(QPushButton, "GuideManualPageCheck")
            self.assertIsNotNone(validation)
            self.assertEqual(validation.text(), "Valider")

            view.deleteLater()
            self.app.processEvents()

    def test_lock_toggle_is_visual_persistent_and_defaults_unlocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            shared = view.stack.currentWidget()
            self.assertIsInstance(shared, SharedGuideManualView)
            service = view._catalog_manual_services["dofus_sylvestre"]
            self.app.processEvents()

            toggle = shared.findChild(QToolButton, "GuideManualProgressLock")
            self.assertIsNotNone(toggle)
            self.assertFalse(toggle.isChecked())
            self.assertEqual(toggle.text(), "🔓 Déverrouillé")
            toggle.click()
            self.app.processEvents()
            self.assertTrue(toggle.isChecked())
            self.assertEqual(toggle.text(), "🔒 Verrouillé")
            self.assertTrue(
                service.manual_checked(
                    "character:1",
                    SharedGuideManualView.ROUTE_LOCK_PROGRESS_KEY,
                )
            )

            restored = SharedGuideManualView(
                service,
                character_key="character:1",
                quest_provider=self.quest_provider,
            )
            self.app.processEvents()
            restored_toggle = restored.findChild(QToolButton, "GuideManualProgressLock")
            self.assertTrue(restored_toggle.isChecked())
            self.assertEqual(restored_toggle.text(), "🔒 Verrouillé")

            restored.deleteLater()
            view.deleteLater()
            self.app.processEvents()

    def test_route_progress_advances_when_the_current_sheet_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            shared = view.stack.currentWidget()
            self.assertIsInstance(shared, SharedGuideManualView)
            self.app.processEvents()

            bar = shared.findChild(QProgressBar, "GuideManualProgress")
            validation = shared.findChild(QPushButton, "GuideManualPageCheck")
            self.assertIsNotNone(bar)
            self.assertIsNotNone(validation)
            self.assertTrue(validation.isEnabled())
            before = bar.value()
            validation.click()
            self.app.processEvents()
            self.assertGreater(bar.value(), before)

            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
