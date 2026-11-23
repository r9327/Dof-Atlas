"""Real Qt interaction and lifecycle audit for every shipped popup family."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

import main as atlas_main
from app.modules.encyclopedia.views.guides_view import SolutionImageLabel
from app.pages.craft_page import (
    CraftResourceDialog,
    ItemSetDialog,
    LevelingDialog,
    RouteDialog,
)
from app.pages.dev_ui_page import DevUiPage
from app.storage import ZaapWidget
from app.ui.preload_popup import PreloadProgressPopup
from app.ui.theme import atlas_stylesheet


class PopupInteractionInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(atlas_stylesheet())

    def setUp(self) -> None:
        self._baseline_top_levels = set(self.app.topLevelWidgets())

    def pump(self, turns: int = 4) -> None:
        for _ in range(turns):
            self.app.processEvents()

    def button(self, widget: QWidget, text: str) -> QAbstractButton:
        for candidate in widget.findChildren(QAbstractButton):
            if candidate.text() == text:
                return candidate
        self.fail(f"Button {text!r} missing from {type(widget).__name__}")

    def dispose(self, *widgets: QWidget) -> None:
        tracked = [widget for widget in widgets if widget is not None and isValid(widget)]
        for widget in tracked:
            widget.close()
            widget.deleteLater()
        self.pump()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.pump()
        for widget in tracked:
            self.assertFalse(isValid(widget), f"Qt wrapper survived: {type(widget).__name__}")
        leaked = [
            widget for widget in self.app.topLevelWidgets()
            if widget not in self._baseline_top_levels and widget.isVisible()
        ]
        self.assertEqual(leaked, [], f"Visible popup ghosts: {leaked!r}")

    def test_preload_popup_handoff_never_leaves_modal_ghost(self) -> None:
        for _ in range(3):
            host = QWidget()
            host.show()
            popup = PreloadProgressPopup(host)
            popup.begin({"quests": "READY", "encyclopedia": "LOADING", "craft": "IDLE"})
            self.pump()
            self.assertTrue(popup.isVisible())
            self.assertTrue(popup.isModal())
            popup.handoff()
            self.pump()
            self.assertFalse(popup.isVisible())
            self.dispose(popup, host)

    def test_close_action_dialog_buttons_are_clickable_and_terminal(self) -> None:
        for label, expected, accepted in (
            ("Annuler", "cancel", False),
            ("Quitter", "quit", True),
            ("Réduire", "minimize", True),
        ):
            dialog = atlas_main.CloseActionDialog()
            dialog.show()
            QTest.mouseClick(self.button(dialog, label), Qt.LeftButton)
            self.pump()
            self.assertFalse(dialog.isVisible())
            self.assertEqual(dialog._selected_action, expected)
            self.assertEqual(dialog.result() == QDialog.Accepted, accepted)
            self.dispose(dialog)

    def test_standard_question_and_warning_buttons_close_cleanly(self) -> None:
        for _ in range(3):
            question = QMessageBox(
                QMessageBox.Question, "Confirmer", "Continuer ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            question.show()
            QTest.mouseClick(question.button(QMessageBox.No), Qt.LeftButton)
            self.pump()
            self.assertFalse(question.isVisible())
            self.dispose(question)

            warning = QMessageBox(
                QMessageBox.Warning, "Indisponible", "Action indisponible.",
                QMessageBox.Ok,
            )
            warning.show()
            QTest.mouseClick(warning.button(QMessageBox.Ok), Qt.LeftButton)
            self.pump()
            self.assertFalse(warning.isVisible())
            self.dispose(warning)

    def test_craft_resource_dialog_controls_close_and_escape_paths(self) -> None:
        for _ in range(3):
            dialog = CraftResourceDialog({"Fer": {"quantity": 8}}, [])
            dialog.show()
            QTest.mouseClick(self.button(dialog, "Tout désélectionner"), Qt.LeftButton)
            self.assertFalse(dialog.resource_checks[0].isChecked())
            QTest.mouseClick(self.button(dialog, "Tout sélectionner"), Qt.LeftButton)
            self.assertTrue(dialog.resource_checks[0].isChecked())
            with patch("app.pages.craft_page.QMessageBox.question", return_value=QMessageBox.No):
                QTest.keyClick(dialog, Qt.Key_Escape)
            self.assertTrue(dialog.isVisible())
            with patch("app.pages.craft_page.QMessageBox.question", return_value=QMessageBox.Yes):
                QTest.keyClick(dialog, Qt.Key_Escape)
            self.pump()
            self.assertFalse(dialog.isVisible())
            self.dispose(dialog)

    def test_item_set_actions_are_clickable_without_lingering_dialog(self) -> None:
        item_set = {
            "name_fr": "Panoplie test",
            "items": [{"name": "Coiffe", "level": 10}, {"name": "Cape", "level": 11}],
        }
        for _ in range(3):
            added: list[str] = []
            dialog = ItemSetDialog(
                item_set,
                lambda item, _quantity: added.append(str(item["name"])),
            )
            dialog.show()
            QTest.mouseClick(self.button(dialog, "+"), Qt.LeftButton)
            self.assertEqual(added, ["Coiffe"])
            QTest.mouseClick(self.button(dialog, "Ajouter la panoplie"), Qt.LeftButton)
            self.pump()
            self.assertEqual(added, ["Coiffe", "Coiffe", "Cape"])
            self.assertFalse(dialog.isVisible())
            self.dispose(dialog)

    def test_leveling_actions_copy_and_close_cleanly(self) -> None:
        guide = {
            "source": "atlas-local",
            "kind": "harvest",
            "entries": [{"level_range": "1-20", "craft": {"name": "Ortie"}}],
        }
        for _ in range(3):
            dialog = LevelingDialog(
                "Alchimiste", guide, lambda _name: None, lambda _craft: None,
            )
            dialog.show()
            QTest.mouseClick(self.button(dialog, "Copier"), Qt.LeftButton)
            self.assertEqual(QApplication.clipboard().text(), "Ortie")
            QTest.mouseClick(self.button(dialog, "Fermer"), Qt.LeftButton)
            self.pump()
            self.assertFalse(dialog.isVisible())
            self.dispose(dialog)

    def test_route_dialog_navigation_and_escape_do_not_leave_ghost(self) -> None:
        for _ in range(3):
            dialog = RouteDialog("Mineur", {"name": "Fer"})
            dialog.show()
            QTest.mouseClick(self.button(dialog, ">"), Qt.LeftButton)
            QTest.mouseClick(self.button(dialog, "<"), Qt.LeftButton)
            self.assertEqual(dialog.step, 1)
            QTest.keyClick(dialog, Qt.Key_Escape)
            self.pump()
            self.assertFalse(dialog.isVisible())
            self.dispose(dialog)

    def test_zaap_suggestion_click_and_escape_close_popup(self) -> None:
        for _ in range(3):
            commands: list[str] = []
            host = QWidget()
            layout = QVBoxLayout(host)
            zaap = ZaapWidget(
                lambda _message: None,
                start_callback=lambda command, *_args: commands.append(command) or True,
                parent=host,
            )
            layout.addWidget(zaap)
            zaap.zaaps = [{"name": "Astrub", "label": "Astrub", "posX": 5, "posY": -18}]
            host.show()
            zaap.refresh_results("Astrub")
            zaap.show_suggestions()
            self.pump()
            self.assertTrue(zaap.suggestion_popup.isVisible())
            item = zaap.suggestion_popup.item(0)
            QTest.mouseClick(
                zaap.suggestion_popup.viewport(), Qt.LeftButton,
                pos=zaap.suggestion_popup.visualItemRect(item).center(),
            )
            self.pump()
            self.assertEqual(commands, ["/zaap 5,-18"])
            self.assertFalse(zaap.suggestion_popup.isVisible())
            zaap.search_input.setText("Astrub")
            zaap.populate_suggestions(zaap.zaaps)
            zaap._suppress_autoshow_after_launch = False
            zaap.show_suggestions()
            QTest.keyClick(zaap.search_input, Qt.Key_Escape)
            self.pump()
            self.assertFalse(zaap.suggestion_popup.isVisible())
            suggestion_popup = zaap.suggestion_popup
            self.dispose(host)
            self.assertFalse(isValid(suggestion_popup))

    def test_solution_image_popup_toggle_has_no_orphan(self) -> None:
        for _ in range(3):
            host = QWidget()
            label = SolutionImageLabel("", "Image de solution", host)
            label._image_load_started = True
            label.source = QPixmap(320, 180)
            label.source.fill(QColor("#18202b"))
            host.show()
            label.show()
            QTest.mouseClick(label, Qt.LeftButton)
            self.pump()
            popup = label._image_popup
            self.assertIsNotNone(popup)
            self.assertTrue(popup.isVisible())
            QTest.mouseClick(label, Qt.LeftButton)
            self.pump()
            self.assertIsNone(label._image_popup)
            self.assertTrue(not isValid(popup) or not popup.isVisible())
            self.dispose(popup, host)

    def test_dev_menu_and_combobox_popup_accept_real_mouse_clicks(self) -> None:
        for target_index in (1, 2, 0):
            page = DevUiPage()
            page.resize(1100, 800)
            page.show()
            self.pump()
            menu = page.menu_button.menu()
            self.assertIsNotNone(menu)
            menu.show()
            self.pump()
            action = menu.actions()[0]
            QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(action).center())
            self.pump()
            self.assertIn("Première action", page.feedback.text())
            self.assertFalse(menu.isVisible())

            combo = page.preview_combo
            combo.showPopup()
            self.pump()
            view = combo.view()
            index = combo.model().index(target_index, 0)
            QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
            self.pump()
            self.assertEqual(combo.currentIndex(), target_index)
            self.assertFalse(view.isVisible())
            self.dispose(page)
            self.assertFalse(isValid(menu))
            self.assertFalse(isValid(view))


if __name__ == "__main__":
    unittest.main()
