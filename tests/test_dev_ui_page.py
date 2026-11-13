"""Direct Qt owner for the developer visual inventory; no game workers.

This is the exact-name source contract for app/pages/dev_ui_page.py in the
existing fail-closed Doctor-lot router. No broad ownership exemptions.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget


class DevUiPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_dev_ui_gallery_uses_shared_widgets_and_real_clicks(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.components import AtlasButton, AtlasDialog, AtlasPanelToggle

        navigation: list[str] = []
        page = DevUiPage(on_back=lambda: navigation.append("Settings"))
        try:
            self.assertTrue(page.property("atlasUnityPage"))
            self.assertEqual(page.styleSheet(), "")
            self.assertTrue(
                all(widget.styleSheet() == "" for widget in page.findChildren(QWidget))
            )
            self.assertIsInstance(page.preview_buttons["primary"], AtlasButton)
            self.assertEqual(
                page.preview_buttons["primary"].objectName(),
                "PrimaryActionButton",
            )
            self.assertFalse(page.preview_buttons["disabled"].isEnabled())
            self.assertEqual(page.startup_title.objectName(), "PreloadPopupTitle")
            self.assertEqual(page.startup_status.objectName(), "PreloadPopupCurrent")
            self.assertEqual(page.startup_progress.objectName(), "PreloadPopupProgress")
            self.assertEqual(page.startup_progress.value(), 2)
            self.assertEqual(page.guide_sample_summary.objectName(), "GuidePreparationSummary")
            self.assertEqual(page.guide_sample_row.objectName(), "GuidePreparationRow")
            self.assertEqual(page.guide_manual_nav.objectName(), "GuideManualNav")
            page.guide_copy_button.click()
            self.assertIn("Copier cliqué", page.feedback.text())
            page.preview_buttons["primary"].click()
            self.assertIn("primary", page.feedback.text())

            page.preview_tree.setCurrentItem(
                page.preview_tree.topLevelItem(0).child(1)
            )
            self.assertIn("Succès", page.feedback.text())
            page.preview_table.setCurrentCell(2, 0)
            self.assertIn("Clavier", page.feedback.text())
            page.preview_input.setText("essai")
            self.assertIn("Saisie : essai", page.feedback.text())
            page.preview_spin.setValue(6)
            self.assertIn("Compteur : 6", page.feedback.text())
            page.preview_text.setPlainText("interaction")
            self.assertIn("Saisie multiligne", page.feedback.text())

            page.preview_nav[0].click()
            self.assertEqual(page.preview_nav[0].objectName(), "TopNavButtonActive")
            self.assertEqual(page.preview_nav[1].objectName(), "TopNavButton")
            page.preview_combo.setCurrentIndex(2)
            self.assertIn("Instantané", page.feedback.text())
            page.preview_tabs.setCurrentIndex(1)
            self.assertIn("Succès", page.feedback.text())
            page.menu_button.menu().actions()[1].trigger()
            self.assertIn("Deuxième action", page.feedback.text())

            page.preview_slider.setValue(78)
            self.assertEqual(page.preview_progress.value(), 78)
            self.assertIsInstance(page.panel_toggle, AtlasPanelToggle)
            page.panel_toggle.click()
            self.assertTrue(page.preview_panel.isHidden())
            self.assertTrue(page.panel_toggle.property("collapsed"))
            page.panel_toggle.click()
            self.assertFalse(page.preview_panel.isHidden())

            page.dialog_button.click()
            self.assertIsInstance(page._preview_dialog, AtlasDialog)
            page._preview_dialog.reject()
            page.back_button.click()
            self.assertEqual(navigation, ["Settings"])
        finally:
            page.close()
            page.deleteLater()


    def test_dev_ui_physical_mouse_click_reaches_shared_button_handler(self) -> None:
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            page.resize(1000, 800)
            page.show()
            self.app.processEvents()
            button = page.preview_buttons["primary"]
            self.assertTrue(button.isVisible())
            QTest.mouseClick(button, Qt.LeftButton)
            self.assertIn("Bouton primary cliqué", page.feedback.text())
            self.assertEqual(page.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()


    def test_dev_ui_gallery_is_lazy_and_accessible_from_settings(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('self.register_page("Dev UI", self.loading_page(', source)
        self.assertIn('self.page_factories["Dev UI"] = self.create_dev_ui_page', source)
        self.assertIn('developer_button.clicked.connect(lambda: self.show_page("Dev UI"))', source)
        self.assertIn(
            'self.release_reconstructible_page("Dev UI", self.create_dev_ui_page)',
            source,
        )



if __name__ == "__main__":
    unittest.main()
