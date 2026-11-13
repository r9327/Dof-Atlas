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
            self.assertEqual(
                page.guide_ultime_sample.objectName(), "GuideUltimeGeneratedView"
            )
            self.assertEqual(page.guide_ultime_combo.styleSheet(), "")
            page.guide_ultime_combo.setCurrentIndex(2)
            self.assertIn("Guide Ultime : Instantané", page.feedback.text())
            page.guide_copy_button.click()
            self.assertIn("Copier cliqué", page.feedback.text())
            page.preview_buttons["primary"].click()
            self.assertIn("primary", page.feedback.text())
            for role, expected_name in (
                ("guide_breadcrumb", "GuideBreadcrumbButton"),
                ("guide_quest_link", "GuideInlineQuestButton"),
                ("guide_achievement_link", "GuideInlineAchievementButton"),
            ):
                self.assertEqual(page.preview_buttons[role].objectName(), expected_name)
                self.assertEqual(page.preview_buttons[role].styleSheet(), "")
                page.preview_buttons[role].click()
                self.assertIn(role, page.feedback.text())

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


    def test_all_ui_families_are_visible_without_local_styles(self) -> None:
        """The developer catalog covers real controls and semantic style roles."""
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import PALETTE
        from PySide6.QtWidgets import QGroupBox, QLabel

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(page.gallery_navigation.count(), len(page.gallery_sections))
            self.assertGreaterEqual(page.gallery_navigation.count(), 13)
            self.assertTrue(all(isinstance(s, QGroupBox) for s in page.gallery_sections))
            self.assertIn("familles UI", page.gallery_count.text())
            self.assertTrue(page.gallery_scroll.widgetResizable())
            self.assertEqual(page.styleSheet(), "")
            self.assertTrue(all(w.styleSheet() == "" for w in page.findChildren(QWidget)))

            # No second palette: all current tokens are represented by Qt swatches.
            swatches = [
                label for label in page.findChildren(QLabel)
                if label.accessibleName().startswith("Couleur ")
            ]
            self.assertEqual(
                {label.accessibleName() for label in swatches},
                {f"Couleur {role}" for role in PALETTE},
            )

            self.assertEqual(set(page.preview_badges), {"done", "active", "blocked"})
            for state, badge in page.preview_badges.items():
                self.assertEqual(badge.objectName(), "StatusBadge")
                self.assertEqual(badge.property("state"), state)
            self.assertEqual(set(page.preview_cards), {"card", "Panel", "QuestPanel"})
            self.assertEqual(page.preview_busy.minimum(), 0)
            self.assertEqual(page.preview_busy.maximum(), 0)
            self.assertEqual(page.preview_complete.value(), 100)
            self.assertEqual(page.preview_splitter.count(), 2)
            self.assertEqual(page.preview_scroll_list.count(), 8)
            self.assertEqual(page.preview_scope.rowCount(), 12)
            self.assertEqual(page.preview_scope.item(11, 0).text(), "Launcher")
            self.assertIn("Tk", page.preview_scope.item(11, 1).text())
            self.assertEqual(len(page.preview_icon_labels), 8)
            self.assertTrue(all(
                icon.styleSheet() == ""
                for icon in page.preview_icon_labels.values()
            ))
            self.assertTrue(page.preview_password.echoMode() == page.preview_password.Password)
            self.assertTrue(page.preview_readonly.isReadOnly())
            self.assertFalse(page.preview_disabled_input.isEnabled())

            page.preview_toggle.click()
            self.assertFalse(page.preview_toggle.isChecked())
            self.assertIn("Commutateur inactif", page.feedback.text())
            page.preview_scroll_list.setCurrentRow(1)
            self.assertIn("Personnage", page.feedback.text())
            page.preview_double_spin.setValue(15.75)
            self.assertIn("15.75", page.feedback.text())
        finally:
            page.close()
            page.deleteLater()

    def test_gallery_index_scrolls_to_real_section(self) -> None:
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            page.resize(1000, 760)
            page.show()
            self.app.processEvents()
            bar = page.gallery_scroll.verticalScrollBar()
            page.gallery_navigation.setCurrentIndex(
                page.gallery_navigation.count() - 1
            )
            self.app.processEvents()
            self.assertGreater(bar.maximum(), 0)
            self.assertGreater(bar.value(), 0)
            self.assertEqual(page.gallery_navigation.currentText(), "Palette Unity · source de vérité")
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


    def test_guide_ultime_dropdown_keyboard_selection_uses_real_qt_signal(self) -> None:
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            page.resize(1000, 800)
            page.show()
            self.app.processEvents()
            combo = page.guide_ultime_combo
            combo.setCurrentIndex(0)
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key_Down)
            self.assertEqual(combo.currentIndex(), 1)
            self.assertIn("Guide Ultime : Rapide", page.feedback.text())
            self.assertEqual(combo.styleSheet(), "")
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
