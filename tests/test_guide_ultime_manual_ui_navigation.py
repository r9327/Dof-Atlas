from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QToolButton

from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideUltimeManualCard,
    GuideUltimeManualView,
)


class _FakeManualUiService:
    def __init__(self) -> None:
        long_lines = [
            {
                "kind": "action",
                "position": f"[{index},-{index}]",
                "text": (
                    f"Action de walkthrough numéro {index} avec suffisamment de texte "
                    "pour forcer le défilement vertical."
                ),
            }
            for index in range(60)
        ]
        self.cards = [
            {
                "manual_title": "Première fiche",
                "manual_chapter_id": "chapter_one",
                "manual_chapter_label": "Chapitre un",
                "destination": "[1,-1] Zone test",
                "manual_resource_names": [],
                "manual_lines": list(long_lines),
            },
            {
                "manual_title": "Deuxième fiche",
                "manual_chapter_id": "chapter_two",
                "manual_chapter_label": "Chapitre deux",
                "destination": "[2,-2] Zone test",
                "manual_resource_names": [],
                "manual_lines": list(long_lines),
            },
        ]
        self.available = True
        self.active_index = 0
        self.completed = 0
        self.quest_provider = None
        # Regression fixture: Guide UI must not render success-linked controls even
        # when the validation contract still contains success metadata.
        self.auto_validation_contract = {
            "cards": [
                {
                    "card_key": "legacy-success-target",
                    "successes": [{"achievement_id": 999, "name": "Succès de test"}],
                }
            ]
        }

    def reload_progress(self) -> None:
        return

    def first_incomplete_index(self, _character_key: str) -> int:
        return self.active_index

    def route_sheet_progress(self, _character_key: str) -> tuple[int, int]:
        return self.completed, len(self.cards)

    def manual_lines_for_card(self, _character_key: str, card: dict) -> list[dict]:
        return list(card.get("manual_lines", []))

    def card_auto_complete(self, _character_key: str, _card: dict) -> bool:
        return False

    def page_checked(self, _character_key: str, _card: dict, _index: int) -> bool:
        return False

    def set_page_checked(
        self,
        _character_key: str,
        _card: dict,
        _index: int,
        _checked: bool,
    ) -> None:
        return


class _FakeQuestProgress:
    def __init__(self) -> None:
        self.completed: set[tuple[str, int, int]] = set()

    def is_objective_completed(self, character_key: str, quest_id: int, objective_id: int) -> bool:
        return (character_key, quest_id, objective_id) in self.completed

    def set_objective_completed(
        self,
        character_key: str,
        quest_id: int,
        objective_id: int,
        completed: bool,
    ) -> None:
        key = (character_key, quest_id, objective_id)
        if completed:
            self.completed.add(key)
        else:
            self.completed.discard(key)


class _FakeQuestProvider:
    def get_quest(self, quest_id: int):
        if int(quest_id) != 42:
            raise KeyError(quest_id)
        objective = SimpleNamespace(
            id=4201,
            type_id=6,
            is_combat=True,
            image_label="Bouftou",
            text="Vaincre x3 Bouftou en un seul combat [1,2]",
            map_label="[1,2]",
            item_quantity=0,
        )
        unrelated = SimpleNamespace(
            id=4202,
            type_id=6,
            is_combat=True,
            image_label="Rat",
            text="Vaincre x8 Rat en un seul combat [9,9]",
            map_label="[9,9]",
            item_quantity=0,
        )
        return SimpleNamespace(
            id=42,
            name="Combat test",
            steps=(SimpleNamespace(objectives=(objective, unrelated)),),
        )


class GuideUltimeManualUiNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self) -> tuple[_FakeManualUiService, GuideUltimeManualView]:
        service = _FakeManualUiService()
        view = GuideUltimeManualView(service, character_key="character:1")
        view.resize(560, 320)
        view.show()
        QApplication.processEvents()
        return service, view

    def test_progress_header_is_compact_and_page_is_in_bottom_navigation(self) -> None:
        _service, view = self._view()
        try:
            self.assertEqual(view.route_progress_label.text(), "0 %")
            self.assertEqual(view.nav_page_label.text(), "Page 1 / 2")
            self.assertNotIn("Quêtes", view.route_progress_label.text())
            self.assertNotIn("Donjons", view.route_progress_label.text())
            self.assertEqual(view.route_lock_check.text(), "Verrouiller")
        finally:
            view.close()

    def test_progress_lock_blocks_only_direct_bar_jumps(self) -> None:
        _service, view = self._view()
        try:
            view.route_lock_check.setChecked(True)
            view._jump_from_progress(1.0)
            self.assertEqual(view.view_index, 0)

            view.navigate_relative(1)
            self.assertEqual(view.view_index, 1)

            view.route_lock_check.setChecked(False)
            view._jump_from_progress(0.0)
            self.assertEqual(view.view_index, 0)
        finally:
            view.close()

    def test_manual_ui_omits_obsolete_success_destination_and_breadcrumb_blocks(self) -> None:
        _service, view = self._view()
        try:
            texts = [label.text() for label in view.findChildren(QLabel)]
            self.assertFalse(any("SUCCÈS LIÉS" in text for text in texts))
            self.assertFalse(any("DESTINATION SUIVANTE" in text for text in texts))
            self.assertIsNone(view.findChild(QFrame, "GuideBreadcrumb"))
            self.assertEqual(view.guide_button.text(), "Guide")
        finally:
            view.close()

    def test_first_sheet_starts_with_a_clear_legend(self) -> None:
        _service, view = self._view()
        try:
            current_sheet = view.cards_layout.itemAt(0).widget()
            legend = current_sheet.findChild(QFrame, "GuideManualLegendCard")
            self.assertIsNotNone(legend)
            self.assertEqual(legend.findChild(QLabel, "GuideManualLegendTitle").text(), "LÉGENDE")
            texts = [label.text() for label in legend.findChildren(QLabel)]
            self.assertTrue(any("/travel x,y" in text for text in texts))
            self.assertTrue(any("Objet en vert" in text for text in texts))

            view.navigate_relative(1)
            QApplication.processEvents()
            current_sheet = view.cards_layout.itemAt(0).widget()
            self.assertIsNone(current_sheet.findChild(QFrame, "GuideManualLegendCard"))
        finally:
            view.close()

    def test_previous_next_and_validation_share_the_bottom_navigation_row(self) -> None:
        _service, view = self._view()
        try:
            nav = view.findChild(QFrame, "GuideManualNav")
            validation = nav.findChild(QCheckBox, "GuideManualPageCheck")
            self.assertIsNotNone(validation)
            self.assertIs(validation.parentWidget(), view.validation_host)
            self.assertIsNotNone(nav.findChild(QFrame, "GuideManualValidationHost"))
            self.assertIs(view.prev_button.parentWidget(), nav)
            self.assertIs(view.next_button.parentWidget(), nav)
        finally:
            view.close()

    def test_quest_combat_names_quantities_and_shared_check_state_are_rendered(self) -> None:
        service = _FakeManualUiService()
        service.quest_provider = _FakeQuestProvider()
        service.quest_progress = _FakeQuestProgress()
        card_data = dict(service.cards[0])
        card_data["manual_quest_ids"] = [42]
        card_data["manual_lines"] = [
            {
                "kind": "action",
                "position": "[1,2]",
                "text": "Vaincre le Bouftou maintenant.",
            }
        ]
        card = GuideUltimeManualCard(
            service,
            "character:1",
            card_data,
            0,
        )
        try:
            checkbox = card.findChild(QCheckBox, "GuideManualCombatCheck")
            self.assertIsNotNone(checkbox)
            self.assertEqual(checkbox.text(), "3 × Bouftou — Combat test")
            self.assertEqual(len(card.findChildren(QCheckBox, "GuideManualCombatCheck")), 1)
            self.assertTrue(checkbox.isEnabled())
            checkbox.click()
            QApplication.processEvents()
            self.assertIn(("character:1", 42, 4201), service.quest_progress.completed)
        finally:
            card.page_check.deleteLater()
            card.close()

    def test_inline_quest_overlay_is_deduplicated_per_quest_and_map(self) -> None:
        service = _FakeManualUiService()
        service.quest_provider = _FakeQuestProvider()
        card_data = dict(service.cards[0])
        card_data["manual_stage_id"] = "TEST-DEDUPE"
        card_data["manual_quest_ids"] = [42, 42]
        card_data["manual_lines"] = [
            {"kind": "action", "position": "[1,2]", "text": "Première action."},
            {"kind": "action", "position": "[1,2]", "text": "Deuxième action."},
            {"kind": "action", "position": "[2,2]", "text": "Map suivante."},
        ]
        card = GuideUltimeManualCard(service, "character:1", card_data, 0)
        try:
            buttons = card.findChildren(QToolButton, "GuideManualQuestInlineButton")
            self.assertEqual(len(buttons), 2)
            self.assertTrue(all(button.toolTip() == "Combat test" for button in buttons))
        finally:
            card.page_check.deleteLater()
            card.close()

    def test_prepare_block_drops_only_exact_actions_already_done_now(self) -> None:
        duplicate_prepare = {
            "kind": "warning",
            "position": "[1,-2]",
            "text": "Prendre la clé.",
        }
        duplicate_now = {
            "kind": "action",
            "position": " [1,-2] ",
            "text": "  PRENDRE LA CLÉ. ",
        }
        distinct_prepare = {
            "kind": "warning",
            "position": "",
            "text": "Prépare 4 × Potion.",
        }

        result = GuideUltimeManualCard._without_prepare_duplicates(
            {
                "prepare": [duplicate_prepare, distinct_prepare],
                "now": [duplicate_now],
                "boss": [],
            }
        )

        self.assertEqual(result["prepare"], [distinct_prepare])
        self.assertEqual(result["now"], [duplicate_now])

    def test_guide_button_returns_to_active_sheet_then_guides_catalog(self) -> None:
        _service, view = self._view()
        returned: list[bool] = []
        view.backToGuidesRequested.connect(lambda: returned.append(True))
        try:
            view.navigate_relative(1)
            QApplication.processEvents()
            self.assertEqual(view.view_index, 1)

            view.guide_button.click()
            QApplication.processEvents()
            self.assertEqual(view.view_index, 0)
            self.assertEqual(returned, [])

            view.guide_button.click()
            QApplication.processEvents()
            self.assertEqual(returned, [True])
        finally:
            view.close()

    def test_manual_line_positions_are_bold(self) -> None:
        rendered = GuideUltimeManualCard._format_line_html(
            "• ",
            "[5,-3]",
            "Parler au PNJ.",
            [],
            [],
        )
        self.assertIn("<b>[5,-3]</b>", rendered)
        self.assertIn("Parler au PNJ.", rendered)

    def test_next_sheet_always_starts_at_top(self) -> None:
        _service, view = self._view()
        try:
            bar = view.scroll.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(bar.maximum())
            self.assertGreater(bar.value(), 0)

            view.navigate_relative(1)
            QApplication.processEvents()

            self.assertEqual(view.view_index, 1)
            self.assertEqual(view.nav_page_label.text(), "Page 2 / 2")
            self.assertEqual(bar.value(), bar.minimum())
        finally:
            view.close()

    def test_external_progress_follows_active_sheet_and_resets_scroll(self) -> None:
        service, view = self._view()
        try:
            bar = view.scroll.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(bar.maximum())

            service.active_index = 1
            service.completed = 1
            view.refresh_external_progress()
            QApplication.processEvents()

            self.assertEqual(view.active_index, 1)
            self.assertEqual(view.view_index, 1)
            self.assertEqual(bar.value(), bar.minimum())
            self.assertEqual(view.route_progress_label.text(), "50 %")
            self.assertEqual(view.nav_page_label.text(), "Page 2 / 2")
        finally:
            view.close()

    def test_external_progress_does_not_yank_user_back_from_history(self) -> None:
        service, view = self._view()
        try:
            view.navigate_relative(1)
            QApplication.processEvents()
            self.assertEqual(view.view_index, 1)

            service.active_index = 0
            service.completed = 0
            view.refresh_external_progress()
            QApplication.processEvents()

            self.assertEqual(view.active_index, 0)
            self.assertEqual(view.view_index, 1)
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
