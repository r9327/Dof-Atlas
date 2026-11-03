from __future__ import annotations

import os
import re
import tempfile
import unittest
from html import unescape
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.guide_shared_route_contract import project_authorized_guide
from PySide6.QtWidgets import QLabel, QFrame
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from tests.test_guide_ultime_manual_ui_navigation import (
    _FakeManualUiService,
    _FakeParticipantService,
)


class _SavedGuideService(_FakeManualUiService):
    """A real atomic GuideProgressService behind the actual Qt view."""

    def __init__(self, path: Path):
        super().__init__()
        self.guide_progress = GuideProgressService(path)
        self.progress_id = "catalog_manual:test_selection"
        self.automatic: set[tuple[str, int]] = set()
        self.blocked: set[tuple[str, int]] = set()

    def reload_progress(self) -> None:
        self.guide_progress.reload()

    def page_key(self, _card: dict, index: int = 0) -> str:
        return f"page:stable:test_selection:{index}"

    def page_checked(self, character_key: str, card: dict, index: int) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key, self.progress_id, self.page_key(card, index)
        )

    def card_auto_complete(self, character_key: str, card: dict) -> bool:
        return (character_key, self.cards.index(card)) in self.automatic

    def manual_order_choice_blocking(self, character_key: str, card: dict) -> bool:
        return (character_key, self.cards.index(card)) in self.blocked

    def route_sheet_progress(self, character_key: str) -> tuple[int, int]:
        done = sum(
            self.card_auto_complete(character_key, card)
            or self.page_checked(character_key, card, index)
            for index, card in enumerate(self.cards)
        )
        return int(done), len(self.cards)

    def first_incomplete_index(self, character_key: str) -> int:
        for index, card in enumerate(self.cards):
            if not (
                self.card_auto_complete(character_key, card)
                or self.page_checked(character_key, card, index)
            ):
                return index
        return max(0, len(self.cards) - 1)


class _ThreeParticipants(_FakeParticipantService):
    def available_characters(self):
        return super().available_characters() + (
            SimpleNamespace(key="character:3", label="Gamma", connected=False),
        )


class GuideManualSelectedValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "guide_progress.json"
        self.service = _SavedGuideService(self.path)
        self.participants = _ThreeParticipants()
        self.view = SharedGuideManualView(
            self.service,
            character_key="character:1",
            participant_service=self.participants,
        )
        self.view.show()
        QApplication.processEvents()

    def tearDown(self) -> None:
        self.view.close()
        QApplication.processEvents()
        self.temp.cleanup()

    def _check(self, character_key: str, sheet_index: int = 0) -> bool:
        return self.service.page_checked(
            character_key,
            self.service.cards[sheet_index],
            sheet_index,
        )

    def _show_sheet(self, index: int = 0) -> None:
        self.view._show_index(index)
        QApplication.processEvents()

    def test_empty_selection_never_writes_global_character(self) -> None:
        self.participants.save_selected_keys(())
        self._show_sheet()
        button = self.view.validation_layout.itemAt(0).widget()
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.text(), "Valider")
        button.click()
        QApplication.processEvents()
        self.assertTrue(self.view.participants_button.isChecked())
        # Opening the explicit picker never writes the browsing identity.
        self.assertFalse(self._check("character:1"))
        self.assertFalse(self.path.exists())

    def test_select_then_validate_and_undo_affects_only_selected_identities(self) -> None:
        self.participants.save_selected_keys(("character:1",))
        self._show_sheet()
        self.view.validation_layout.itemAt(0).widget().click()
        self.assertTrue(self._check("character:1"))
        self.assertFalse(self._check("character:2"))
        self.assertFalse(self._check("character:3"))

        # Change selection through a real portrait click, without reopening Guide.
        self.view._participant_buttons["character:2"].click()
        QApplication.processEvents()
        # The first Valider legitimately advanced to the next incomplete
        # sheet. Navigate back to the source sheet before testing mixed-team
        # completion; never assert a click on the next page changed page zero.
        self._show_sheet(0)
        control = self.view.validation_layout.itemAt(0).widget()
        self.assertEqual(control.text(), "Valider")
        control.click()
        self.assertTrue(self._check("character:1"))
        self.assertTrue(self._check("character:2"))
        self.assertFalse(self._check("character:3"))

        self.view._participant_buttons["character:1"].click()
        QApplication.processEvents()
        self._show_sheet(0)
        control = self.view.validation_layout.itemAt(0).widget()
        self.assertEqual(control.text(), "Annuler validation")
        control.click()
        self.assertTrue(self._check("character:1"))
        self.assertFalse(self._check("character:2"))
        self.assertFalse(self._check("character:3"))
        self.assertTrue(
            GuideProgressService(self.path).is_manual_step_completed(
                "character:1", self.service.progress_id, self.service.page_key(self.service.cards[0], 0)
            )
        )

    def test_automatic_evidence_survives_manual_undo(self) -> None:
        self.participants.save_selected_keys(("character:1", "character:2"))
        self.service.automatic.add(("character:1", 0))
        self._show_sheet()
        self.view.validation_layout.itemAt(0).widget().click()
        self.assertFalse(self._check("character:1"))
        self.assertTrue(self._check("character:2"))

        self.service.automatic.add(("character:2", 0))
        self._show_sheet()
        self.assertEqual(self.view.validation_layout.itemAt(0).widget().text(), "Annuler validation")
        self.view.validation_layout.itemAt(0).widget().click()
        self.assertFalse(self._check("character:2"))
        self.assertTrue(self.service.card_auto_complete("character:2", self.service.cards[0]))

    def test_blocked_participant_prevents_partial_team_write(self) -> None:
        self.participants.save_selected_keys(("character:1", "character:2"))
        self.service.blocked.add(("character:2", 0))
        self._show_sheet()
        control = self.view.validation_layout.itemAt(0).widget()
        self.assertFalse(control.isEnabled())
        self.assertIn("ordre", control.text())
        self.assertFalse(self._check("character:1"))
        self.assertFalse(self._check("character:2"))
        self.assertFalse(self.path.exists())

    def test_unregistered_selected_identity_is_never_written(self) -> None:
        self.participants.save_selected_keys(("character:1", "character:999"))
        self._show_sheet()
        self.view.validation_layout.itemAt(0).widget().click()
        self.assertTrue(self._check("character:1"))
        self.assertFalse(
            GuideProgressService(self.path).manual_steps(
                "character:999", self.service.progress_id
            )
        )

    def test_unknown_participant_progress_is_not_reported_as_zero(self) -> None:
        self.participants.save_selected_keys(("character:1",))
        self.service.route_sheet_progress = lambda key: (
            (0, 0) if key == "character:1" else (0, len(self.service.cards))
        )
        self.view._refresh_participants_panel()
        self.view._refresh_header()

        unknown = self.view._participant_buttons["character:1"]
        known_zero = self.view._participant_buttons["character:2"]
        self.assertIsNone(unknown.progress)
        self.assertIn("progression inconnue", unknown.toolTip())
        self.assertEqual(known_zero.progress, 0)
        self.assertIn("0 %", known_zero.toolTip())
        self.assertEqual(self.view.route_progress_label.text(), "—")
        self.assertIsNone(self.view.progress_donut._percent)
        self.assertFalse(self.view.current_button.isEnabled())

    def test_known_zero_progress_still_displays_zero(self) -> None:
        self.participants.save_selected_keys(("character:1",))
        self.view._refresh_participants_panel()
        self.view._refresh_header()
        self.assertEqual(self.view._participant_buttons["character:1"].progress, 0)
        self.assertEqual(self.view.route_progress_label.text(), "0 %")
        self.assertEqual((self.view.route_bar.value(), self.view.route_bar.maximum()), (0, 2))
        self.assertEqual(self.view.progress_donut._percent, 0)

    def test_external_progress_refresh_updates_existing_portrait(self) -> None:
        self.participants.save_selected_keys(("character:1",))
        self.view._refresh_participants_panel()
        portrait = self.view._participant_buttons["character:1"]
        self.assertEqual(portrait.progress, 0)

        first = self.service.cards[0]
        self.service.guide_progress.set_manual_step_completed(
            "character:1", self.service.progress_id, self.service.page_key(first, 0), True,
        )
        self.view.refresh()
        self.assertIs(self.view._participant_buttons["character:1"], portrait)
        self.assertEqual(portrait.progress, 50)
        self.assertIn("50 %", portrait.toolTip())

    def test_team_progress_counts_shared_sheet_intersection(self) -> None:
        self.participants.save_selected_keys(("character:1", "character:2"))
        first, second = self.service.cards
        self.service.guide_progress.set_manual_step_completed(
            "character:1", self.service.progress_id, self.service.page_key(first, 0), True,
        )
        self.service.guide_progress.set_manual_step_completed(
            "character:2", self.service.progress_id, self.service.page_key(second, 1), True,
        )
        self.view.refresh()
        self.assertEqual(self.view.route_progress_label.text(), "0 %")
        self.assertEqual((self.view.route_bar.value(), self.view.route_bar.maximum()), (0, 2))
        self.assertEqual(self.view.progress_donut._percent, 0)

    def test_last_click_refreshes_completed_state_without_reopening_guide(self) -> None:
        self.participants.save_selected_keys(("character:1", "character:2"))
        first = self.service.cards[0]
        self.service.guide_progress.set_manual_steps_for_characters(
            ("character:1", "character:2"),
            self.service.progress_id,
            self.service.page_key(first, 0),
            True,
        )
        self._show_sheet(1)
        self.view.validation_layout.itemAt(0).widget().click()
        QApplication.processEvents()
        self.assertEqual(self.view.route_progress_label.text(), "100 %")
        self.assertEqual((self.view.route_bar.value(), self.view.route_bar.maximum()), (2, 2))
        self.assertEqual(self.view.current_button.property("guideFullText"), "Terminé")
        # Compact viewport hides only the caption, not its meaning.
        self.assertEqual(self.view.current_button.accessibleName(), "Terminé")
        self.assertFalse(self.view.current_button.isEnabled())
        self.assertEqual(
            self.view.validation_layout.itemAt(0).widget().text(), "Annuler validation"
        )

    def test_completed_team_has_no_phantom_current_sheet(self) -> None:
        self.participants.save_selected_keys(("character:1", "character:2"))
        for index, card in enumerate(self.service.cards):
            self.service.guide_progress.set_manual_steps_for_characters(
                ("character:1", "character:2"),
                self.service.progress_id,
                self.service.page_key(card, index),
                True,
            )
        self.view.refresh()
        self.assertEqual(self.view.route_progress_label.text(), "100 %")
        self.assertEqual((self.view.route_bar.value(), self.view.route_bar.maximum()), (2, 2))
        self.assertFalse(self.view.current_button.isEnabled())


