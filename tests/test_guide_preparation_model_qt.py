from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from tests.test_guide_manual_selected_validation import _SavedGuideService, _ThreeParticipants


class _RealReadyStore(_SavedGuideService):
    """Tiny authored cards and a real atomic on-disk GuideProgressService."""

    def manual_checked(self, character_key: str, key: str) -> bool:
        return self.guide_progress.is_manual_step_completed(
            character_key, self.progress_id, key,
        )

    def set_manual_checked(self, character_key: str, key: str, checked: bool) -> None:
        self.guide_progress.set_manual_step_completed(
            character_key, self.progress_id, key, checked,
        )


class GuidePreparationQtFocusedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "progress.json"
        self.service = _RealReadyStore(self.path)
        self.service.cards[0]["a_preparer"] = [
            {"item_id": 123, "name": "Potion de rappel", "quantity": 2,
             "consumable": True},
        ]
        self.participants = _ThreeParticipants()
        self.view = None

    def tearDown(self):
        if self.view is not None:
            self.view.close()
            self.view.deleteLater()
            QApplication.processEvents()
        self.temp.cleanup()

    def _view(self):
        self.view = SharedGuideManualView(
            self.service, character_key="character:1",
            participant_service=self.participants,
        )
        self.view.resize(1100, 740)
        self.view.show()
        QApplication.processEvents()
        self.view.preparation_button.setChecked(True)
        QApplication.processEvents()
        return self.view

    def test_six_verified_participants_can_be_ready_without_anonymous_writes(self):
        from types import SimpleNamespace

        class SixParticipants(_ThreeParticipants):
            def available_characters(self):
                return tuple(SimpleNamespace(
                    key=f"character:{index}", label=f"Perso {index}", connected=False
                ) for index in range(1, 7))

        self.participants = SixParticipants()
        self.participants.save_selected_keys(tuple(
            f"character:{index}" for index in range(1, 7)
        ))
        view = self._view()
        self.assertEqual(len(view._preparation_needs), 1)
        need = view._preparation_needs[0]
        self.assertEqual(len(need.required_by_character), 6)
        key = view._ready_progress_key(need)
        ready = view.preparation_panel.findChild(QToolButton, "GuidePreparationReady")
        self.assertTrue(ready.isEnabled())
        ready.click()
        QApplication.processEvents()
        persisted = GuideProgressService(self.path)
        self.assertTrue(all(
            persisted.is_manual_step_completed(
                f"character:{index}", self.service.progress_id, key
            )
            for index in range(1, 7)
        ))
        self.assertFalse(persisted.is_manual_step_completed(
            "character:7", self.service.progress_id, key,
        ))

    def test_many_preparation_rows_remain_bounded_in_qt(self):
        self.participants.save_selected_keys(("character:1",))
        self.service.cards[0]["a_preparer"] = [
            {"item_id": index + 10000, "name": f"Objet témoin {index}",
             "quantity": 1}
            for index in range(235)
        ]
        view = self._view()
        self.assertEqual(len(view._preparation_needs), 235)
        rows = view.preparation_panel.findChildren(QToolButton, "GuidePreparationReady")
        self.assertLessEqual(len(rows), 80)
        self.assertIsNotNone(view.preparation_panel.findChild(
            QLabel, "GuidePreparationEmpty"
        ) if not view._preparation_needs else view.preparation_panel.findChild(
            QToolButton, "GuidePreparationReady"
        ))
        more = view.preparation_panel.findChild(
            __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton,
            "GuidePreparationShowMore",
        )
        self.assertIsNotNone(more)
        more.click()
        QApplication.processEvents()
        self.assertLessEqual(
            len(view.preparation_panel.findChildren(QToolButton, "GuidePreparationReady")),
            160,
        )

    def test_readonly_without_selected_character(self):
        self.participants.save_selected_keys(())
        view = self._view()
        self.assertEqual(view.selected_participant_keys(), ())
        self.assertEqual(view._preparation_needs, ())
        self.assertTrue(view._preparation_preview)
        self.assertFalse(view.preparation_panel.findChildren(
            QToolButton, "GuidePreparationReady",
        ))
        label = view.preparation_panel.findChild(QLabel, "GuidePreparationEmpty")
        self.assertIsNotNone(label)
        self.assertIn("Aperçu des préparatifs", label.text())
        self.assertFalse(self.path.exists())

    def test_atomic_team_ready_and_undo_survive_real_reload(self):
        self.participants.save_selected_keys(("character:1", "character:2"))
        view = self._view()
        needs = view._preparation_needs
        self.assertEqual(len(needs), 1)
        self.assertEqual(
            {key: qty for key, qty in needs[0].required_by_character},
            {"character:1": 2, "character:2": 2},
        )
        key = view._ready_progress_key(needs[0])
        button = view.preparation_panel.findChild(QToolButton, "GuidePreparationReady")
        self.assertIsNotNone(button)
        self.assertTrue(button.isEnabled())
        button.click()
        QApplication.processEvents()
        persisted = GuideProgressService(self.path)
        for character in ("character:1", "character:2"):
            self.assertTrue(persisted.is_manual_step_completed(
                character, self.service.progress_id, key,
            ))
        self.assertFalse(persisted.is_manual_step_completed(
            "character:3", self.service.progress_id, key,
        ))
        view._load_preparation_needs()
        view._render_preparation("Tout")
        QApplication.processEvents()
        undo_button = view.preparation_panel.findChild(QToolButton, "GuidePreparationReady")
        self.assertIsNotNone(undo_button)
        self.assertTrue(undo_button.isChecked())
        undo_button.click()
        QApplication.processEvents()
        persisted.reload()
        for character in ("character:1", "character:2", "character:3"):
            self.assertFalse(persisted.is_manual_step_completed(
                character, self.service.progress_id, key,
            ))


if __name__ == "__main__":
    unittest.main()
