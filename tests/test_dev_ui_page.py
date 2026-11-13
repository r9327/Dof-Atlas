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
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget


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
            self.assertEqual(page.preview_icon_grid.count(), 8)
            self.assertEqual(page.preview_icon_grid.getItemPosition(7), (1, 3, 1, 1))
            for index in range(page.preview_icon_grid.count()):
                cell = page.preview_icon_grid.itemAt(index).widget()
                self.assertEqual(cell.objectName(), "DevUiIconCell")
                self.assertEqual(cell.styleSheet(), "")
            self.assertEqual(page.preview_tree.columnWidth(1), 150)
            self.assertFalse(page.preview_table.showGrid())
            self.assertFalse(page.preview_scope.showGrid())
            self.assertFalse(page.preview_table.alternatingRowColors())
            self.assertFalse(page.preview_tree.alternatingRowColors())
            self.assertFalse(page.preview_metrics.alternatingRowColors())
            self.assertFalse(page.preview_scope.alternatingRowColors())
            self.assertFalse(page.gallery_navigation.view().alternatingRowColors())
            from app.pages.dev_ui_page import UnityPopupSeparatorDelegate
            self.assertIsInstance(
                page.gallery_navigation.view().itemDelegate(),
                UnityPopupSeparatorDelegate,
            )
            self.assertEqual(page.gallery_navigation.count(), 16)
            self.assertEqual(page.gallery_scroll.objectName(), "DevUiGalleryScroll")
            self.assertFalse(page.preview_combo.view().alternatingRowColors())
            self.assertFalse(page.guide_ultime_combo.view().alternatingRowColors())
            self.assertTrue(all(
                page.preview_tabs.widget(index).objectName() == "DevUiTabPage"
                for index in range(page.preview_tabs.count())
            ))
            self.assertTrue(page.preview_checked_action.isChecked())
            page.preview_checked_action.click()
            self.assertFalse(page.preview_checked_action.isChecked())
            self.assertIn("désélectionné", page.feedback.text())
            self.assertTrue(all(
                icon.styleSheet() == ""
                for icon in page.preview_icon_labels.values()
            ))
            self.assertTrue(page.preview_password.echoMode() == QLineEdit.Password)
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

    def test_shared_type_scale_and_gallery_finishes(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import TYPOGRAPHY, atlas_stylesheet

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(
                set(page.preview_type_samples),
                {"page", "section", "body", "muted"},
            )
            self.assertEqual(page.preview_type_samples["page"].objectName(), "PageTitle")
            self.assertEqual(
                page.preview_type_samples["section"].objectName(), "PanelTitle"
            )
            self.assertEqual(page.preview_type_samples["body"].objectName(), "")
            self.assertEqual(
                page.preview_type_samples["muted"].objectName(), "MutedLabel"
            )
            self.assertTrue(all(
                widget.styleSheet() == ""
                for widget in page.preview_type_samples.values()
            ))
            self.assertTrue(all(
                "px" in button.text()
                for button in page.preview_metric_buttons.values()
            ))
            self.assertEqual(TYPOGRAPHY["FONT_TITLE"], "18px")
            self.assertEqual(TYPOGRAPHY["FONT_SECTION"], "14px")
            self.assertEqual(TYPOGRAPHY["FONT_BODY"], "12px")
            self.assertEqual(TYPOGRAPHY["FONT_SMALL"], "11px")
            css = atlas_stylesheet()
            self.assertIn("QWidget#DevUiPage QGroupBox::title", css)
            self.assertIn("QScrollArea#DevUiGalleryScroll", css)
            self.assertIn("stop:0 rgba(33, 49, 84, 0.68)", css)
            self.assertIn("stop:1 rgba(27, 39, 70, 0.74)", css)
            # Only the gallery transparency changes; global panel tokens
            # and the real shell background source are untouched.
            self.assertIn("QWidget#DevUiPage QGroupBox {", css)
            self.assertIn("QWidget#DevUiPage QComboBox QAbstractItemView", css)
            self.assertIn("QWidget#DevUiPage QFrame#GuideUltimeGeneratedView", css)
            self.assertIn("alternate-background-color: #1B2746", css)
            self.assertIn("QWidget#DevUiPage QFrame#card", css)
            self.assertIn("rgba(217, 234, 242, 0.16)", css)
            self.assertIn("stop:0 rgba(33, 49, 84, 0.82)", css)
            self.assertIn("stop:1 rgba(27, 39, 70, 0.88)", css)
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            for card in page.preview_cards.values():
                shadow = card.graphicsEffect()
                self.assertIsInstance(shadow, QGraphicsDropShadowEffect)
                self.assertEqual(shadow.blurRadius(), 17)
                self.assertEqual(shadow.color().alpha(), 135)
            shadow_sections = [
                section for section in page.gallery_sections
                if section.graphicsEffect() is not None
            ]
            self.assertEqual(len(shadow_sections), len(page.gallery_sections))
            for section in shadow_sections:
                shadow = section.graphicsEffect()
                self.assertIsInstance(shadow, QGraphicsDropShadowEffect)
                self.assertEqual(shadow.blurRadius(), 17)
                self.assertEqual(shadow.color().alpha(), 135)
            self.assertEqual(page.preview_advanced_grid.columnCount(), 3)
            self.assertEqual(page.preview_date.displayFormat(), "dd/MM/yyyy")
            self.assertEqual(page.preview_time.displayFormat(), "HH:mm")
            advanced_fields = (
                page.preview_password, page.preview_readonly,
                page.preview_disabled_input, page.preview_double_spin,
                page.preview_date, page.preview_time,
            )
            self.assertTrue(all(widget.minimumHeight() == 32
                                for widget in advanced_fields))
            self.assertIn("QWidget#DevUiPage QWidget#DevUiIconCell", css)
            self.assertIn("QWidget#DevUiPage QTreeWidget::item", css)
            self.assertIn("#SecondaryButton:checked", css)
            self.assertIn("background: #9FCE51;", css)
            self.assertIn("font-size: 14px;", css)
            self.assertEqual(page.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_game_ui_colors_sizes_icons_and_gradient_preview(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.unity_palette import (
            UNITY_ICON_NAMES, UNITY_MAIN_ROLES, UNITY_SIZES_PX, UNITY_UI_USAGE,
        )

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(page.preview_main_color_roles, UNITY_MAIN_ROLES)
            self.assertEqual(page.preview_ui_usage, UNITY_UI_USAGE)
            self.assertTrue(page.preview_palette_details.isHidden())
            page.preview_palette_toggle.click()
            self.assertFalse(page.preview_palette_details.isHidden())
            page.preview_palette_toggle.click()
            self.assertTrue(page.preview_palette_details.isHidden())

            self.assertEqual(set(page.preview_icon_labels), set(UNITY_ICON_NAMES))
            from app.ui.unity_skin import unity_original_preview_icon
            self.assertTrue(all(
                not unity_original_preview_icon(name).isNull()
                for name in UNITY_ICON_NAMES
            ))
            self.assertTrue(all(
                label.pixmap() is not None and not label.pixmap().isNull()
                for label in page.preview_icon_labels.values()
            ))
            self.assertEqual(
                set(page.preview_metric_buttons),
                {"control_compact", "control_normal", "control_large"},
            )
            for role, button in page.preview_metric_buttons.items():
                self.assertEqual(button.height(), UNITY_SIZES_PX[role])
            for role, label in page.preview_metric_icons.items():
                self.assertEqual(label.pixmap().width(), UNITY_SIZES_PX[role])
            self.assertGreater(page.preview_metrics.rowCount(), 10)

            # QSS gradients must be drawn, not fed to QColor as invalid hex.
            gradient = page._color_pixmap(
                "qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 #101010, stop:1 #F0F0F0)",
                32, 18,
            ).toImage()
            self.assertTrue(gradient.pixelColor(1, 9).isValid())
            self.assertNotEqual(
                gradient.pixelColor(1, 9).red(),
                gradient.pixelColor(30, 9).red(),
            )
            self.assertGreater(gradient.pixelColor(1, 9).alpha(), 0)
            # Vertical gradients must use their actual QSS coordinates.
            vertical = page._color_pixmap(
                "qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "stop:0 #111111, stop:1 #EEEEEE)",
                32, 24,
            ).toImage()
            self.assertNotEqual(
                vertical.pixelColor(15, 1).red(),
                vertical.pixelColor(15, 22).red(),
            )
            self.assertEqual(
                page._color_pixmap("#123456", 8, 8).toImage()
                .pixelColor(0, 0).name(), "#123456",
            )
        finally:
            page.close()
            page.deleteLater()

    def test_gallery_renders_real_qt_full_height_in_reduced_window(self) -> None:
        """Viewport and full scroll content must be real, grab-able Qt pixels."""
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            page.resize(900, 680)
            page.show()
            self.app.processEvents()
            self.assertEqual(page.gallery_navigation.count(), 16)
            self.assertGreater(
                page.gallery_scroll.verticalScrollBar().maximum(), 0
            )
            viewport = page.grab()
            full = page.gallery_scroll.widget().grab()
            self.assertFalse(viewport.isNull())
            self.assertFalse(full.isNull())
            self.assertGreater(full.height(), page.gallery_scroll.viewport().height())
            self.assertEqual(viewport.width(), page.width())
            self.assertTrue(all(
                section.styleSheet() == "" for section in page.gallery_sections
            ))
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