class ImportedSourceSharedManualUiTests(unittest.TestCase):
    """Synthetic preview cards pass through the EXISTING shared Qt renderer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _source(guide_id: str = "fictional-cawotte") -> dict:
        return {
            "guide_id": guide_id, "title": "Fictitious guide",
            "steps": [
                {
                    "source_step_id": "starting-step", "title": "Start",
                    "coordinates": [-5, 2],
                    "actions": [
                        {
                            "action_id": "prepare", "kind": "prepare",
                            "text": "Préparer 2 Ressource fictive",
                            "items": [{"name": "Ressource fictive", "quantity": 2}],
                        },
                        {
                            "action_id": "travel", "kind": "travel",
                            "text": "Aller en [-5,2]", "coordinates": [-5, 2],
                        },
                        {
                            "action_id": "npc", "kind": "talk",
                            "text": "Parler au PNJ fictif", "npc": "PNJ fictif",
                            "dialogue_choice": "Réponse B fictive",
                        },
                        {
                            "action_id": "item", "kind": "item",
                            "text": "Acheter Ressource fictive",
                            "items": [{"name": "Ressource fictive", "quantity": 3}],
                        },
                        {
                            "action_id": "fight", "kind": "combat",
                            "text": "Vaincre le Monstre fictif",
                            "monsters": [{"name": "Monstre fictif", "quantity": 2}],
                        },
                        {
                            "action_id": "save", "kind": "keep",
                            "text": "Conserver Ressource fictive",
                            "items": [{"name": "Ressource fictive", "quantity": 1}],
                        },
                        {
                            "action_id": "warn", "kind": "warning",
                            "text": "Avant de partir : vérifier le PNJ fictif",
                        },
                    ],
                },
                {
                    "source_step_id": "ending-step", "title": "Next",
                    "actions": [{
                        "action_id": "next", "kind": "talk",
                        "text": "Parler au second PNJ fictif",
                    }],
                },
            ],
        }

    @staticmethod
    def _service(progress_path: Path, route: dict) -> _SavedGuideService:
        service = _SavedGuideService(progress_path)
        service.cards = route["steps"]
        service.progress_id = route["id"]
        service.guide_id = route["id"]
        service.guide_title = route["source_guide_metadata"]["title"]
        # Preserve identities by source guide + source step, never page index.
        service.page_key = lambda card, index=0: card["manual_stage_id"]
        return service

    def test_preview_preserves_source_sections_and_clickable_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            route = project_authorized_guide(self._source())
            service = self._service(Path(temp) / "progress.json", route)
            def forbidden_provider(*_args):
                raise AssertionError("source sections must not be rebuilt by a legacy provider")
            service.manual_sections_for_card = forbidden_provider
            service.manual_lines_for_card = forbidden_provider
            sheet = None
            try:
                from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard
                sheet = SharedGuideManualCard(service, "character:1", service.cards[0], 0)
                QApplication.processEvents()
                rich = "\n".join(label.text() for label in sheet.findChildren(QLabel))
                visible = unescape(re.sub(r"<[^>]+>", "", rich))
                for expected in (
                    "Aller en [-5,2]", "PNJ fictif", "Monstre fictif",
                    "Conserver Ressource fictive", "Avant de partir",
                    "Réponse B fictive", "×3 Ressource fictive",
                    "×2 Monstre fictif",
                ):
                    self.assertIn(expected, visible)
                self.assertIn("travel-copy:-5,2", rich)
                self.assertIn("item-copy:Ressource%20fictive", rich)
                self.assertNotIn("Préparer 2 Ressource fictive", visible)
                self.assertIsNone(sheet.findChild(QFrame, "GuideManualWarningSection"))
                self.assertIsNotNone(sheet.findChild(QFrame, "GuideManualResourceSection"))
                self.assertTrue(sheet.findChildren(QLabel, "GuideManualSourceActionDetail"))
                # Check source evidence is retained alongside visible values.
                self.assertEqual(
                    sheet.card["manual_sections"]["now"][2]["source_action"]["items"][0]["quantity"],
                    3,
                )
            finally:
                if sheet is not None:
                    sheet.close()
                    sheet.deleteLater()
                    QApplication.processEvents()

    def test_source_without_preparation_never_calls_legacy_provider(self) -> None:
        # A source step with no prepare actions is a valid empty inventory.
        # Opening the shared preparation panel must not ask a legacy service
        # to invent rows or hydrate all Quest content.
        with tempfile.TemporaryDirectory() as temp:
            route = project_authorized_guide(self._source())
            service = self._service(Path(temp) / "progress.json", route)
            source_card = service.cards[1]
            self.assertEqual(source_card["a_preparer"], [])

            def forbidden_provider(*_args):
                raise AssertionError("source preparation must not fall back to legacy")

            service.manual_sections_for_card = forbidden_provider
            requirements = SharedGuideManualView._requirements_from_card(
                service, "character:1", source_card
            )
            self.assertEqual(requirements, ())

            # Existing optimized routes still have their historical fallback.
            legacy_card = dict(source_card)
            legacy_card.pop("manual_source")
            service.manual_sections_for_card = lambda *_args: {
                "prepare": [{"text": "Prépare 2 x Composant fictif"}]
            }
            legacy_requirements = SharedGuideManualView._requirements_from_card(
                service, "character:1", legacy_card
            )
            self.assertEqual(
                legacy_requirements[0][:3], (None, "Composant fictif", 2)
            )

    def test_source_resources_skip_legacy_quest_evidence(self) -> None:
        from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard

        source = self._source()
        source["steps"][0]["quest_ids"] = [123]
        card = project_authorized_guide(source)["steps"][0]

        def forbidden_evidence(_quest_id):
            raise AssertionError("source card must not hydrate legacy Quest evidence")

        service = SimpleNamespace(
            quest_provider=SimpleNamespace(guide_evidence=forbidden_evidence)
        )
        names = GuideUltimeManualCard._clickable_resource_names(service, card)
        self.assertIn("Ressource fictive", names)

        # Non-source guides still enrich their names from Quest evidence.
        legacy = dict(card)
        legacy.pop("manual_source")
        service.quest_provider.guide_evidence = lambda _quest_id: {
            "items": [{"name": "Objet historique fictif"}]
        }
        names = GuideUltimeManualCard._clickable_resource_names(service, legacy)
        self.assertIn("Objet historique fictif", names)

    def test_source_npc_uses_explicit_name_color_in_action_and_details(self) -> None:
        from app.modules.encyclopedia.views.guide_ultime_manual_view import NPC_COLOR
        from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard

        source = self._source()
        actions = source["steps"][0]["actions"]
        actions[2]["text"] = "Interagir avec le veilleur fictif"
        actions[2]["npc"] = "le veilleur fictif"
        actions.insert(3, {
            "action_id": "other-npc", "kind": "talk",
            "text": "Choisir une option au dialogue",
            "npc": "guide fictif", "dialogue_choice": "Option B fictive",
        })
        with tempfile.TemporaryDirectory() as temp:
            route = project_authorized_guide(source)
            service = self._service(Path(temp) / "progress.json", route)
            sheet = SharedGuideManualCard(
                service, "character:1", service.cards[0], 0
            )
            try:
                rich = "\\n".join(label.text() for label in sheet.findChildren(QLabel))
                for npc in ("le veilleur fictif", "guide fictif"):
                    self.assertIn(
                        f'<span style="color:{NPC_COLOR};"><b>{npc}</b></span>',
                        rich,
                    )
                self.assertIn("Option B fictive", rich)
            finally:
                sheet.close()
                sheet.deleteLater()
                QApplication.processEvents()

    def test_empty_source_sections_never_fall_back_to_legacy_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            route = project_authorized_guide(self._source())
            service = self._service(Path(temp) / "progress.json", route)
            source = dict(service.cards[0])
            source["manual_sections"] = {}
            def forbidden_provider(*_args):
                raise AssertionError("missing source sections cannot be replaced by legacy data")
            service.manual_sections_for_card = forbidden_provider
            service.manual_lines_for_card = forbidden_provider
            from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard
            sheet = SharedGuideManualCard(service, "character:1", source, 0)
            try:
                texts = "\n".join(label.text() for label in sheet.findChildren(QLabel))
                self.assertNotIn("Vaincre le Monstre fictif", texts)
                self.assertNotIn("Aller en [-5,2]", texts)
            finally:
                sheet.close()
                sheet.deleteLater()
                QApplication.processEvents()

    def test_existing_guides_still_use_their_original_section_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            route = project_authorized_guide(self._source())
            service = self._service(Path(temp) / "progress.json", route)
            ordinary = dict(service.cards[0])
            ordinary.pop("manual_source", None)
            called = []
            def original_provider(_key, _card):
                called.append(True)
                return {"now": [{"kind": "action", "text": "Existing guide route line"}]}
            service.manual_sections_for_card = original_provider
            from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualCard
            sheet = SharedGuideManualCard(service, "character:1", ordinary, 0)
            try:
                self.assertEqual(called, [True])
                texts = "\n".join(label.text() for label in sheet.findChildren(QLabel))
                self.assertIn("Existing guide route line", texts)
                self.assertNotIn("Vaincre le Monstre fictif", texts)
            finally:
                sheet.close()
                sheet.deleteLater()
                QApplication.processEvents()

    def test_source_validation_fills_selected_characters_and_reverses_manual_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            route = project_authorized_guide(self._source())
            service = self._service(path, route)
            participants = _ThreeParticipants()
            participants.save_selected_keys(("character:1", "character:2"))
            # Automatic evidence for one character cannot be overwritten by
            # a manual batch on the same source step.
            service.automatic.add(("character:1", 0))
            view = SharedGuideManualView(
                service, character_key="character:1",
                participant_service=participants,
            )
            try:
                view.show()
                view._show_index(0)
                QApplication.processEvents()
                view.validation_layout.itemAt(0).widget().click()
                QApplication.processEvents()
                stage_id = route["steps"][0]["manual_stage_id"]
                self.assertFalse(service.guide_progress.is_manual_step_completed(
                    "character:1", route["id"], stage_id,
                ))
                self.assertTrue(service.guide_progress.is_manual_step_completed(
                    "character:2", route["id"], stage_id,
                ))
                self.assertFalse(service.guide_progress.is_manual_step_completed(
                    "character:3", route["id"], stage_id,
                ))
                view._show_index(0)
                QApplication.processEvents()
                view.validation_layout.itemAt(0).widget().click()
                QApplication.processEvents()
                self.assertFalse(service.guide_progress.is_manual_step_completed(
                    "character:2", route["id"], stage_id,
                ))
                self.assertTrue(service.card_auto_complete(
                    "character:1", service.cards[0],
                ))
            finally:
                view.close()
                view.deleteLater()
                QApplication.processEvents()

    def test_source_without_selected_identity_never_writes_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            route = project_authorized_guide(self._source())
            service = self._service(path, route)
            participants = _ThreeParticipants()
            participants.save_selected_keys(())
            view = SharedGuideManualView(
                service, character_key="character:1",
                participant_service=participants,
            )
            try:
                view.show()
                view._show_index(0)
                QApplication.processEvents()
                view.validation_layout.itemAt(0).widget().click()
                QApplication.processEvents()
                self.assertFalse(path.exists())
                self.assertTrue(view.participants_button.isChecked())
            finally:
                view.close()
                view.deleteLater()
                QApplication.processEvents()

    def test_view_validation_uses_per_character_stable_source_step_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "progress.json"
            route = project_authorized_guide(self._source())
            service = self._service(path, route)
            participants = _ThreeParticipants()
            participants.save_selected_keys(("character:1",))
            view = SharedGuideManualView(
                service, character_key="character:1",
                participant_service=participants,
            )
            try:
                view.show()
                view._show_index(0)
                QApplication.processEvents()
                view.validation_layout.itemAt(0).widget().click()
                QApplication.processEvents()
                original_id = service.cards[0]["manual_stage_id"]
                self.assertTrue(service.guide_progress.is_manual_step_completed(
                    "character:1", route["id"], original_id,
                ))
                self.assertFalse(service.guide_progress.is_manual_step_completed(
                    "character:2", route["id"], original_id,
                ))
                different_guide = project_authorized_guide(self._source("fictional-other"))
                self.assertFalse(service.guide_progress.is_manual_step_completed(
                    "character:1", different_guide["id"],
                    different_guide["steps"][0]["manual_stage_id"],
                ))
                changed = self._source()
                changed["steps"].insert(0, {
                    "source_step_id": "inserted", "title": "Inserted",
                    "actions": [{
                        "action_id": "injected", "kind": "talk",
                        "text": "Fictional inserted step",
                    }],
                })
                changed_route = project_authorized_guide(changed)
                self.assertEqual(changed_route["steps"][1]["manual_stage_id"], original_id)
                self.assertTrue(service.guide_progress.is_manual_step_completed(
                    "character:1", route["id"], changed_route["steps"][1]["manual_stage_id"],
                ))
            finally:
                view.close()
                view.deleteLater()
                QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
