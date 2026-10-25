from __future__ import annotations

import copy
import os
import tempfile
import unittest
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

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


class _VerifiedSoloParticipant:
    """Deterministic selected character for validation integration tests."""

    def available_characters(self):
        return (SimpleNamespace(key="character:1", label="Alpha", connected=False),)

    def selected_keys(self):
        return ("character:1",)

    def save_selected_keys(self, values):
        return tuple(values)


class LanyelSharedManualUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        started = time.perf_counter()
        cls.app = QApplication.instance() or QApplication([])
        cls.quest_provider = QuestProvider()
        cls.achievement_provider = AchievementProvider(quest_provider=cls.quest_provider)
        # Load the lightweight retained achievement index only. Eager
        # load_all() also builds heavy detail-source offsets unrelated to
        # these Guide/route contracts; get_detail_by_id stays lazy.
        cls.achievement_provider.load_retained()
        cls.guide_provider = GuideProvider(
            quest_provider=cls.quest_provider,
            achievement_provider=cls.achievement_provider,
        )
        cls.guide_provider.load_all()
        cls.fixture_setup_ms = round((time.perf_counter() - started) * 1000, 1)
        print(f"AT018 fixture=lanyel_ui setup_ms={cls.fixture_setup_ms}", flush=True)

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
            self.assertEqual(service.guide_title, "Sylvestre Opti")
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

    def test_rapid_navigation_detaches_old_sheets_before_deferred_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            for guide_id in ("dofus_sylvestre", "guide_complet"):
                self.assertTrue(view.select_guide(guide_id))
                manual = view.stack.currentWidget()
                self.assertIsInstance(manual, SharedGuideManualView)
                previous = manual.findChild(QFrame, "GuideManualSheet")
                self.assertIsNotNone(previous)
                for index in (1, 2, 0, 1, 0):
                    manual._show_index(index)
                    # Deliberately no QApplication.processEvents(): the previous
                    # widget must be detached before Qt processes DeferredDelete.
                    sheets = manual.findChildren(QFrame, "GuideManualSheet")
                    self.assertEqual(
                        len(sheets), 1,
                        f"{guide_id}: old GuideManualSheet still attached at page {index}",
                    )
                    if previous is not None:
                        self.assertIsNone(
                            previous.parentWidget(),
                            f"{guide_id}: previous sheet was left as a child",
                        )
                    previous = sheets[0]
                self.app.processEvents()
            view.deleteLater()
            self.app.processEvents()

    def test_prepare_rows_are_not_repeated_inside_the_active_sheet(self) -> None:
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
            self.assertIsNone(card.findChild(QFrame, "GuideManualWarningSection"))
            texts = [label.text() for label in card.findChildren(QLabel)]
            self.assertFalse(any("Prépare le premier objet" in text for text in texts))
            self.assertFalse(any("Prépare le second objet" in text for text in texts))

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
            headings = card.findChildren(QLabel, "GuideManualCombatTargetsTitle")
            self.assertTrue(headings)
            self.assertTrue(all(heading.text() == "Faire les combats :" for heading in headings))
            self.assertTrue(
                all(
                    checkbox.text().startswith("×")
                    and " — " not in checkbox.text()
                    and checkbox.toolTip()
                    for checkbox in combat_checks
                )
            )
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

    def test_common_progress_uses_same_sheet_ids_not_smallest_count(self) -> None:
        completed = {
            "character:1": {0, 1, 2, 3, 4},
            "character:2": {5, 6, 7, 8, 9},
        }
        count = SharedGuideManualView._common_sheet_count(
            ("character:1", "character:2"),
            tuple(range(10)),
            lambda key, card, _index: card in completed[key],
        )
        self.assertEqual(count, 0)
        completed["character:2"].update((0, 2))
        self.assertEqual(
            SharedGuideManualView._common_sheet_count(
                tuple(completed), tuple(range(10)),
                lambda key, card, _index: card in completed[key],
            ),
            2,
        )

    def test_preparation_without_selected_characters_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            shared = view.stack.currentWidget()
            self.assertIsInstance(shared, SharedGuideManualView)
            shared.participant_service.save_selected_keys([])
            shared._load_preparation_needs()
            shared.preparation_button.setChecked(True)
            self.app.processEvents()
            self.assertEqual(shared._preparation_needs, ())
            self.assertFalse(shared.preparation_panel.findChildren(QToolButton, "GuidePreparationReady"))
            description = shared.preparation_panel.findChild(QLabel, "GuidePreparationEmpty")
            self.assertIsNotNone(description)
            self.assertIn("Aperçu des préparatifs", description.text())
            view.deleteLater()
            self.app.processEvents()

    def test_navigation_and_compact_headers_have_the_requested_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = self._view(Path(directory))
            self.assertTrue(view.select_guide("dofus_sylvestre"))
            shared = view.stack.currentWidget()
            self.assertIsInstance(shared, SharedGuideManualView)
            self.app.processEvents()

            nav = shared.findChild(QFrame, "GuideManualNav")
            compact = shared.findChild(QFrame, "GuideCompactHeader")
            sheet_header = shared.findChild(QFrame, "GuideSheetHeader")
            self.assertIsNotNone(nav)
            self.assertIsNotNone(compact)
            self.assertIsNotNone(sheet_header)
            self.assertEqual(
                self._layout_widget_names(nav),
                [
                    "GuideManualPrev",
                    "GuideManualValidationHost",
                    "GuideManualNextButton",
                ],
            )
            self.assertIsNotNone(compact.findChild(QProgressBar, "GuideManualProgress"))
            self.assertIsNotNone(compact.findChild(QToolButton, "GuideManualProgressLock"))
            self.assertIsNotNone(compact.findChild(QToolButton, "GuideParticipantsButton"))
            self.assertIsNotNone(compact.findChild(QToolButton, "GuideSummaryButton"))
            self.assertIsNotNone(compact.findChild(QToolButton, "GuidePreparationToggle"))
            self.assertIsNone(sheet_header.findChild(QToolButton, "GuideParticipantsButton"))
            self.assertEqual(
                [shared.header_actions_row.itemAt(i).widget().objectName() for i in range(3)],
                ["GuidePreparationToggle", "GuideSummaryButton", "GuideParticipantsButton"],
            )
            self.assertFalse(hasattr(shared, "page_jump_button"))
            self.assertEqual(shared.guide_button.text(), "←")
            self.assertFalse(shared.overlay_button.isEnabled())
            self.assertGreater(len(shared.service.cards), 1)
            shared.page_jump.setValue(2)
            self.app.processEvents()
            self.assertEqual(shared.view_index, 1)
            self.assertEqual(shared.page_jump.value(), 2)
            shared.page_jump.setValue(1)
            self.app.processEvents()
            self.assertEqual(shared.view_index, 0)
            self.assertEqual(shared.nav_page_label.text().split(" / ")[0], "Page 1")
            self.assertFalse(shared.nav_page_label.isVisible())
            shared.participant_service = _VerifiedSoloParticipant()
            shared._refresh_participants_panel()
            shared._refresh_header()
            self.assertTrue(shared.route_progress_label.text().endswith(" %"))
            self.assertIsNotNone(shared.progress_donut._percent)
            validation = shared.findChild(QPushButton, "GuideManualPageCheck")
            self.assertIsNotNone(validation)
            self.assertIn(validation.text(), ("Choisir des personnages", "Valider"))

            view.deleteLater()
            self.app.processEvents()

    def test_lock_toggle_has_visible_state_label_is_persistent_and_defaults_unlocked(self) -> None:
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
            self.assertEqual(toggle.text(), "Déverrouillé")
            self.assertTrue(toggle.icon().isNull() is False)
            toggle.click()
            self.app.processEvents()
            self.assertTrue(toggle.isChecked())
            self.assertEqual(toggle.text(), "Verrouillé")
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
            self.assertEqual(restored_toggle.text(), "Verrouillé")

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

            shared.participant_service = _VerifiedSoloParticipant()
            shared._refresh_participants_panel()
            shared._refresh_header()
            shared._render_window()
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
