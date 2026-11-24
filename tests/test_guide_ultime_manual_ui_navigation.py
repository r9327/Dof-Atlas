from __future__ import annotations

import os
import unittest
from html import unescape
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QProgressBar,
)

from app.modules.encyclopedia.views.guide_ultime_manual_view import (
    GuideUltimeManualCard,
    GuideUltimeManualView,
)
from app.modules.encyclopedia.views.shared_manual_guide_view import (
    SharedGuideManualCard,
    SharedGuideManualView,
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
        self.manual_states: dict[tuple[str, str], bool] = {}
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

    def manual_checked(self, character_key: str, key: str) -> bool:
        return bool(self.manual_states.get((str(character_key), str(key)), False))

    def set_manual_checked(self, character_key: str, key: str, checked: bool) -> None:
        self.manual_states[(str(character_key), str(key))] = bool(checked)


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


class _FakeParticipantService:
    def __init__(self) -> None:
        self.selected = ["character:1"]

    def available_characters(self):
        return (
            SimpleNamespace(key="character:1", label="Alpha", connected=True),
            SimpleNamespace(key="character:2", label="Beta", connected=False),
        )

    def selected_keys(self):
        return tuple(self.selected)

    def save_selected_keys(self, values):
        self.selected = list(values)
        return tuple(self.selected)


class GuideUltimeManualUiNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self) -> tuple[_FakeManualUiService, SharedGuideManualView]:
        service = _FakeManualUiService()
        view = SharedGuideManualView(
            service, character_key="character:1", participant_service=_FakeParticipantService(),
        )
        view.resize(560, 320)
        view.show()
        QApplication.processEvents()
        return service, view

    def test_participant_rows_use_shared_deferred_cleanup(self) -> None:
        import inspect
        source = inspect.getsource(SharedGuideManualView._refresh_participants_panel)
        self.assertIn(
            "clear_unity_widget_layout(self.participants_layout, detach_widgets=False)",
            source,
        )

    def test_manual_renderers_hide_old_rows_via_shared_cleanup(self) -> None:
        import inspect

        self.assertIn(
            "clear_unity_widget_layout(self.cards_layout, hide_widgets=True)",
            inspect.getsource(SharedGuideManualView._clear_cards),
        )
        self.assertIn(
            "clear_unity_widget_layout(self.global_details_layout, hide_widgets=True)",
            inspect.getsource(SharedGuideManualView._refresh_global_details),
        )
        self.assertIn(
            "clear_unity_widget_layout(self.preparation_rows_layout, hide_widgets=True)",
            inspect.getsource(SharedGuideManualView._clear_preparation_rows),
        )

    def test_manual_validation_reuses_shared_cleanup_before_attaching_next_widget(self) -> None:
        import inspect

        source = inspect.getsource(GuideUltimeManualView._set_validation_widget)
        self.assertIn("clear_unity_widget_layout(self.validation_layout)", source)
        self.assertIn("self.validation_layout.addWidget(widget)", source)

    def test_progress_header_uses_canonical_layout_metrics(self) -> None:
        from app.ui.unity_palette import UNITY_LAYOUT_SIZES_PX

        _service, view = self._view()
        try:
            header = view.findChild(QFrame, "GuideCompactHeader")
            self.assertIsNotNone(header)
            margins = header.layout().contentsMargins()
            self.assertEqual(
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
                (
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_top"],
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_bottom"],
                ),
            )
            self.assertEqual(
                view._header_content_layout.spacing(),
                UNITY_LAYOUT_SIZES_PX["guide_header_content_spacing"],
            )
            self.assertEqual(
                header.layout().spacing(),
                UNITY_LAYOUT_SIZES_PX["guide_header_outer_spacing"],
            )
        finally:
            view.close()

    def test_progress_header_is_compact_and_page_is_in_bottom_navigation(self) -> None:
        _service, view = self._view()
        try:
            from app.ui.components import AtlasGuideReadingHeader, AtlasGuideSheetHeader
            self.assertIsInstance(view.reading_header, AtlasGuideReadingHeader)
            self.assertIsInstance(view.sheet_header, AtlasGuideSheetHeader)
            self.assertEqual(view.global_progress_label.text(), "0 %")
            self.assertEqual((view.global_progress_bar.value(), view.global_progress_bar.maximum()), (0, 2))
            self.assertTrue(view.progress_donut.isHidden())
            self.assertEqual(view.donut_count_label.text(), "0 fiches validées")
            self.assertFalse(hasattr(view, "summary_button"))
            self.assertFalse(hasattr(view, "route_bar"))
            self.assertIsNone(view.findChild(QFrame, "GuideSummaryPanel"))
            self.assertIsNone(view.findChild(QProgressBar, "GuideManualProgress"))
            self.assertEqual(view.sheet_title_label.text(), "Première fiche")
            self.assertIsNone(view.findChild(QLabel, "GuideSheetMeta"))
            self.assertEqual(view.nav_page_label.text(), "1/2")
        finally:
            view.close()


    def test_shared_guide_navigation_uses_universal_atlas_buttons(self) -> None:
        from app.ui.components import AtlasButton
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        _service, view = self._view()
        try:
            for control in (view.prev_button, view.next_button, view.guide_button):
                self.assertIsInstance(control, AtlasButton)
            self.assertEqual(view.prev_button.objectName(), "GuideManualPrev")
            self.assertEqual(view.next_button.objectName(), "GuideManualNextButton")
            self.assertEqual(view.page_jump.objectName(), "GuideCompactPageJump")
            self.assertEqual(view.page_jump.suffix(), "/2")
            self.assertEqual(view.preparation_button.objectName(), "GuideMetricDropdown")
            self.assertEqual(view.global_details_button.objectName(), "GuideMetricDropdown")
            self.assertEqual(view.participants_button.width(), UNITY_CONTROL_SIZES_PX["guide_character_button"])
            self.assertEqual(view.global_details_button.width(), UNITY_CONTROL_SIZES_PX["progress_toggle_width"])
            self.assertIs(
                view._header_content_layout.itemAt(1).widget(), view.participants_panel,
            )
            self.assertIs(
                view._metric_columns["Préparation"].itemAt(0).widget(),
                view.preparation_panel,
            )
            self.assertIs(view.preparation_bar.parentWidget(), view.reading_header.preparation_column)
            self.assertTrue(hasattr(view.reading_header, "summary_panel"))
            self.assertFalse(hasattr(view, "route_bar"))
            self.assertTrue(view.preparation_bar.isEnabled())
            self.assertEqual(view.prev_button.text(), "Précédent")
            self.assertEqual(view.next_button.text(), "Suivant")
        finally:
            view.close()


    def test_participant_portrait_sizes_are_shared_with_dev_ui(self) -> None:
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX
        from app.modules.encyclopedia.views.shared_manual_guide_view import _ParticipantPortraitButton

        portrait = _ParticipantPortraitButton("character:demo", progress=25)
        try:
            box = UNITY_CONTROL_SIZES_PX["guide_portrait_button"]
            icon = UNITY_CONTROL_SIZES_PX["guide_portrait_icon"]
            self.assertEqual((portrait.width(), portrait.height()), (box, box))
            self.assertEqual((portrait.iconSize().width(), portrait.iconSize().height()), (icon, icon))
            self.assertLess(icon, box)
        finally:
            portrait.close()

    def test_progress_edges_match_at_four_window_sizes_with_drawers_open_and_closed(self) -> None:
        from app.ui.components import AtlasComboBox
        from app.ui.unity_palette import UNITY_WINDOW_PRESETS_PX

        _service, view = self._view()
        try:
            self.assertIsInstance(view.preparation_filter, AtlasComboBox)
            self.assertEqual(view.preparation_filter.count(), 7)
            for preset, (width, height) in UNITY_WINDOW_PRESETS_PX.items():
                with self.subTest(preset=preset):
                    view.resize(width, height)
                    view.show()
                    for opened in (False, True):
                        view.global_details_button.setChecked(opened)
                        view.preparation_button.setChecked(opened)
                        QApplication.processEvents()
                        self.assertEqual(view.global_progress_bar.width(),
                                         view.global_details_panel.width() if opened else view.global_progress_bar.width())
                        if opened:
                            self.assertTrue(view.global_details_panel.isVisible())
                            self.assertTrue(view.preparation_panel.isVisible())
                            self.assertLessEqual(
                                view.preparation_filter.width(),
                                view.preparation_panel.width(),
                            )
            self.assertEqual(view.preparation_filter.currentText(), "Tout")
        finally:
            view.close()


    def test_narrow_layout_preserves_named_actions(self) -> None:
        _service, view = self._view()
        try:
            view.resize(490, 320)
            QApplication.processEvents()
            from app.ui.unity_palette import UNITY_LAYOUT_BREAKPOINTS_PX
            self.assertLess(view.width(), UNITY_LAYOUT_BREAKPOINTS_PX["guide_header_compact_below"])
            self.assertEqual(view.participants_button.text(), "")
            self.assertFalse(view.participants_button.icon().isNull())
            self.assertEqual(view.participants_button.accessibleName(), "Mes personnages · 1")
            self.assertIn("Choisir les identités", view.participants_button.toolTip())
            from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX
            self.assertLessEqual(
                view.page_jump.maximumWidth(),
                UNITY_CONTROL_SIZES_PX["guide_page_jump_compact_max_width"],
            )
            self.assertEqual(view.page_jump.suffix(), "/2")
            self.assertEqual(view._metric_caption_labels["Préparation"].text(), "Préparation")
            self.assertEqual(view._metric_caption_labels["Préparation"].toolTip(), "Préparation")

            view.resize(960, 640)
            QApplication.processEvents()
            self.assertEqual(view.participants_button.text(), "")
            self.assertEqual(view.participants_button.accessibleName(), "Mes personnages · 1")
            self.assertLessEqual(
                view.page_jump.maximumWidth(),
                UNITY_CONTROL_SIZES_PX["guide_page_jump_normal_max_width"],
            )
            self.assertEqual(view._metric_caption_labels["Préparation"].text(), "Préparation")
        finally:
            view.close()

    def test_obsolete_route_lock_is_removed_but_page_navigation_still_works(self) -> None:
        _service, view = self._view()
        try:
            self.assertIsNone(view.findChild(QToolButton, "GuideManualProgressLock"))
            self.assertIsNone(view.findChild(QProgressBar, "GuideManualProgress"))
            view.navigate_relative(1)
            self.assertEqual(view.view_index, 1)
            view.navigate_relative(-1)
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
            self.assertFalse(view.guide_button.icon().isNull())
            self.assertEqual(view.guide_button.accessibleName(), "Fiche actuelle ou catalogue des guides")
            self.assertEqual(view.guide_title_label.text(), "Guide Succès")
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

    def test_participants_are_persistent_and_coordinate_launches_once(self) -> None:
        service = _FakeManualUiService()
        participants = _FakeParticipantService()
        calls: list[tuple[str, tuple[str, ...]]] = []
        view = SharedGuideManualView(
            service,
            character_key="character:1",
            participant_service=participants,
            travel_callback=lambda command, keys: calls.append((command, keys)),
        )
        try:
            self.assertEqual(view.participants_button.text(), "")
            self.assertFalse(view.participants_button.icon().isNull())
            self.assertEqual(view.participants_button.accessibleName(), "Mes personnages · 1")
            self.assertFalse(view.participants_panel.isVisible())
            view.participants_button.click()
            QApplication.processEvents()
            portraits = view.findChildren(QToolButton, "GuideParticipantPortrait")
            self.assertEqual([portrait.accessibleName() for portrait in portraits], ["Alpha", "Beta"])
            self.assertTrue(all(portrait.text() == "" for portrait in portraits))
            portraits[1].click()
            self.assertEqual(view.participants_button.accessibleName(), "Mes personnages · 2")
            self.assertEqual(view.participants_button.text(), "")
            self.assertEqual(
                participants.selected_keys(),
                ("character:1", "character:2"),
            )

            current_sheet = view.cards_layout.itemAt(0).widget()
            current_sheet._copy_link_target("travel-copy:1,-1")
            self.assertEqual(
                calls,
                [("/travel 1,-1", ("character:1",))],
            )
            legend = current_sheet.findChild(QFrame, "GuideManualLegendCard")
            texts = [label.text() for label in legend.findChildren(QLabel)]
            self.assertTrue(any("participants sélectionnés" in text for text in texts))
        finally:
            view.close()

    def test_travel_refuses_unverified_offline_or_empty_recipients(self) -> None:
        service = _FakeManualUiService()
        participants = _FakeParticipantService()
        sends: list[tuple[str, tuple[str, ...]]] = []
        view = SharedGuideManualView(
            service,
            character_key="character:1",
            participant_service=participants,
            travel_callback=lambda command, keys: sends.append((command, keys)),
        )
        try:
            participants.selected = ["character:2", "character:999"]
            self.assertFalse(view._launch_travel_command("/travel 4,-8"))
            self.assertEqual(sends, [])
            self.assertEqual(QApplication.clipboard().text(), "/travel 4,-8")

            participants.selected = ["character:1", "character:2", "character:999"]
            self.assertTrue(view._launch_travel_command("/travel 4,-8"))
            self.assertEqual(sends, [("/travel 4,-8", ("character:1",))])

            self.assertFalse(view._launch_travel_command("/zaap 4,-8"))
            self.assertEqual(sends, [("/travel 4,-8", ("character:1",))])
            self.assertEqual(QApplication.clipboard().text(), "/zaap 4,-8")
        finally:
            view.close()

    def test_global_and_preparation_drawers_remain_open_during_page_navigation(self) -> None:
        _service, view = self._view()
        try:
            view.show()
            view.preparation_button.click()
            view.reading_header.summary_button.click()
            QApplication.processEvents()
            self.assertFalse(view.global_details_panel.isVisible())
            self.assertTrue(view.preparation_panel.isVisible())
            self.assertTrue(view.reading_header.summary_panel.isVisible())
            view.global_details_button.click()
            view.reading_header.summary_panel.setCurrentRow(1)
            self.assertEqual(view.view_index, 1)
            self.assertTrue(view.global_details_button.isChecked())
            self.assertTrue(view.preparation_button.isChecked())
            self.assertTrue(view.reading_header.summary_button.isChecked())
            view.navigate_relative(-1)
            self.assertEqual(view.view_index, 0)
            self.assertTrue(view.preparation_panel.isVisible())
        finally:
            view.close()


    def test_previous_next_and_validation_share_the_bottom_navigation_row(self) -> None:
        _service, view = self._view()
        try:
            nav = view.findChild(QFrame, "GuideManualNav")
            validation = nav.findChild(QCheckBox, "GuideManualPageCheck")
            if validation is None:
                validation = nav.findChild(QToolButton, "GuideManualPageCheck")
            self.assertIsNotNone(view.validation_host.findChild(QFrame) or view.validation_host)
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
        card = SharedGuideManualCard(
            service,
            "character:1",
            card_data,
            0,
        )
        try:
            checkbox = card.findChild(QCheckBox, "GuideManualCombatCheck")
            self.assertIsNotNone(checkbox)
            self.assertEqual(checkbox.text(), "×3 Bouftou")
            self.assertEqual(checkbox.minimumWidth(), 0)
            self.assertEqual(
                checkbox.sizePolicy().horizontalPolicy(),
                QSizePolicy.Ignored,
            )
            self.assertIn("×3 Bouftou — Combat test", checkbox.toolTip())
            self.assertEqual(len(card.findChildren(QCheckBox, "GuideManualCombatCheck")), 1)
            self.assertTrue(checkbox.isEnabled())
            checkbox.click()
            QApplication.processEvents()
            self.assertIn(("character:1", 42, 4201), service.quest_progress.completed)
        finally:
            card.page_check.deleteLater()
            card.close()

    def test_inline_quest_overlay_is_deduplicated_per_quest_and_sheet(self) -> None:
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
        card = SharedGuideManualCard(service, "character:1", card_data, 0)
        try:
            buttons = card.findChildren(QToolButton, "GuideManualQuestInlineButton")
            self.assertEqual(len(buttons), 1)
            self.assertTrue(all(button.toolTip() == "Combat test" for button in buttons))
        finally:
            card.page_check.deleteLater()
            card.close()

    def test_contiguous_actions_at_exact_same_map_share_visual_group_only(self) -> None:
        service = _FakeManualUiService()
        card_data = dict(service.cards[0])
        card_data["manual_lines"] = [
            {"kind": "action", "position": "[1,2]", "text": "Parler au PNJ."},
            {"kind": "action", "position": "[1,2]", "text": "Prendre l'objet."},
            {"kind": "action", "position": "[2,2]", "text": "Changer de carte."},
            {"kind": "action", "position": "[1,2]", "text": "Revenir plus tard."},
        ]
        card = SharedGuideManualCard(service, "character:1", card_data, 0)
        try:
            groups = card.findChildren(QFrame, "GuideManualActionGroup")
            self.assertEqual(len(groups), 1)
            grouped_rows = groups[0].findChildren(QFrame, "GuideManualLineRow")
            self.assertEqual(len(grouped_rows), 2)
            row_texts = [
                unescape(row.findChild(QLabel).text()) for row in grouped_rows
            ]
            self.assertIn("Parler au PNJ", row_texts[0])
            self.assertIn("Prendre l'objet", row_texts[1])
            self.assertEqual(len(card.findChildren(QFrame, "GuideManualLineRow")), 4)
            self.assertEqual(
                card_data["manual_lines"][0]["text"], "Parler au PNJ."
            )
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

    def test_existing_guide_inline_links_share_universal_styles_and_copy(self) -> None:
        from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES
        from app.ui.theme import PALETTE

        rendered = GuideUltimeManualCard._format_line_html(
            "", "[5,-3]", "Parler à PNJ Exemple puis ramasser Ortie.",
            ["PNJ Exemple"], ["Ortie"],
        )
        for kind, href in (
            ("position", 'href="travel-copy:5,-3"'),
            ("item", 'href="item-copy:Ortie"'),
        ):
            with self.subTest(kind=kind):
                self.assertIn(href, rendered)
                self.assertIn(f"color:{PALETTE[ENTITY_LINK_COLOR_ROLES[kind]]}", rendered)
        self.assertIn(
            f"color:{PALETTE[ENTITY_LINK_COLOR_ROLES['npc']]}", rendered
        )
        self.assertEqual(
            GuideUltimeManualCard._copy_text_for_link("item-copy:Ortie"), "Ortie"
        )
        self.assertEqual(
            GuideUltimeManualCard._copy_text_for_link("travel-copy:5,-3"),
            "/travel 5,-3",
        )

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
            self.assertEqual(view.nav_page_label.text(), "2/2")
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
            self.assertEqual(view.global_progress_label.text(), "50 %")
            self.assertEqual((view.global_progress_bar.value(), view.global_progress_bar.maximum()), (1, 2))
            self.assertEqual(view.progress_donut._percent, 50)
            self.assertEqual(view.nav_page_label.text(), "2/2")
        finally:
            view.close()

    def test_actual_uses_first_incomplete_sheet_across_selected_participants(self) -> None:
        service = _FakeManualUiService()
        participants = _FakeParticipantService()
        participants.selected = ["character:1", "character:2"]
        service.first_incomplete_index = lambda key: {
            "character:1": 1,
            "character:2": 0,
        }[key]
        view = SharedGuideManualView(
            service,
            character_key="character:1",
            participant_service=participants,
        )
        try:
            view._show_index(1)
            view.go_active()
            self.assertEqual(view.active_index, 0)
            self.assertEqual(view.view_index, 0)
        finally:
            view.close()

    def test_sommaire_has_no_visual_widgets_in_shared_reader(self) -> None:
        _service, view = self._view()
        try:
            self.assertIsNone(view.findChild(QFrame, "GuideSummaryPanel"))
            self.assertFalse(hasattr(view, "summary_list"))
            self.assertFalse(hasattr(view, "summary_button"))
            self.assertFalse(hasattr(view, "route_bar"))
        finally:
            view.close()


    def test_preparation_aggregates_exact_participant_needs_and_keeps_stones_in_typed_filters(self) -> None:
        service = _FakeManualUiService()
        # Explicit consumable evidence permits adding separate incomplete stages;
        # duplicate lines on one card remain display mirrors, not extra purchases.
        service.cards[0]["a_preparer"] = [
            {"item_id": 10, "name": "Potion de test", "quantity": 4, "consumable": True},
            {"item_id": 10, "name": "Potion de test", "quantity": 4, "consumable": True},
            {"item_id": 20, "name": "Pierre d'âme moyenne", "quantity": 1},
            {"item_id": 30, "name": "Clef de test", "quantity": 2},
        ]
        service.cards[1]["a_preparer"] = [
            {"item_id": 10, "name": "Potion de test", "quantity": 2, "consumable": True},
        ]
        service.card_auto_complete = lambda key, card: (
            key == "character:2" and card is service.cards[0]
        )
        participants = _FakeParticipantService()
        participants.selected = ["character:1", "character:2"]
        view = SharedGuideManualView(
            service,
            character_key="character:1",
            participant_service=participants,
        )
        try:
            self.assertFalse(view.preparation_panel.isVisible())
            view.global_details_button.click()
            view.preparation_button.click()
            potion = next(need for need in view._preparation_needs if need.name == "Potion de test")
            self.assertEqual(
                dict(potion.required_by_character),
                {"character:1": 6, "character:2": 2},
            )
            summaries = [
                label.text()
                for row in view.findChildren(QFrame, "GuidePreparationSummary")
                for label in row.findChildren(QLabel)
            ]
            self.assertIn("0 / 1 prêts", summaries)
            # Tout must retain both special resources and their authored
            # quantities; neither belongs to the generic "Objets" filter.
            categories = {need.name: need.category for need in view._preparation_needs}
            self.assertEqual(categories["Pierre d'âme moyenne"], "Pierres d'âme")
            self.assertEqual(categories["Clef de test"], "Clefs")
            labels = [
                label.text()
                for label in view.preparation_panel.findChildren(
                    QPushButton, "GuidePreparationItemCopy"
                )
            ]
            self.assertTrue(any("Pierre d'âme moyenne" in label for label in labels))
            self.assertTrue(any("Clef de test" in label for label in labels))
            for filter_key, expected in (
                ("Pierres d'âme", "Pierre d'âme moyenne"),
                ("Clefs", "Clef de test"),
            ):
                view.preparation_filter.setCurrentText(filter_key)
                QApplication.processEvents()
                selected_rows = [
                    view.preparation_rows_layout.itemAt(i).widget()
                    for i in range(view.preparation_rows_layout.count())
                ]
                displayed = [
                    label.text()
                    for widget in selected_rows if widget is not None
                    for label in widget.findChildren(QPushButton, "GuidePreparationItemCopy")
                ]
                self.assertTrue(
                    any(expected in label for label in displayed),
                    f"{expected} missing from {filter_key}: {displayed!r}",
                )
        finally:
            view.close()

    def test_ready_state_is_per_identity_when_a_participant_is_added(self) -> None:
        service = _FakeManualUiService()
        service.cards[0]["a_preparer"] = [
            {"item_id": 10, "name": "Potion de test", "quantity": 4},
        ]
        participants = _FakeParticipantService()
        view = SharedGuideManualView(
            service,
            character_key="character:1",
            participant_service=participants,
        )
        try:
            view.global_details_button.click()
            view.preparation_button.click()
            view.preparation_filter.setCurrentText("Potions")
            self.assertEqual(view.preparation_filter.currentText(), "Potions")
            ready = view.findChild(QCheckBox, "GuidePreparationReady")
            # Exact visual/functional row order, shared by Guide and Ganymède.
            line = ready.parentWidget().layout().itemAt(0).layout()
            self.assertIs(line.itemAt(0).widget(), ready)
            self.assertIn(
                line.itemAt(1).widget().objectName(),
                {"GuidePreparationQuantity", "GuidePreparationQuantityPlaceholder"},
            )
            copy_button = line.itemAt(2).widget()
            self.assertEqual(copy_button.objectName(), "GuidePreparationItemCopy")
            QApplication.clipboard().clear()
            copy_button.click()
            self.assertIn("Potion de test", QApplication.clipboard().text())
            ready.click()
            self.assertTrue(ready.isChecked())
            view.participants_button.click()
            portraits = view.findChildren(QToolButton, "GuideParticipantPortrait")
            portraits[1].click()
            QApplication.processEvents()
            self.assertFalse(view.findChild(QCheckBox, "GuidePreparationReady").isChecked())
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
