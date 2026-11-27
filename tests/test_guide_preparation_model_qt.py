from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QApplication, QLabel, QPushButton, QSpinBox, QToolButton

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
from app.ui.components import fit_unity_number_spinbox
from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX, UNITY_SIZES_PX
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
        self.view.global_details_button.setChecked(True)
        self.view.preparation_button.setChecked(True)
        QApplication.processEvents()
        self.assertTrue(self.view.global_details_panel.isVisible())
        self.assertTrue(self.view.preparation_panel.isVisible())
        return self.view

    def test_compact_preparation_is_content_sized_from_dev_ui_tokens(self):
        from app.ui.theme import atlas_stylesheet

        old_style = self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet, old_style)
        self.app.setStyleSheet(atlas_stylesheet())
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        quantity = view.preparation_panel.findChild(QSpinBox, "GuidePreparationQuantity")
        name = view.preparation_panel.findChild(QPushButton, "GuidePreparationItemCopy")
        ready = view.preparation_panel.findChild(QCheckBox, "GuidePreparationReady")
        from app.ui.components import AtlasGuidePreparationPanel
        self.assertIsInstance(view.preparation_panel, AtlasGuidePreparationPanel)
        self.assertIsNotNone(quantity)
        self.assertIsNotNone(name)
        self.assertIsNotNone(ready)
        self.assertEqual(view.preparation_filter.height(), UNITY_SIZES_PX["control_compact"])
        self.assertEqual(name.height(), UNITY_SIZES_PX["control_compact"])
        self.assertEqual(quantity.suffix(), "/2")
        self.assertLess(quantity.width(), 100)
        self.assertEqual(quantity.width(), fit_unity_number_spinbox(quantity))
        self.assertGreaterEqual(
            view.preparation_scroll.height(),
            UNITY_CONTROL_SIZES_PX["guide_preparation_min_height"],
        )
        self.assertLessEqual(
            view.preparation_scroll.height(), view.preparation_scroll.maximumHeight()
        )

        # Six digits must fit rather than being cut off by a fixed width.
        compact_width = quantity.width()
        quantity.setRange(0, 123456)
        quantity.setSuffix("/123456")
        fit_unity_number_spinbox(quantity)
        self.assertGreater(quantity.width(), compact_width)

    def test_guide_numeric_editors_cannot_reintroduce_a_black_native_inset(self):
        from app.ui.theme import atlas_stylesheet

        style = atlas_stylesheet()
        for role in ("GuideCompactPageJump", "GuidePreparationQuantity"):
            self.assertIn(f"QSpinBox#{role}", style)
        match = re.search(
            r"QSpinBox#GuideCompactPageJump QLineEdit,\s*"
            r"QSpinBox#GuidePreparationQuantity QLineEdit\s*\{([^}]+)\}",
            style,
        )
        self.assertIsNotNone(match)
        self.assertIn("background: transparent", match.group(1))
        self.assertIn("border: none", match.group(1))

    def test_preparation_images_use_the_exact_id_without_generic_inventory_icon(self):
        view = self._view()
        image = Path(self.temp.name) / "item-12003.png"
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.white)
        self.assertTrue(pixmap.save(str(image), "PNG"))

        with patch(
            "app.modules.encyclopedia.views.shared_manual_guide_view.item_icon_path",
            return_value=image,
        ) as resolver:
            item = view._copyable_preparation_item("Potion de rappel", "Potion de rappel", 12003)
            self.assertFalse(item.icon().isNull())
            resolver.assert_called_once_with(12003)

        missing_id = view._copyable_preparation_item("Objet inconnu", "Objet inconnu", None)
        self.assertTrue(missing_id.icon().isNull())
        with patch(
            "app.modules.encyclopedia.views.shared_manual_guide_view.item_icon_path",
            return_value=None,
        ):
            missing_artwork = view._copyable_preparation_item(
                "Objet sans image livrée", "Objet sans image livrée", 999999999,
            )
        self.assertTrue(missing_artwork.icon().isNull())

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
        ready = view.preparation_panel.findChild(QCheckBox, "GuidePreparationReady")
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
        rows = view.preparation_panel.findChildren(QCheckBox, "GuidePreparationReady")
        self.assertLessEqual(len(rows), 80)
        self.assertIsNotNone(view.preparation_panel.findChild(
            QLabel, "GuidePreparationEmpty"
        ) if not view._preparation_needs else view.preparation_panel.findChild(
            QCheckBox, "GuidePreparationReady"
        ))
        more = view.preparation_panel.findChild(
            __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton,
            "GuidePreparationShowMore",
        )
        self.assertIsNotNone(more)
        more.click()
        QApplication.processEvents()
        self.assertLessEqual(
            len(view.preparation_panel.findChildren(QCheckBox, "GuidePreparationReady")),
            160,
        )

    def test_compact_route_preview_never_hydrates_card(self):
        import json
        import zlib

        self.participants.save_selected_keys(())
        stage = {
            "id": "INC-mini",
            "resource_plan": {"items": [
                {"name": "Pierre d'âme parfaite", "quantity": 3},
            ]},
        }
        self.service.cards[0]["a_preparer"] = []
        self.service.cards[0]["_manual_stage_payload"] = zlib.compress(
            json.dumps(stage, ensure_ascii=False).encode("utf-8"),
        )
        card = self.service.cards[0]
        initial_keys = set(card)
        view = self._view()
        self.assertIn(
            ("Pierres d'âme", "Pierre d'âme parfaite", 3, None),
            view._preparation_preview,
        )
        self.assertEqual(set(card), initial_keys)
        self.assertFalse(self.path.exists())

    def test_non_material_gates_have_filter_and_no_fake_quantity(self):
        self.participants.save_selected_keys(("character:1",))
        self.service.cards[0]["hard_runtime_gates"] = [
            {"condition": "Être niveau 100"},
        ]
        view = self._view()
        gates = [x for x in view._preparation_needs if x.category == "Prérequis"]
        self.assertEqual(len(gates), 1)
        self.assertIsNone(gates[0].required_total)
        self.assertIn("Prérequis", [
            view.preparation_filter.itemText(index)
            for index in range(view.preparation_filter.count())
        ])
        view.preparation_filter.setCurrentText("Prérequis")
        self.assertEqual(view.preparation_filter.currentText(), "Prérequis")
        QApplication.processEvents()
        # Prerequisites are copyable buttons, not QLabel text. Inspect the
        # actual visible control without changing its no-quantity contract.
        items = view.preparation_panel.findChildren(QPushButton, "GuidePreparationItemCopy")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].text(), "Être niveau 100")
        items[0].click()
        self.assertEqual(QApplication.clipboard().text(), "Être niveau 100")
        self.assertNotIn("? ×", items[0].text())

    def test_readonly_without_selected_character(self):
        self.participants.save_selected_keys(())
        view = self._view()
        self.assertEqual(view.selected_participant_keys(), ())
        self.assertEqual(view._preparation_needs, ())
        self.assertTrue(view._preparation_preview)
        self.assertFalse(view.preparation_panel.findChildren(
            QCheckBox, "GuidePreparationReady",
        ))
        label = view.preparation_panel.findChild(QLabel, "GuidePreparationEmpty")
        self.assertIsNotNone(label)
        self.assertIn("Aperçu des préparatifs", label.text())
        self.assertFalse(self.path.exists())

    def test_open_preparation_rebuilds_rows_when_guide_progress_refreshes(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        previous = view.preparation_panel.findChild(
            QPushButton, "GuidePreparationItemCopy",
        )
        self.assertEqual(previous.text(), "Potion de rappel")

        # A data/progress refresh while the drawer stays open must replace
        # stale needs and preserve the active category filter.
        self.service.cards[0]["a_preparer"] = [
            {"item_id": 124, "name": "Clef du donjon", "quantity": 3},
        ]
        view.refresh()
        QApplication.processEvents()

        current = view.preparation_panel.findChild(
            QPushButton, "GuidePreparationItemCopy",
        )
        self.assertIsNotNone(current)
        self.assertEqual(current.text(), "Clef du donjon")
        self.assertEqual(view._preparation_needs[0].required_total, 3)
        self.assertEqual(view.preparation_bar.maximum(), 1)

    def test_empty_preparation_is_hidden_on_first_parent_open(self):
        self.participants.save_selected_keys(("character:1",))
        for card in self.service.cards:
            card["a_preparer"] = []
        view = SharedGuideManualView(self.service, character_key="character:1",
                                     participant_service=self.participants)
        self.view = view
        view.show()
        QApplication.processEvents()
        with patch.object(view, "_render_preparation", wraps=view._render_preparation) as render:
            view.global_details_button.click()
            QApplication.processEvents()
            render.assert_not_called()
        self.assertTrue(view._preparation_loaded)
        self.assertFalse(view.preparation_button.isVisible())
        self.assertTrue(view.reading_header.summary_button.isVisible())

    def test_closed_preparation_defers_rebuild_until_reopened(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        view.preparation_button.setChecked(False)
        self.service.cards[0]["a_preparer"] = [
            {"item_id": 125, "name": "Potion nouvelle", "quantity": 5},
        ]
        with patch.object(view, "_render_preparation", wraps=view._render_preparation) as render:
            view.refresh()
            self.assertTrue(view._preparation_loaded)
            render.assert_not_called()
            view.preparation_button.setChecked(True)
            QApplication.processEvents()
            render.assert_called_once()
        self.assertTrue(view._preparation_loaded)
        self.assertEqual(view._preparation_needs[0].required_total, 5)
        button = view.preparation_panel.findChild(
            QPushButton, "GuidePreparationItemCopy",
        )
        self.assertEqual(button.text(), "Potion nouvelle")

    def test_collapsed_global_parent_defers_preparation_until_reopened(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        view.global_details_button.setChecked(False)
        self.assertTrue(view.preparation_button.isChecked())
        self.assertFalse(view.preparation_panel.isVisible())
        self.service.cards[0]["a_preparer"] = [
            {"item_id": 125, "name": "Potion nouvelle", "quantity": 5},
        ]
        with patch.object(view, "_load_preparation_needs",
                          wraps=view._load_preparation_needs) as load:
            view.refresh()
            load.assert_not_called()
            self.assertFalse(view._preparation_loaded)
            view.global_details_button.setChecked(True)
            QApplication.processEvents()
            load.assert_called_once()
        self.assertTrue(view.preparation_panel.isVisible())
        self.assertEqual(view._preparation_needs[0].required_total, 5)

    def test_changing_team_discards_old_quantity_drafts(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        counter = view.preparation_panel.findChild(QSpinBox, "GuidePreparationQuantity")
        self.assertIsNotNone(counter)
        counter.setValue(1)
        self.assertEqual(len(view._preparation_quantity_drafts), 1)

        view._participant_toggled("character:2", True)
        QApplication.processEvents()
        self.assertEqual(view._preparation_quantity_drafts, {})
        next_counter = view.preparation_panel.findChild(
            QSpinBox, "GuidePreparationQuantity",
        )
        self.assertIsNotNone(next_counter)
        self.assertEqual(next_counter.value(), 0)
        self.assertEqual(next_counter.suffix(), "/4")

    def test_external_team_change_clears_drafts_and_rejects_stale_ready_click(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        old_need = view._preparation_needs[0]
        counter = view.preparation_panel.findChild(QSpinBox, "GuidePreparationQuantity")
        counter.setValue(1)
        view.refresh()
        self.assertEqual(view._preparation_quantity_drafts[old_need.item_key], 1)

        # A superset is especially important: checking the old row used to
        # write a valid but incomplete subset of the new team's requirement.
        self.participants.save_selected_keys(("character:1", "character:2"))
        with patch.object(self.service.guide_progress, "set_manual_steps_for_characters") as write:
            view._set_preparation_draft(old_need, 2)
            view._set_need_ready(old_need, True)
            write.assert_not_called()
        QApplication.processEvents()
        self.assertEqual(view._preparation_quantity_drafts, {})
        self.assertEqual(view._preparation_needs[0].required_total, 4)
        next_counter = view.preparation_panel.findChild(QSpinBox, "GuidePreparationQuantity")
        self.assertEqual(next_counter.value(), 0)
        self.assertEqual(next_counter.suffix(), "/4")
        self.assertEqual(view.preparation_bar.value(), 0)

    def test_browsing_character_change_refreshes_open_preparation_once(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        counter = view.preparation_panel.findChild(QSpinBox, "GuidePreparationQuantity")
        counter.setValue(1)
        self.assertEqual(len(view._preparation_quantity_drafts), 1)

        view.set_character_key("character:2")
        QApplication.processEvents()
        self.assertTrue(view._preparation_loaded)
        self.assertEqual(view._preparation_quantity_drafts, {})
        current = view.preparation_panel.findChild(
            QSpinBox, "GuidePreparationQuantity",
        )
        self.assertIsNotNone(current)
        self.assertEqual(current.value(), 0)
        self.assertEqual(current.suffix(), "/2")

    def test_final_sheet_completion_clears_open_remaining_preparation(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        self.assertEqual(len(view._preparation_needs), 1)

        for index, card in enumerate(self.service.cards):
            self.service.guide_progress.set_manual_step_completed(
                "character:1", self.service.progress_id,
                self.service.page_key(card, index), True,
            )
        view._follow_active_after_progress_change()
        QApplication.processEvents()

        self.assertEqual(view._preparation_needs, ())
        self.assertEqual(view.preparation_progress_label.text(), "—")
        self.assertEqual(view.global_progress_label.text(), "100 %")
        self.assertFalse(view.preparation_button.isVisible())
        self.assertFalse(view.preparation_panel.isVisible())
        self.assertFalse(any(button.isVisible() for button in view.preparation_panel.findChildren(
            QPushButton, "GuidePreparationItemCopy",
        )))

    def test_missing_selected_character_keeps_copyable_readonly_preview(self):
        # Selection can outlive a removed profile, which must not hide the
        # actual preparation or offer save controls for a deleted identity.
        self.participants.save_selected_keys(("character:999",))
        view = self._view()
        self.assertEqual(view._progress_participant_keys(), ())
        self.assertEqual(view._preparation_needs, ())
        self.assertTrue(view._preparation_preview)
        copy_items = view.preparation_panel.findChildren(
            QPushButton, "GuidePreparationItemCopy",
        )
        self.assertTrue(copy_items)
        self.assertIn("Potion de rappel", copy_items[0].text())
        self.assertFalse(view.preparation_panel.findChildren(
            QCheckBox, "GuidePreparationReady",
        ))

    def test_ready_updates_existing_row_and_category_without_rebuilding_widgets(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        from app.ui.components import AtlasGuidePreparationRow
        row = view.preparation_panel.findChild(AtlasGuidePreparationRow)
        details = row.findChild(QToolButton, "GuidePreparationDetailsButton")
        details.click()
        with patch.object(view, "_render_preparation", wraps=view._render_preparation) as rebuild:
            row.ready_button.click()
            QApplication.processEvents()
            rebuild.assert_not_called()
        self.assertIs(view.preparation_panel.findChild(AtlasGuidePreparationRow), row)
        self.assertTrue(details.isChecked())
        self.assertEqual(row.quantity_editor.value(), 2)
        self.assertEqual(row.status_label.text(), "Prêt")
        self.assertEqual(view.preparation_bar.value(), 1)
        self.assertEqual(view.preparation_panel.findChild(
            QLabel, "GuidePreparationSummaryCount",
        ).text(), "1 / 1 prêts")

    def test_rejected_ready_write_does_not_claim_draft_quantity_or_ready(self):
        self.participants.save_selected_keys(("character:1",))
        view = self._view()
        from app.ui.components import AtlasGuidePreparationRow
        row = view.preparation_panel.findChild(AtlasGuidePreparationRow)
        row.quantity_editor.setValue(1)
        with patch.object(self.service.guide_progress, "set_manual_steps_for_characters",
                          side_effect=RuntimeError("concurrent update")):
            row.ready_button.click()
        self.assertFalse(row.ready_button.isChecked())
        self.assertEqual(row.quantity_editor.value(), 1)
        self.assertEqual(row.status_label.text(), "Manque 1")
        self.assertEqual(view.preparation_bar.value(), 0)

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
        button = view.preparation_panel.findChild(QCheckBox, "GuidePreparationReady")
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
        undo_button = view.preparation_panel.findChild(QCheckBox, "GuidePreparationReady")
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
