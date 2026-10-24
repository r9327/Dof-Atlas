from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
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
        self.assertFalse(self.view.validation_layout.itemAt(0).widget().isEnabled())
        self.assertIn("Choisir", self.view.validation_layout.itemAt(0).widget().text())
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
        control = self.view.validation_layout.itemAt(0).widget()
        self.assertEqual(control.text(), "Valider")
        control.click()
        self.assertTrue(self._check("character:1"))
        self.assertTrue(self._check("character:2"))
        self.assertFalse(self._check("character:3"))

        self.view._participant_buttons["character:1"].click()
        QApplication.processEvents()
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
        self.assertEqual(self.view.route_progress_label.text(), "0 / 2")
        self.assertEqual(self.view.progress_donut._percent, 0)

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
        self.assertEqual(self.view.route_progress_label.text(), "2 / 2")
        self.assertFalse(self.view.current_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
