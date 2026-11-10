"""Focused Craft regressions: click flows, selection UX and image paths."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.craft_images import craft_image_item
from app.pages.craft_page import CraftPage, CraftResourceDialog
from local_dofus_data.normalizer import craft_category_for_item


class CraftFixesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_page(self):
        page = CraftPage(Mock(), defer_runtime=True)
        self.addCleanup(page.deleteLater)
        return page

    def test_click_any_job_opens_leveling_automatically(self):
        page = self.make_page()
        page.jobs = [{"name": "Mineur"}, {"name": "Forgeron"}]
        page.guides = {"guides": {
            "Mineur": {"entries": [{"craft": {"name": "Fer"}}]},
            "Forgeron": {"entries": [{"craft": {"name": "Épée"}}]},
        }}
        with (
            patch.object(page, "find_job_resource", return_value={"name": "Fer"}),
            patch.object(page, "open_leveling_dialog") as open_dialog,
        ):
            page.show()
            page.refresh_jobs()
            QApplication.processEvents()
            for job in ("Mineur", "Forgeron"):
                with self.subTest(job=job):
                    buttons = [page.job_buttons_layout.itemAt(index).widget()
                               for index in range(page.job_buttons_layout.count())]
                    button = next(button for button in buttons if button.text() == job)
                    QTest.mouseClick(button, Qt.LeftButton)
                    QTest.qWait(35)
                    open_dialog.assert_called_with(job)
            self.assertEqual(open_dialog.call_count, 2)
            page.close()

    def test_missing_leveling_is_explicit_not_silent(self):
        page = self.make_page()
        page.guides = {"guides": {}}
        with (
            patch("app.pages.craft_page.LEVELING_FILE", Path("/missing/metiers_leveling.json")),
            patch("app.pages.craft_page.QMessageBox.warning", return_value=QMessageBox.Ok) as warning,
        ):
            page.open_leveling_dialog("Mineur")
            warning.assert_called_once()
            self.assertIn("Fichier de guides absent", warning.call_args.args[2])

    def test_selection_order_and_scroll_survive_append(self):
        page = self.make_page()
        page.resize(1100, 670)
        page.show()
        for idx in range(1, 55):
            page.selection[idx] = {"item": {"ankama_id": idx, "name": f"Objet {55 - idx}"}, "quantity": 1}
        page.refresh_selection()
        QApplication.processEvents()
        scroll = page.selection_list.verticalScrollBar()
        self.assertGreater(scroll.maximum(), 0)
        scroll.setValue(min(150, scroll.maximum()))
        before = scroll.value()
        with patch.object(page, "save_selection"):
            page.add_item({"ankama_id": 99, "name": "A en dernier"}, 1)
        self.assertEqual([page.selection_list.item(i).data(Qt.UserRole)
                          for i in range(page.selection_list.count())], [*range(1, 55), 99])
        self.assertEqual(scroll.value(), before)
        page.close()

    def test_escape_asks_confirmation_and_no_is_safe(self):
        dialog = CraftResourceDialog({}, [])
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        with patch("app.pages.craft_page.QMessageBox.question",
                   side_effect=[QMessageBox.No, QMessageBox.Yes]) as question:
            QTest.keyClick(dialog, Qt.Key_Escape)
            self.assertTrue(dialog.isVisible())
            QTest.keyClick(dialog, Qt.Key_Escape)
            self.assertFalse(dialog.isVisible())
            self.assertEqual(question.call_count, 2)

    def test_flat_legacy_craft_icon_resolves_nested_weapon_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weapon_dir = root / "data" / "images" / "items" / "armes"
            weapon_dir.mkdir(parents=True)
            icon = weapon_dir / "987.png"
            icon.write_bytes(b"fixture")
            item = {"name": "Épée de test", "type": "Épée",
                    "image_path": "data/images/items/987.png"}
            result = craft_image_item(item, root=root)
            self.assertEqual(Path(result["image_path"]), icon)
            self.assertEqual(item["image_path"], "data/images/items/987.png")

    def test_existing_guide_constructs_and_shows_leveling_dialog(self):
        page = self.make_page()
        page.guides = {"guides": {"Forgeron": {"entries": [{"craft": {"name": "Épée"}}]}}}
        with patch("app.pages.craft_page.LevelingDialog") as dialog:
            page.open_leveling_dialog("Forgeron")
        dialog.assert_called_once()
        dialog.return_value.exec.assert_called_once()

    def test_text_search_filters_typographic_and_ascii_apostrophes(self):
        page = self.make_page()
        page._runtime_ready = True
        page.items = [{
            "name": "L’Épée d’Âme", "type": "Épée",
            "_search_name": "l_epee_d_ame", "_craft_category": "equipment",
        }]
        page.search.setText("L'EPÉE D'AME")
        page.search_timer.stop()
        page.refresh_results()
        page.result_batch_timer.stop()
        self.assertEqual(len(page._pending_result_items), 1)

    def test_previous_resource_dialog_finish_does_not_clear_new_dialog(self):
        page = self.make_page()
        page.selection = {42: {"item": {"ankama_id": 42, "name": "Épée"}, "quantity": 1}}
        recipe = {"found": True, "ingredients": [{
            "name": "Fer", "quantity": 2, "image_path": "",
        }]}
        with patch("app.pages.craft_page.local_data_cache.get_recipe_for_item", return_value=recipe):
            page.show_resources()
            previous = page.resource_dialog
            page.show_resources()
            current = page.resource_dialog
            self.assertIsNot(previous, current)
            previous.finished.emit(0)
            self.assertIs(page.resource_dialog, current)
            current.accept()

    def test_image_fallback_does_not_guess_between_duplicate_sprites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ("armes", "divers"):
                folder = root / "data" / "images" / "items" / directory
                folder.mkdir(parents=True)
                (folder / "777.png").write_bytes(b"fixture")
            item = {"type": "Objet mystère", "image_path": "data/images/items/777.png"}
            self.assertIs(craft_image_item(item, root=root), item)

    def test_craft_category_identifies_weapon_types_without_name_false_positives(self):
        for kind in ("Épée", "Arc", "Dagues", "Marteau", "Pelle", "Baguette"):
            with self.subTest(kind=kind):
                self.assertEqual(craft_category_for_item({
                    "name": "Objet", "type": kind, "category": "Divers",
                }), "equipment")
        self.assertEqual(craft_category_for_item({
            "name": "Parchemin", "type": "Ressource", "category": "Divers",
        }), "resource")


if __name__ == "__main__":
    unittest.main()
