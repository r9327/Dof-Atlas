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
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QLineEdit, QSizePolicy, QWidget
from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX


class DevUiPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_ui_gallery_final_coverage_of_navigation_grid_and_variants(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.components import AtlasStatusBadge
        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(page.preview_tabs.objectName(), "EncyclopediaTabs")
            self.assertEqual(page.preview_sidebar.objectName(), "sidebar")
            self.assertEqual(page.preview_sidebar_content.objectName(),
                             "DevUiSidebarContent")
            self.assertEqual(page.preview_burger.text(), "Menu")
            self.assertIsNotNone(page.preview_sidebar.graphicsEffect())
            self.assertEqual(page.page_breadcrumb.objectName(),
                             "GuideBreadcrumb")
            self.assertEqual(page.layout().itemAt(0).widget(),
                             page.page_breadcrumb)
            self.assertEqual(page.page_breadcrumb_back.objectName(),
                             "GuideBreadcrumbButton")
            self.assertIsNotNone(page.preview_breadcrumb.graphicsEffect())
            self.assertEqual(page.preview_sidebar_buttons["Encyclopédie"].objectName(),
                             "navItemActive")
            page.preview_sidebar_buttons["Outils"].click()
            self.assertEqual(page.preview_sidebar_buttons["Outils"].objectName(),
                             "navItemActive")
            self.assertEqual(page.preview_sidebar_buttons["Encyclopédie"].objectName(),
                             "navItem")
            page.preview_burger.click()
            self.assertTrue(page.preview_sidebar_content.isHidden())
            page.preview_burger.click()
            self.assertFalse(page.preview_sidebar_content.isHidden())
            self.assertFalse(page.preview_page_prev.isEnabled())
            page.preview_page_next.click()
            self.assertEqual(page.preview_page_index, 2)
            page.preview_page_prev.click()
            self.assertEqual(page.preview_page_index, 1)
            self.assertEqual(page.preview_breadcrumb_compact.objectName(),
                             "BreadcrumbLabel")
            self.assertEqual(page.preview_breadcrumb_strong.objectName(),
                             "GuideBreadcrumbCurrentStrong")
            self.assertEqual(len(page.preview_layout_cards), 4)
            self.assertTrue(all(c.objectName() == "card"
                                for c in page.preview_layout_cards))
            self.assertEqual(set(page.preview_state_buttons),
                             {"normal", "hover", "pressed", "selected",
                              "focus", "disabled"})
            self.assertFalse(page.preview_state_buttons["disabled"].isEnabled())
            self.assertEqual(page.preview_glass_panel.objectName(),
                             "OrganizerPanel")
            self.assertEqual(page.preview_title_accent.objectName(),
                             "TitleAccent")
            self.assertEqual(page.preview_card_accent.objectName(),
                             "CardTitleAccent")
            menu = page.menu_button.menu()
            self.assertTrue(any(a.menu() is not None for a in menu.actions()))
            self.assertTrue(any(a.isCheckable() for a in menu.actions()))
            self.assertEqual(set(page.preview_dialog_variants),
                             {"info", "warning", "danger", "confirmation", "form"})
            page.preview_dialog_variants["danger"].click()
            self.assertIsNotNone(page._preview_dialog)
            self.assertTrue(any(
                badge.property("state") == "danger"
                for badge in page._preview_dialog.findChildren(AtlasStatusBadge)
            ))
            page._preview_dialog.reject()
            self.assertTrue(all(widget.styleSheet() == ""
                                for widget in page.findChildren(QWidget)))
        finally:
            page.close()
            page.deleteLater()

    def test_shared_content_sizing_and_x_x_page_navigation(self) -> None:
        from PySide6.QtWidgets import QSizePolicy
        from app.ui.components import AtlasComboBox, AtlasPageNavigator

        chooser = AtlasComboBox()
        navigator = AtlasPageNavigator(total=120)
        try:
            self.assertEqual(
                chooser.sizeAdjustPolicy(), AtlasComboBox.AdjustToContents
            )
            self.assertEqual(
                chooser.sizePolicy().horizontalPolicy(), QSizePolicy.Maximum
            )
            chooser.addItem("Un")
            narrow = chooser.sizeHint().width()
            chooser.addItem("Un intitulé beaucoup plus long à sélectionner")
            self.assertGreater(chooser.sizeHint().width(), narrow)
            self.assertEqual(chooser.maxVisibleItems(), 8)
            self.assertEqual(chooser.styleSheet(), "")

            self.assertEqual(navigator.page_label.objectName(), "AtlasPageCounter")
            self.assertEqual(navigator.page_label.text(), "1/120")
            self.assertFalse(navigator.previous_button.isEnabled())
            requested = []
            navigator.pageRequested.connect(requested.append)
            navigator.next_button.click()
            self.assertEqual(requested, [2])
            navigator.set_page(120, 120)
            self.assertEqual(navigator.page_label.text(), "120/120")
            self.assertFalse(navigator.next_button.isEnabled())
            navigator.previous_button.click()
            self.assertEqual(requested, [2, 119])
            navigator.set_page(2, 7)
            self.assertEqual(navigator.page_label.text(), "2/7")
            navigator.set_page(0, 0)
            self.assertEqual(navigator.page_label.text(), "0/0")
            self.assertFalse(navigator.previous_button.isEnabled())
            self.assertFalse(navigator.next_button.isEnabled())
        finally:
            chooser.deleteLater()
            navigator.deleteLater()

    def test_black_surface_and_density_regressions_use_shared_unity_roles(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import atlas_stylesheet
        from app.ui.unity_palette import UNITY_SIZES_PX
        from app.ui.components import AtlasComboBox

        page = DevUiPage(on_back=lambda: None)
        try:
            detail_shell = page.preview_success_columns["AchievementDetailStack"]
            self.assertEqual(detail_shell.widget(0).objectName(),
                             "AtlasTransparentHost")
            self.assertEqual(detail_shell.styleSheet(), "")
            from PySide6.QtWidgets import QSizePolicy
            self.assertEqual(
                page.gallery_navigation.sizeAdjustPolicy(),
                AtlasComboBox.AdjustToContents,
            )
            self.assertEqual(
                page.gallery_navigation.sizePolicy().horizontalPolicy(),
                QSizePolicy.Maximum,
            )
            self.assertEqual(page.gallery_navigation.maxVisibleItems(), 8)
            self.assertIn("combobox-popup: 0;", atlas_stylesheet())
            self.assertEqual(page.preview_map_tree.maximumHeight(),
                             3 * UNITY_SIZES_PX["control_normal"])
            self.assertEqual(page.preview_scroll_list.maximumHeight(),
                             4 * UNITY_SIZES_PX["control_normal"])
            self.assertEqual(page.preview_almanax_calendar.maximumHeight(),
                             7 * UNITY_SIZES_PX["control_normal"])
            self.assertTrue(all(
                frame.graphicsEffect() is not None
                for frame in page.preview_notifications.values()
            ))
            self.assertIsNotNone(page.preview_panel.graphicsEffect())
            self.assertEqual(AtlasComboBox().maxVisibleItems(), 8)
            self.assertTrue(all(w.styleSheet() == ""
                                for w in page.findChildren(QWidget)))
        finally:
            page.close()
            page.deleteLater()

        css = atlas_stylesheet()
        self.assertIn(
            "QCalendarWidget#AlmanaxCalendar QTableView#qt_calendar_calendarview::item",
            css,
        )
        self.assertIn(
            "QWidget#AchievementsView QStackedWidget#AchievementDetailStack > QWidget",
            css,
        )

    def test_shared_dialog_keeps_real_icon_only_and_compact_actions(self) -> None:
        from PySide6.QtGui import QIcon
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.components import AtlasDialog, AtlasDialogHeader

        empty_icon_header = AtlasDialogHeader("Test", icon=QIcon())
        try:
            self.assertTrue(empty_icon_header.icon_label.isHidden())
        finally:
            empty_icon_header.deleteLater()

        dialog = AtlasDialog()
        try:
            self.assertGreaterEqual(dialog.minimumWidth(), 400)
            self.assertEqual(dialog.styleSheet(), "")
        finally:
            dialog.deleteLater()

        page = DevUiPage(on_back=lambda: None)
        try:
            page.preview_dialog_variants["info"].click()
            preview = page._preview_dialog
            self.assertIsNotNone(preview)
            self.assertEqual(preview.content_layout.count(), 4)
            preview.reject()
        finally:
            page.close()
            page.deleteLater()

    def test_dialog_variants_share_one_surface_with_custom_content(self) -> None:
        from PySide6.QtWidgets import QCheckBox, QDialog, QSpinBox
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.components import (
            AtlasButton, AtlasDialog, AtlasDialogHeader, fit_unity_number_spinbox,
        )

        page = DevUiPage(on_back=lambda: None)
        try:
            page.preview_dialog_variants["confirmation"].click()
            confirmation = page._preview_dialog
            self.assertIsInstance(confirmation, AtlasDialog)
            self.assertTrue(confirmation.isModal())
            self.assertEqual(confirmation.styleSheet(), "")
            self.assertEqual(len(confirmation.findChildren(AtlasDialogHeader)), 1)
            actions = {
                button.text(): button
                for button in confirmation.findChildren(AtlasButton)
            }
            self.assertEqual(set(actions), {"Annuler", "Valider"})
            actions["Annuler"].click()
            self.assertFalse(confirmation.isVisible())

            page.preview_dialog_variants["form"].click()
            form = page._preview_dialog
            self.assertIsInstance(form, AtlasDialog)
            self.assertEqual(form.objectName(), "AtlasDialog")
            self.assertEqual(len(form.findChildren(AtlasDialogHeader)), 1)
            options = form.findChildren(QCheckBox, "DevUiDialogOption")
            counters = form.findChildren(QSpinBox, "DevUiDialogQuantity")
            self.assertEqual(len(options), 1)
            self.assertEqual(len(counters), 1)
            self.assertEqual(counters[0].maximum(), 9999)
            self.assertEqual(counters[0].styleSheet(), "")
            self.assertEqual(counters[0].width(), fit_unity_number_spinbox(counters[0]))
            actions = {
                button.text(): button for button in form.findChildren(AtlasButton)
            }
            self.assertEqual(set(actions), {"Annuler", "Valider"})
            actions["Valider"].click()
            self.assertFalse(form.isVisible())
            self.assertEqual(form.result(), QDialog.Accepted)
            self.assertEqual(form.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_featured_guide_uses_shared_hidden_button_without_changing_open_signal(self) -> None:
        from types import SimpleNamespace
        from app.modules.encyclopedia.views.guide_featured_home import FeaturedGuideCard
        from app.ui.components import AtlasButton

        opened = []
        card = FeaturedGuideCard(
            "guide_complet", "Guide Succès Opti", opened.append,
        )
        try:
            self.assertIsInstance(card.open_button, AtlasButton)
            self.assertEqual(card.open_button.objectName(), "FeaturedGuideOpen")
            self.assertTrue(card.open_button.isHidden())
            self.assertFalse(card.open_button.isEnabled())
            card.set_guide(
                SimpleNamespace(description="Guide de démonstration", image_path=None),
                (0, 4, ""),
            )
            self.assertTrue(card.open_button.isEnabled())
            card.open_button.click()
            self.assertEqual(opened, ["guide_complet"])
            self.assertEqual(card.open_button.styleSheet(), "")
        finally:
            card.close()
            card.deleteLater()

    def test_four_actual_craft_dialogs_are_previewable_without_new_ui_classes(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.pages.craft_page import (
            CraftResourceDialog, ItemSetDialog, LevelingDialog, RouteDialog,
        )
        from app.ui.components import (
            AtlasComboBox, AtlasButton, AtlasDialog, AtlasDialogHeader,
            BUTTON_OBJECT_NAMES,
        )

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertIsInstance(page.preview_craft_dialog_choice, AtlasComboBox)
            self.assertIsInstance(page.preview_craft_dialog_open, AtlasButton)
            self.assertEqual(page.preview_craft_dialog_choice.count(), 4)
            for index, cls in enumerate((
                CraftResourceDialog, ItemSetDialog, LevelingDialog, RouteDialog,
            )):
                with self.subTest(dialog=cls.__name__):
                    page.preview_craft_dialog_choice.setCurrentIndex(index)
                    page.preview_craft_dialog_open.click()
                    self.app.processEvents()
                    dialog = page._preview_dialog
                    self.assertIsInstance(dialog, cls)
                    self.assertIsInstance(dialog, AtlasDialog)
                    self.assertEqual(dialog.objectName(), "AtlasDialog")
                    self.assertEqual(len(dialog.findChildren(AtlasDialogHeader)), 1)
                    self.assertEqual(dialog.styleSheet(), "")
                    self.assertIn("Fenêtre Craft réelle", page.feedback.text())
                    dialog.reject()
                    self.app.processEvents()
            counts = page.preview_shared_ui_counts.text()
            self.assertIn(
                f"1 AtlasButton / {len(BUTTON_OBJECT_NAMES)} rôles visuels",
                counts,
            )
            self.assertIn(
                f"1 AtlasDialog / {len(page.preview_dialog_variants)} variantes",
                counts,
            )
            self.assertIn("Craft : 4 usages sur AtlasDialog commun", counts)
            self.assertIn("15 usages existants distincts", counts)
        finally:
            page.close()
            page.deleteLater()

    def test_success_three_column_shell_shares_dev_ui_materials(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from PySide6.QtWidgets import QStackedWidget

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(
                page.preview_success_catalogue.objectName(),
                "AchievementsView",
            )
            self.assertEqual(set(page.preview_success_columns),
                             {"GuideLeftPanel", "GuideCenterPanel",
                              "AchievementDetailStack"})
            self.assertIsInstance(
                page.preview_success_columns["AchievementDetailStack"],
                QStackedWidget,
            )
            for name, column in page.preview_success_columns.items():
                self.assertEqual(column.objectName(), name)
                self.assertEqual(column.styleSheet(), "")
                self.assertIsNotNone(column.graphicsEffect())
            self.assertEqual(page.preview_success_catalogue.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_world_map_navigation_and_panels_are_real_dev_ui_samples(self) -> None:
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(page.preview_world_menu.objectName(), "WorldMenu")
            self.assertIsNotNone(page.preview_world_menu.graphicsEffect())
            self.assertEqual(
                page.preview_world_buttons["Monde des Douze"].objectName(),
                "WorldMenuItemActive",
            )
            page.preview_world_buttons["Frigost"].click()
            self.assertEqual(
                page.preview_world_buttons["Frigost"].objectName(),
                "WorldMenuItemActive",
            )
            self.assertEqual(
                page.preview_world_buttons["Monde des Douze"].objectName(),
                "WorldMenuItem",
            )
            self.assertIn("Navigation Monde : Frigost", page.feedback.text())
            self.assertEqual(page.preview_map_tree.objectName(), "MapViewTree")
            page.preview_map_tree.setCurrentItem(
                page.preview_map_tree.topLevelItem(1)
            )
            self.assertIn("Arbre Carte : Incarnam", page.feedback.text())
            self.assertEqual(set(page.preview_map_chrome),
                             {"MapToolbar", "WorldDetailPanel"})
            self.assertEqual(set(page.preview_map_values),
                             {"WorldDetailValue", "MapDetailValue"})
            for frame in page.preview_map_chrome.values():
                self.assertIsNotNone(frame.graphicsEffect())
            for widget in (*page.preview_map_chrome.values(),
                           *page.preview_map_values.values()):
                self.assertEqual(widget.styleSheet(), "")
            self.assertTrue(all(child.styleSheet() == ""
                                for child in page.findChildren(QWidget)))
        finally:
            page.close()
            page.deleteLater()

    def test_almanax_calendar_uses_shared_unity_component_and_future_dates(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from PySide6.QtCore import QDate

        page = DevUiPage(on_back=lambda: None)
        try:
            picker = page.preview_almanax_calendar
            self.assertEqual(picker.objectName(), "AlmanaxCalendar")
            self.assertEqual(picker.styleSheet(), "")
            self.assertIsNotNone(picker.graphicsEffect())
            from app.ui.unity_palette import UNITY_PALETTE
            from PySide6.QtGui import QColor
            for day in (Qt.Saturday, Qt.Sunday):
                self.assertEqual(
                    picker.weekdayTextFormat(day).foreground().color(),
                    QColor(UNITY_PALETTE["TEXT_SOFT"]),
                )
            target = QDate.currentDate().addDays(12)
            picker.setSelectedDate(target)
            self.assertEqual(picker.selectedDate(), target)
            self.assertIn(target.toString("dd/MM/yyyy"), page.feedback.text())
        finally:
            page.close()
            page.deleteLater()

    def test_quest_launch_position_preview_uses_real_shared_style(self) -> None:
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            label = page.preview_quest_start_position
            self.assertEqual(label.objectName(), "QuestLaunchPosition")
            self.assertIn("[4,-18]", label.text())
            self.assertEqual(label.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_headers_gallery_shares_real_styles_and_controls(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.modules.encyclopedia.views.shared_manual_guide_view import (
            _ParticipantPortraitButton,
        )
        from app.ui.unity_palette import UNITY_LAYOUT_SIZES_PX, UNITY_SPACING_PX
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QCheckBox

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertIn("headers", page.gallery_family_widgets)
            for name, role in (
                ("preview_page_header", "card"),
                ("preview_module_header", "GuideHeader"),
                ("preview_compact_header", "GuideCompactHeader"),
                ("preview_sheet_header", "GuideSheetHeader"),
                ("preview_dialog_header", "DialogHeader"),
            ):
                widget = getattr(page, name)
                self.assertEqual(widget.objectName(), role)
                self.assertEqual(widget.styleSheet(), "")
            margins = page.preview_compact_header.layout().contentsMargins()
            self.assertEqual(
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
                (
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_top"],
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
                    UNITY_LAYOUT_SIZES_PX["guide_header_margin_bottom"],
                ),
            )
            self.assertEqual(page.preview_header_global_progress.value(), 35)
            self.assertEqual(page.preview_header_page_jump.suffix(), " / 20")
            # The x/x selector is content-sized, not artificially fixed
            # to the old 110px cap. Short counts must remain compact.
            from app.ui.components import fit_unity_number_spinbox
            page_jump = page.preview_header_page_jump
            self.assertEqual(page_jump.width(), fit_unity_number_spinbox(page_jump))
            self.assertLessEqual(
                page_jump.width(),
                UNITY_CONTROL_SIZES_PX["guide_page_jump_normal_max_width"]
                + UNITY_SPACING_PX["sm"],
            )
            previous_width = page_jump.width()
            page_jump.setRange(1, 123456)
            page_jump.setSuffix(" / 123456")
            self.assertGreater(fit_unity_number_spinbox(page_jump), previous_width)
            self.assertIs(page.preview_header_page_jump.parentWidget(),
                          page.preview_sheet_header)
            self.assertEqual(
                {name: bar.objectName() for name, bar in page.preview_header_metrics.items()},
                {"Préparation": "GuideCompactPreparationProgress"},
            )
            self.assertEqual(set(page.preview_header_metric_icons), {"Préparation"})
            self.assertEqual(
                set(page.preview_header_controls),
                {"Progression globale", "Préparation", "Personnages"},
            )
            self.assertEqual(page.preview_header_global_panel.objectName(),
                             "GuideGlobalDetailsPanel")
            self.assertEqual(
                page.preview_header_materials_host.objectName(),
                "GuidePreparationContent",
            )
            self.assertEqual(
                page.preview_header_prerequisites_host.objectName(),
                "GuidePreparationContent",
            )
            from app.ui.theme import atlas_stylesheet
            compiled_qss = atlas_stylesheet()
            # The live Guide and this preview use these same role selectors:
            # no invisible idle/disabled character border and no tight x/x.
            from app.ui.unity_palette import UNITY_PALETTE, UNITY_SPACING_PX
            self.assertIn(
                "QToolButton#GuideParticipantsButton {", compiled_qss
            )
            participant_style = compiled_qss.split(
                "QToolButton#GuideParticipantsButton {", 1
            )[1].split("}", 1)[0]
            self.assertIn(
                "border: 1px solid " + UNITY_PALETTE["GUIDE_TOGGLE_BORDER"],
                participant_style,
            )
            self.assertIn(
                "QToolButton#GuideParticipantsButton:focus,", compiled_qss
            )
            disabled_participant_style = compiled_qss.split(
                "QToolButton#GuideParticipantsButton:disabled {", 1
            )[1].split("}", 1)[0]
            self.assertIn(
                "border-color: " + UNITY_PALETTE["BORDER_SOFT"],
                disabled_participant_style,
            )
            page_selector_style = compiled_qss.split(
                "QSpinBox#GuideCompactPageJump {", 1
            )[1].split("}", 1)[0]
            self.assertIn(
                f'padding-left: {UNITY_SPACING_PX["lg"]}px;',
                page_selector_style,
            )
            self.assertIn("QWidget#GuideGlobalCharacterProgress", compiled_qss)
            self.assertIn("QWidget#GuidePreparationContent", compiled_qss)
            self.assertIsNone(page.preview_compact_header.findChild(
                QWidget, "GuideSummaryPanel"
            ))
            self.assertIsNone(page.preview_compact_header.findChild(
                QWidget, "GuideManualProgress"
            ))
            for name in ("Progression globale", "Préparation"):
                button = page.preview_header_controls[name]
                self.assertEqual(button.objectName(), "GuideMetricDropdown")
                self.assertFalse(button.icon().isNull())
                self.assertEqual(button.arrowType(), Qt.NoArrow)
                self.assertEqual(button.width(),
                                 UNITY_CONTROL_SIZES_PX["progress_toggle_width"])
            self.assertFalse(page.preview_header_overlay.isEnabled())
            self.assertFalse(page.preview_header_guide_icon.pixmap().isNull())
            participants_button = page.preview_header_controls["Personnages"]
            self.assertIs(
                page.preview_header_title_row.itemAt(
                    page.preview_header_title_row.count() - 1
                ).widget(),
                participants_button,
            )
            self.assertIs(page.preview_header_content_layout.itemAt(1).widget(),
                          page.preview_header_panels["Personnages"])
            self.assertEqual(participants_button.width(),
                             UNITY_CONTROL_SIZES_PX["guide_character_button"])
            self.assertFalse(participants_button.icon().isNull())
            self.assertEqual(len(page.preview_header_portraits), 3)
            self.assertTrue(all(
                isinstance(p, _ParticipantPortraitButton)
                and p.width() == UNITY_CONTROL_SIZES_PX["guide_portrait_button"]
                and p.iconSize().width() == UNITY_CONTROL_SIZES_PX["guide_portrait_icon"]
                for p in page.preview_header_portraits
            ))
            participants_button.click()
            self.assertTrue(page.preview_header_panels["Personnages"].isVisibleTo(
                page.preview_compact_header
            ))
            participants_button.click()

            global_button = page.preview_header_controls["Progression globale"]
            preparation_button = page.preview_header_controls["Préparation"]
            self.assertFalse(page.preview_header_global_panel.isVisible())
            global_button.click()
            self.assertTrue(page.preview_header_global_panel.isVisibleTo(
                page.preview_compact_header
            ))
            preparation_button.click()
            self.assertTrue(page.preview_header_panels["Préparation"].isVisibleTo(
                page.preview_compact_header
            ))
            self.assertIs(
                page.preview_header_panels["Préparation"].parentWidget(),
                page.preview_header_global_panel,
            )
            global_button.click()
            self.assertFalse(page.preview_header_global_panel.isVisible())
            global_button.click()
            self.assertTrue(page.preview_header_panels["Préparation"].isVisibleTo(
                page.preview_compact_header
            ))
            self.assertEqual(set(page.preview_header_preparation_tabs),
                             {"Prérequis", "À préparer"})
            self.assertTrue(
                page.preview_header_preparation_tabs["À préparer"].isChecked()
            )
            page.preview_header_preparation_tabs["Prérequis"].click()
            self.assertTrue(page.preview_header_prerequisites_host.isVisibleTo(
                page.preview_compact_header
            ))
            self.assertFalse(page.preview_header_materials_host.isVisible())
            page.preview_header_preparation_tabs["À préparer"].click()
            self.assertTrue(page.preview_header_materials_host.isVisibleTo(
                page.preview_compact_header
            ))
            self.assertEqual(page.preview_header_filter.count(), 6)
            page.preview_header_filter.setCurrentText("Objets")
            self.assertEqual(page.preview_header_filter.currentText(), "Objets")

            self.assertEqual(len(page.preview_header_preparation_rows), 3)
            quantity, checkbox = page.preview_header_preparation_rows[1]
            self.assertIsInstance(checkbox, QCheckBox)
            self.assertEqual(quantity.suffix(), " / 1")
            self.assertFalse(checkbox.isChecked())
            checkbox.click()
            self.assertEqual((quantity.value(), checkbox.isChecked()), (1, True))
            row = checkbox.parentWidget().layout()
            self.assertIs(row.itemAt(0).widget(), checkbox)
            self.assertIs(row.itemAt(1).widget(), quantity)
            copy = row.itemAt(2).widget()
            self.assertEqual(copy.objectName(), "GuidePreparationItemCopy")
            QApplication.clipboard().clear()
            copy.click()
            self.assertEqual(QApplication.clipboard().text(), "Clef du donjon")
            page.preview_header_page_jump.setValue(8)
            self.assertIn("fiche 8", page.feedback.text())
            self.assertEqual(page.guide_manual_scroll_sample.objectName(),
                             "GuideManualScroll")
            self.assertTrue(all(
                widget.styleSheet() == "" for widget in page.findChildren(QWidget)
            ))
        finally:
            page.close()
            page.deleteLater()

    def test_guide_catalog_materials_are_real_shared_dev_ui_components(self) -> None:
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            examples = {
                "guide_sample_header": "GuideHeader",
                "guide_sample_category": "GuidesHomeCategory",
                "guide_sample_dofus_card": "GuideDofusCard",
                "guide_sample_active_route": "GuideQuestLineActive",
                "guide_sample_compact_header": "GuideCompactHeader",
            }
            for attr, object_name in examples.items():
                with self.subTest(object_name=object_name):
                    widget = getattr(page, attr)
                    self.assertEqual(widget.objectName(), object_name)
                    self.assertEqual(widget.styleSheet(), "")
            for attr in (
                "guide_sample_header", "guide_sample_category",
                "guide_sample_dofus_card", "guide_sample_compact_header",
            ):
                self.assertIsNotNone(getattr(page, attr).graphicsEffect())
            # Shadows are reserved for static panels, not each selected row.
            self.assertIsNone(page.guide_sample_active_route.graphicsEffect())
        finally:
            page.close()
            page.deleteLater()

    def test_unification_contract_previews_breadcrumb_alerts_and_backdrop(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.unity_palette import (
            UNITY_UI_UNIFICATION_CONTRACT, UNITY_UI_FAMILY_INDEX,
        )

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(page.preview_breadcrumb.objectName(), "GuideBreadcrumb")
            self.assertEqual(page.preview_breadcrumb_current.text(), "Ocre")
            self.assertEqual(page.preview_breadcrumb_current.objectName(),
                             "GuideBreadcrumbCurrent")
            self.assertEqual(set(page.preview_breadcrumb_links),
                             {"Encyclopédie", "Guides", "Dofus"})
            page.preview_breadcrumb_links["Guides"].click()
            self.assertIn("Fil d'Ariane : Guides", page.feedback.text())
            self.assertEqual(page.preview_backdrop.objectName(), "AtlasUnityBackdrop")
            self.assertEqual(set(page.preview_notifications),
                             {"done", "info", "warning", "danger"})
            self.assertEqual(page.preview_contract.rowCount(),
                             len(UNITY_UI_UNIFICATION_CONTRACT))
            # No hidden inventory rows in nested table scroll areas.
            for table, toggle in (
                (page.preview_contract, page.preview_contract_toggle),
                (page.preview_scope, page.preview_scope_toggle),
                (page.preview_secondary_surfaces, page.preview_secondary_toggle),
                (page.preview_mutualization_matrix, page.preview_mutualization_toggle),
                (page.preview_metrics, page.preview_metrics_toggle),
            ):
                self.assertTrue(table.isHidden())
                toggle.click()
                self.assertFalse(table.isHidden())
                self.assertEqual(
                    table.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOff
                )
                self.assertGreater(
                    table.height(), table.horizontalHeader().sizeHint().height()
                )
                self.assertGreaterEqual(
                    table.height(),
                    table.horizontalHeader().sizeHint().height()
                    + sum(table.rowHeight(i) for i in range(table.rowCount()))
                )
                toggle.click()
                self.assertTrue(table.isHidden())
            self.assertEqual(page.gallery_navigation.count(),
                             len(UNITY_UI_FAMILY_INDEX))
            for row, (label, family) in enumerate(UNITY_UI_UNIFICATION_CONTRACT):
                self.assertEqual(page.preview_contract.item(row, 0).text(), label)
                self.assertEqual(
                    page.preview_contract.item(row, 1).text(),
                    UNITY_UI_FAMILY_INDEX[family]["title"],
                )
            index = next(i for i, (_label, family) in
                         enumerate(UNITY_UI_UNIFICATION_CONTRACT)
                         if family == "breadcrumbs")
            page.preview_contract.cellClicked.emit(index, 1)
            self.assertEqual(page.gallery_navigation.currentIndex(),
                             tuple(UNITY_UI_FAMILY_INDEX).index("breadcrumbs"))
            self.assertTrue(all(widget.styleSheet() == ""
                                for widget in page.findChildren(QWidget)))
        finally:
            page.close()
            page.deleteLater()

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
            self.assertEqual(
                page.preview_buttons["selected"].objectName(), "ActiveButton",
            )
            self.assertFalse(page.preview_buttons["disabled"].isEnabled())
            self.assertIsInstance(page.preview_zaap_favorite_button, AtlasButton)
            self.assertEqual(
                page.preview_zaap_favorite_button.objectName(), "favoriteChipName"
            )
            self.assertEqual(page.preview_zaap_favorite_button.styleSheet(), "")
            page.preview_zaap_favorite_button.click()
            self.assertIn("Bouton favori Zaap partagé", page.feedback.text())
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
            from app.ui.components import fit_unity_number_spinbox
            self.assertEqual(
                page.preview_spin.width(),
                fit_unity_number_spinbox(page.preview_spin),
            )
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



    def test_all_dev_ui_sections_are_driven_by_canonical_index(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.unity_palette import UNITY_UI_FAMILY_INDEX

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(
                tuple(page.gallery_family_widgets), tuple(UNITY_UI_FAMILY_INDEX),
            )
            self.assertEqual(
                tuple(page.gallery_navigation.itemText(i)
                      for i in range(page.gallery_navigation.count())),
                tuple(details["title"]
                      for details in UNITY_UI_FAMILY_INDEX.values()),
            )
            for key, group in page.gallery_family_widgets.items():
                with self.subTest(family=key):
                    details = UNITY_UI_FAMILY_INDEX[key]
                    self.assertEqual(group.property("atlasUiFamily"), key)
                    self.assertEqual(group.title(), details["title"])
                    self.assertEqual(group.accessibleName(), details["title"])
                    self.assertIn(details["style_owner"], group.toolTip())
                    from app.ui.ui_registry import UI_FAMILY_QSS_SELECTORS
                    for selector in UI_FAMILY_QSS_SELECTORS[key]:
                        self.assertIn(selector, group.toolTip())
                    for item in details["components"]:
                        self.assertIn(item, group.toolTip())
                    self.assertEqual(group.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_all_indexed_visual_rules_have_global_owners(self) -> None:
        """The gallery must not advertise selectors missing from real QSS."""
        from pathlib import Path
        from app.ui.theme import atlas_stylesheet
        from app.ui.ui_registry import (
            UI_CONSUMER_INDEX, UI_FAMILY_PAINTED_ROLES,
            UI_FAMILY_QSS_SELECTORS, UI_INTERACTION_QSS_SELECTORS,
            validate_ui_index,
        )
        from app.ui.unity_palette import (
            UNITY_ORGANIZER_METRICS_PX, UNITY_PAINTED_UI_ROLES,
        )

        validate_ui_index()
        style = atlas_stylesheet()
        for family, selectors in UI_FAMILY_QSS_SELECTORS.items():
            for selector in selectors:
                with self.subTest(family=family, selector=selector):
                    self.assertIn(selector, style)
        for family, selectors in UI_INTERACTION_QSS_SELECTORS.items():
            for selector in selectors:
                with self.subTest(family=family, interaction=selector):
                    self.assertIn(selector, style)
        self.assertEqual(
            {role for roles in UI_FAMILY_PAINTED_ROLES.values() for role in roles},
            set(UNITY_PAINTED_UI_ROLES),
        )
        root = Path(__file__).resolve().parents[1]
        for module, consumer in UI_CONSUMER_INDEX.items():
            for source in consumer["paths"]:
                with self.subTest(module=module, source=source):
                    self.assertTrue((root / source).is_file())
        self.assertEqual(UNITY_ORGANIZER_METRICS_PX["button_height"], 30)

    def test_painted_roles_and_organizer_metrics_are_visible_in_gallery(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.ui_registry import UI_FAMILY_PAINTED_ROLES
        from app.ui.unity_palette import UNITY_ORGANIZER_METRICS_PX

        page = DevUiPage(on_back=lambda: None)
        try:
            for family, painted in UI_FAMILY_PAINTED_ROLES.items():
                for role in painted:
                    self.assertIn(role, page.gallery_family_widgets[family].toolTip())
            metric_names = {
                page.preview_metrics.item(i, 0).text()
                for i in range(page.preview_metrics.rowCount())
            }
            for key in UNITY_ORGANIZER_METRICS_PX:
                self.assertIn(f"ORGANIZER_{key.upper()}", metric_names)
            self.assertEqual(page.styleSheet(), "")
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
            names = {label.accessibleName() for label in swatches}
            # The source-backed clickable Guide entity colors are real
            # previews, not extra palette tokens. Audit both families.
            from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES
            self.assertEqual(
                names,
                {f"Couleur {role}" for role in PALETTE}
                | {
                    f"Couleur de lien Guide : {name}"
                    for name in ("Monstre", "Boss", "Objet", "Équipement",
                                 "PNJ", "Position", "Quête")
                },
            )
            self.assertEqual(len(ENTITY_LINK_COLOR_ROLES), 7)

            self.assertEqual(set(page.preview_badges), {
                "done", "active", "blocked", "danger", "warning", "info",
                "neutral",
            })
            from app.ui.unity_palette import (
                UNITY_CHIP_TONES, UNITY_INTERACTION_STATES, UNITY_SIZES_PX,
            )
            self.assertEqual(set(page.preview_chips), set(UNITY_CHIP_TONES))
            self.assertEqual(page.preview_interaction_states, UNITY_INTERACTION_STATES)
            self.assertEqual(set(page.preview_text_actions), {"inline_action", "popup_link"})
            self.assertTrue(page.preview_chips["success"].isChecked())
            page.preview_chips["danger"].click()
            self.assertTrue(page.preview_chips["danger"].isChecked())
            self.assertIn("Badge danger activé", page.feedback.text())
            self.assertFalse(page.preview_chips["info"].isChecked())
            self.assertTrue(all(
                not chip.text().startswith("• ")
                and chip.minimumHeight() == 20
                and chip.maximumHeight() == 24
                and chip.cursor().shape() == Qt.PointingHandCursor
                for chip in page.preview_chips.values()
            ))
            self.assertEqual(page.preview_text_actions["inline_action"].styleSheet(), "")
            page.preview_text_actions["inline_action"].click()
            self.assertIn("Détails ouverts", page.feedback.text())
            from app.ui.components import AtlasDialog
            page.preview_text_actions["popup_link"].click()
            self.assertIsInstance(page._preview_dialog, AtlasDialog)
            page._preview_dialog.reject()
            for state, badge in page.preview_badges.items():
                self.assertEqual(badge.objectName(), "StatusBadge")
                self.assertEqual(badge.property("state"), state)
                self.assertNotIn("•", badge.text())
                self.assertEqual(badge.minimumHeight(), UNITY_SIZES_PX["control_compact"])
                self.assertEqual(badge.accessibleName(), f"Statut {badge.text()}")
                self.assertEqual(badge.cursor().shape(), Qt.ArrowCursor)
            self.assertEqual(set(page.preview_cards), {"card", "Panel", "QuestPanel"})
            self.assertEqual(page.preview_busy.minimum(), 0)
            self.assertEqual(page.preview_busy.maximum(), 0)
            self.assertEqual(page.preview_complete.value(), 100)
            self.assertEqual(page.preview_splitter.count(), 2)
            self.assertEqual(page.preview_splitter.objectName(), "DevUiResizeSplitter")
            self.assertEqual(page.preview_splitter.handleWidth(), 6)
            self.assertFalse(page.preview_splitter.childrenCollapsible())
            self.assertEqual(page.preview_slider.objectName(), "DevUiProgressSlider")
            self.assertEqual(page.preview_scroll_list.count(), 8)
            self.assertEqual(page.preview_scope.rowCount(), 18)
            self.assertEqual(page.preview_scope.item(11, 0).text(), "Launcher")
            self.assertEqual(page.preview_scope.item(14, 0).text(), "Paramètres")
            self.assertIn("main.py", page.preview_scope.item(14, 1).toolTip())
            self.assertEqual(page.preview_mutualization_matrix.rowCount(), 18)
            self.assertEqual(page.preview_mutualization_matrix.columnCount(), 5)
            dialog_rows = [
                idx for idx in range(page.preview_mutualization_matrix.rowCount())
                if page.preview_mutualization_matrix.item(idx, 0).text()
                == "Fenêtres et popups classiques"
            ]
            self.assertEqual(len(dialog_rows), 1)
            self.assertIn(
                "Craft : 4/4 unifiés, 0 locaux",
                page.preview_mutualization_matrix.item(dialog_rows[0], 4).text(),
            )
            page.preview_mutualization_matrix.cellClicked.emit(dialog_rows[0], 0)
            from app.ui.unity_palette import UNITY_UI_FAMILY_INDEX
            self.assertEqual(
                page.gallery_navigation.currentIndex(),
                tuple(UNITY_UI_FAMILY_INDEX).index("dialogs"),
            )
            self.assertEqual(page.preview_mutualization_matrix.styleSheet(), "")
            audits = {
                page.preview_mutualization_matrix.item(index, 0).text():
                    page.preview_mutualization_matrix.item(index, 4)
                for index in range(page.preview_mutualization_matrix.rowCount())
            }
            self.assertIn("0 QSS local", audits["Bordures et arrondis"].text())
            self.assertIn(
                "largeur(s) littérale(s) à revoir",
                audits["Scrollbars et resize"].text(),
            )
            self.assertIn(
                "QDialog natif(s) à qualifier",
                audits["Fenêtres et popups classiques"].text(),
            )
            self.assertIn(
                "guides_view.py",
                audits["Fenêtres et popups classiques"].toolTip(),
            )
            self.assertEqual(page.preview_secondary_surfaces.rowCount(), 15)
            unique_cases = {
                (
                    page.preview_secondary_surfaces.item(index, 1).text(),
                    page.preview_secondary_surfaces.item(index, 2).toolTip(),
                )
                for index in range(page.preview_secondary_surfaces.rowCount())
            }
            self.assertEqual(len(unique_cases), 15)
            self.assertEqual(
                sum(label == "PreloadProgressPopup" for label, _ in unique_cases),
                1,
            )
            actual = {
                page.preview_secondary_surfaces.item(index, 1).text()
                for index in range(page.preview_secondary_surfaces.rowCount())
            }
            for name in ("PreloadProgressPopup", "CloseActionDialog",
                         "CraftResourceDialog", "LevelingDialog",
                         "ZaapSuggestionPopup", "GuideImagePopup",
                         "Organizer radial", "Splash Unity"):
                self.assertIn(name, actual)
            self.assertEqual(page.preview_secondary_surfaces.styleSheet(), "")
            self.assertTrue(all(
                page.preview_secondary_surfaces.item(index, 2).toolTip().endswith(".py")
                for index in range(page.preview_secondary_surfaces.rowCount())
            ))
            self.assertTrue(all(
                "/" not in page.preview_secondary_surfaces.item(index, 2).text()
                for index in range(page.preview_secondary_surfaces.rowCount())
            ))
            self.assertIn("Tk", page.preview_scope.item(11, 1).text())
            self.assertIn(
                "app/distribution/launcher_ui.py",
                page.preview_scope.item(11, 1).toolTip(),
            )
            self.assertIn("Organizer", page.preview_scope.item(8, 0).text())
            self.assertIn(
                "app/ui/organizer_style.py",
                page.preview_scope.item(8, 1).toolTip(),
            )
            from app.ui.unity_palette import UNITY_ICON_NAMES, UNITY_ICON_PENDING
            self.assertEqual(
                set(page.preview_icon_labels),
                set(UNITY_ICON_NAMES) | set(UNITY_ICON_PENDING),
            )
            self.assertEqual(page.preview_icon_grid.count(),
                             len(UNITY_ICON_NAMES) + len(UNITY_ICON_PENDING))
            self.assertEqual(page.preview_icon_grid.getItemPosition(7),
                             (1, 3, 1, 1))
            self.assertEqual(page.preview_icon_grid.getItemPosition(13),
                             (3, 1, 1, 1))
            self.assertEqual(set(page.preview_icon_missing), set(UNITY_ICON_PENDING))
            self.assertTrue(any(
                label.text() == "Non détecté ici"
                for label in page.findChildren(QLabel)
            ))
            self.assertTrue(any(
                label.text().startswith("Sources Unity communes :")
                for label in page.findChildren(QLabel)
            ))
            for index in range(page.preview_icon_grid.count()):
                cell = page.preview_icon_grid.itemAt(index).widget()
                self.assertEqual(cell.objectName(), "DevUiIconCell")
                self.assertEqual(cell.styleSheet(), "")
            self.assertEqual(page.preview_tree.objectName(), "QuestHierarchyTree")
            self.assertEqual(page.preview_tree.styleSheet(), "")
            self.assertEqual(page.preview_tree.columnWidth(1), 150)
            self.assertFalse(page.preview_table.showGrid())
            self.assertFalse(page.preview_scope.showGrid())
            self.assertFalse(page.preview_table.alternatingRowColors())
            self.assertFalse(page.preview_tree.alternatingRowColors())
            self.assertFalse(page.preview_metrics.alternatingRowColors())
            self.assertFalse(page.preview_scope.alternatingRowColors())
            self.assertFalse(page.gallery_navigation.view().alternatingRowColors())
            from app.ui.components import AtlasComboBox, UnityPopupSeparatorDelegate
            from app.modules.encyclopedia.widgets.filter_panel import AchievementFilterPanel
            self.assertIsInstance(
                page.gallery_navigation.view().itemDelegate(),
                UnityPopupSeparatorDelegate,
            )
            for combo in (page.preview_combo, page.guide_ultime_combo):
                self.assertIsInstance(combo, AtlasComboBox)
                self.assertIsInstance(combo.view().itemDelegate(), UnityPopupSeparatorDelegate)
            filters = AchievementFilterPanel(parent=page)
            self.assertIsInstance(filters.category_combo, AtlasComboBox)
            self.assertIsInstance(
                filters.category_combo.view().itemDelegate(), UnityPopupSeparatorDelegate
            )
            from app.ui.components import fit_unity_number_spinbox
            for selector in (filters.min_level, filters.max_level):
                self.assertEqual(selector.minimum(), 0)
                self.assertEqual(selector.maximum(), 999)
                self.assertEqual(selector.width(), fit_unity_number_spinbox(selector))
                self.assertEqual(selector.styleSheet(), "")
            self.assertEqual(page.gallery_navigation.count(), len(page.gallery_sections))
            self.assertEqual(page.gallery_navigation.objectName(), "DevUiFamilyCombo")
            from PySide6.QtWidgets import QStyleOptionViewItem
            row_hint = page.gallery_navigation.view().itemDelegate().sizeHint(
                QStyleOptionViewItem(),
                page.gallery_navigation.model().index(0, 0),
            )
            self.assertGreaterEqual(row_hint.height(), 24)
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
            self.assertIn("QGroupBox::title", css)
            self.assertIn("#StatusChip {\n    background: transparent;", css)
            self.assertIn("#StatusBadge, #ActivityBadge {\n    background: transparent;", css)
            self.assertIn("border-top: 2px solid", css)
            self.assertIn("border-left: 2px solid", css)
            self.assertIn("#StatusBadge[state=\"danger\"]", css)
            self.assertIn("#StatusChip[tone=\"success\"]:hover", css)
            self.assertIn("#StatusChip[tone=\"danger\"]:checked", css)
            self.assertIn("#InlineActionButton:hover", css)
            self.assertIn("#PopupLinkButton:focus", css)
            self.assertIn("#TopNavButtonActive:hover", css)
            self.assertIn("QTabBar::tab:selected", css)
            self.assertIn("QWidget#DevUiPage QLabel#DevUiMissingIcon", css)
            self.assertIn("QSlider::groove:horizontal", css)
            self.assertIn("QSlider::sub-page:horizontal", css)
            self.assertIn("QSlider::add-page:horizontal", css)
            self.assertIn("QSlider::handle:horizontal", css)
            self.assertIn("background: #213154;", css)
            self.assertIn("QScrollArea#DevUiGalleryScroll", css)
            group_style = css.split("QGroupBox {", 1)[1].split("}", 1)[0]
            card_style = css.split(
                "#card, #OrganizerPanel, #Panel, #CraftPanel, #QuestPanel {", 1
            )[1].split("}", 1)[0]
            for common_gradient in (
                "stop:0 rgba(33, 49, 84, 0.82)",
                "stop:1 rgba(27, 39, 70, 0.88)",
            ):
                self.assertIn(common_gradient, group_style)
                self.assertIn(common_gradient, card_style)
            self.assertIn("QSplitter::handle:horizontal", css)
            self.assertIn("QWidget#DevUiPage QListWidget QScrollBar:vertical", css)
            self.assertIn("QWidget#DevUiPage QListWidget QScrollBar::add-page:vertical", css)
            self.assertIn("QWidget#DevUiPage QListWidget QScrollBar::sub-page:vertical", css)
            self.assertIn("QWidget#DevUiPage QScrollArea#DevUiGalleryScroll QScrollBar:vertical", css)
            self.assertIn("QScrollBar:vertical", css)
            self.assertIn("QScrollBar::add-page:vertical", css)
            self.assertIn("QScrollBar::sub-page:vertical", css)
            # The same palette and list surfaces now apply globally, while
            # the real shell wallpaper and widget behavior stay unchanged.
            self.assertIn("QGroupBox {", css)
            self.assertIn("QComboBox QAbstractItemView", css)
            self.assertIn("QFrame#GuideUltimeGeneratedView", css)
            self.assertIn("alternate-background-color: rgba(27, 39, 70, 0.95)", css)
            self.assertIn("#card, #OrganizerPanel, #Panel, #CraftPanel, #QuestPanel", css)
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
            self.assertIn("QTreeWidget::item", css)
            self.assertIn("#SecondaryButton:checked", css)
            self.assertIn("background: #9FCE51;", css)
            self.assertIn("font-size: 14px;", css)
            self.assertEqual(page.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_achievement_entity_rows_keep_central_colors_and_click_owner(self) -> None:
        from app.modules.encyclopedia.models.entity_ref import EntityRef
        from app.modules.encyclopedia.widgets.achievement_entity_section import (
            AchievementEntityRow,
        )
        from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES
        from app.ui.theme import PALETTE

        for kind in ("monster", "boss", "item", "equipment", "quest", "npc"):
            with self.subTest(kind=kind):
                row = AchievementEntityRow(EntityRef(kind, 42, "Exemple <test>"))
                try:
                    label = row.findChild(QLabel, "AchievementEntityRowText")
                    self.assertIsNotNone(label)
                    self.assertIn(
                        f'color:{PALETTE[ENTITY_LINK_COLOR_ROLES[kind]]}',
                        label.text(),
                    )
                    self.assertIn("Exemple &lt;test&gt;", label.text())
                    self.assertTrue(
                        label.testAttribute(Qt.WA_TransparentForMouseEvents)
                    )
                    self.assertEqual(row.entity.entity_type, kind)
                    self.assertEqual(row.entity.entity_id, 42)
                finally:
                    row.close()
                    row.deleteLater()

        # Unsupported/before-business-module categories stay plain text.
        row = AchievementEntityRow(EntityRef("dungeon", 5, "Donjon test"))
        try:
            self.assertEqual(
                row.findChild(QLabel, "AchievementEntityRowText").text(),
                "Donjon test",
            )
        finally:
            row.close()
            row.deleteLater()

    def test_guide_preparation_copy_color_has_one_live_qt_style_owner(self) -> None:
        """Inspect the actual Unity control and its unique canonical QSS rule.

        Pixel assertions on scroll-area descendants are unreliable in Windows
        Qt offscreen; the workflow separately captures the real raster.
        """
        from PySide6.QtWidgets import QApplication
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import atlas_stylesheet, PALETTE
        from app.ui.unity_skin import unity_skin_stylesheet

        page = DevUiPage(on_back=lambda: None)
        try:
            page.resize(1440, 900)
            page.show()
            page.preview_header_controls["Progression globale"].setChecked(True)
            page.preview_header_controls["Préparation"].setChecked(True)
            QApplication.processEvents()
            button = page.preview_header_preparation_names[0]
            self.assertTrue(button.isVisible())
            self.assertTrue(button.isEnabled())
            self.assertFalse(button.isFlat())
            self.assertEqual(button.objectName(), "GuidePreparationItemCopy")
            self.assertEqual(button.styleSheet(), "")
            qss = atlas_stylesheet()
            selector = "QPushButton#GuidePreparationItemCopy {"
            self.assertEqual(qss.count(selector), 1)
            rule = qss.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn(f"color: {PALETTE['GREEN']};", rule)
            self.assertNotIn(selector, unity_skin_stylesheet())
        finally:
            page.close()
            page.deleteLater()
            QApplication.processEvents()

    def test_shared_item_copy_buttons_use_indexed_item_color(self) -> None:
        from app.ui.theme import atlas_stylesheet, PALETTE
        from app.ui.entity_link_roles import ENTITY_LINK_COLOR_ROLES

        css = atlas_stylesheet()
        self.assertIn(
            "QPushButton#GuideItemNameButton {", css
        )
        self.assertIn(
            f"color: {PALETTE[ENTITY_LINK_COLOR_ROLES['item']]};", css,
        )
        self.assertIn(f"color: {PALETTE['GREEN_HOVER']};", css)

    def test_guide_entity_colors_use_one_unity_index_and_are_visible(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import PALETTE, GUIDE_ENTITY_LINK_COLORS
        from app.ui.unity_palette import GUIDE_ENTITY_LINK_ROLES

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(
                set(page.preview_guide_link_labels), set(GUIDE_ENTITY_LINK_ROLES)
            )
            for category, role in GUIDE_ENTITY_LINK_ROLES.items():
                with self.subTest(category=category):
                    color = PALETTE[role]
                    self.assertEqual(GUIDE_ENTITY_LINK_COLORS[category], color)
                    sample = page.preview_guide_link_labels[category]
                    self.assertIn(f"color:{color}", sample.text())
                    self.assertIn(f'href="dev-preview:{category}"', sample.text())
                    self.assertFalse(sample.openExternalLinks())
                    self.assertIn(category, sample.toolTip())
                    sample.linkActivated.emit(f"dev-preview:{category}")
                    self.assertIn(
                        f"Aperçu lien sémantique : {category}",
                        page.feedback.text(),
                    )
            self.assertEqual(
                len({GUIDE_ENTITY_LINK_COLORS[key] for key in (
                    "monster", "boss", "item", "equipment", "npc", "position"
                )}), 6
            )
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

            from app.ui.unity_palette import UNITY_ICON_PENDING
            self.assertEqual(set(page.preview_icon_labels),
                             set(UNITY_ICON_NAMES) | set(UNITY_ICON_PENDING))
            from app.ui.unity_skin import unity_original_preview_icon
            self.assertTrue(all(
                not unity_original_preview_icon(name).isNull()
                for name in UNITY_ICON_NAMES
            ))
            self.assertTrue(all(
                label.pixmap() is not None and not label.pixmap().isNull()
                for name, label in page.preview_icon_labels.items()
                if name in UNITY_ICON_NAMES
            ))
            self.assertTrue(all(
                (page.preview_icon_labels[name].pixmap() is None
                 or page.preview_icon_labels[name].pixmap().isNull())
                for name in UNITY_ICON_PENDING
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

    def test_motion_gallery_replays_three_real_qt_animations(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(
                set(page.motion_buttons),
                {"apparition", "panneau", "progression"},
            )
            self.assertEqual(set(page.motion_animations), set(page.motion_buttons))
            self.assertTrue(all(
                isinstance(animation, QPropertyAnimation)
                for animation in page.motion_animations.values()
            ))
            self.assertTrue(all(
                animation.easingCurve().type() == QEasingCurve.OutCubic
                for animation in page.motion_animations.values()
            ))
            self.assertEqual(page.motion_duration.value(), 180)
            self.assertTrue(all(button.styleSheet() == ""
                                for button in page.motion_buttons.values()))

            # Directly advance the real Qt animation clock: deterministic and
            # independent of CI host performance or a Windows display server.
            page.motion_buttons["apparition"].click()
            self.assertIn("apparition", page.feedback.text())
            fade = page.motion_animations["apparition"]
            fade.setCurrentTime(fade.duration())
            self.assertAlmostEqual(page.motion_opacity.opacity(), 1.0)

            page.motion_duration.setValue(240)
            page.motion_buttons["panneau"].click()
            panel = page.motion_animations["panneau"]
            self.assertEqual(panel.duration(), 240)
            panel.setCurrentTime(panel.duration())
            self.assertEqual(
                page.motion_panel.maximumHeight(), page._motion_panel_height
            )

            page.motion_buttons["progression"].click()
            progress = page.motion_animations["progression"]
            self.assertEqual(progress.duration(), 240)
            progress.setCurrentTime(progress.duration())
            self.assertEqual(page.motion_progress.value(), 100)

            # Replaying does not leave a second animation attached to a widget.
            page.motion_buttons["apparition"].click()
            self.assertEqual(len(page.motion_animations), 3)
            self.assertEqual(page.motion_fade_card.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_dev_ui_asset_fallback_is_explicit_without_pretend_artwork(self) -> None:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import atlas_stylesheet

        with TemporaryDirectory() as folder:
            invalid_wallpaper = Path(folder) / "background_selection_clean.png"
            invalid_wallpaper.write_bytes(b"unreadable image")
            with patch("app.ui.unity_skin.wallpaper_path", return_value=invalid_wallpaper):
                page = DevUiPage(on_back=lambda: None)
        try:
            self.assertFalse(page.preview_backdrop.has_wallpaper)
            self.assertIn("dégradé Unity de secours",
                          page.preview_wallpaper_status.text())
            self.assertEqual(page.preview_wallpaper_status.styleSheet(), "")
            self.assertEqual(page.preview_backdrop.height(),
                             5 * 32)
            self.assertIn(
                "QWidget#DevUiPage QLabel#DevUiMissingIcon",
                atlas_stylesheet(),
            )
            self.assertTrue(all(section.graphicsEffect() is not None
                                for section in page.gallery_sections))
        finally:
            page.close()
            page.deleteLater()


    def test_responsive_dimensions_preview_keeps_panels_in_place(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.unity_palette import (
            UNITY_LAYOUT_PROFILE_PX, UNITY_LAYOUT_SIZES_PX,
            UNITY_WINDOW_PRESETS_PX, unity_layout_metrics,
        )

        page = DevUiPage(on_back=lambda: None)
        try:
            self.assertEqual(page.preview_window_selector.count(), 4)
            self.assertEqual(len(page.preview_responsive_cards), 3)
            self.assertEqual(
                page.preview_responsive_host.maximumWidth(),
                UNITY_WINDOW_PRESETS_PX["standard"][0]
                - 2 * UNITY_LAYOUT_SIZES_PX["page_margin"],
            )
            stable_positions = ((0, 0, 1, 2), (0, 2, 1, 1), (0, 3, 1, 1))
            for available in (480, 850, 1100, 1250, 1600, 1850):
                page._relayout_responsive_cards(available)
                self.assertEqual(page.preview_responsive_columns, 3)
                positions = tuple(
                    page.preview_responsive_grid.getItemPosition(
                        page.preview_responsive_grid.indexOf(card)
                    )
                    for card in page.preview_responsive_cards
                )
                self.assertEqual(positions, stable_positions)
                expected = unity_layout_metrics(min(available, 1180))
                self.assertEqual(
                    page.preview_responsive_grid.spacing(), expected["module_gap"]
                )
            for name, (width, height) in UNITY_WINDOW_PRESETS_PX.items():
                index = page.preview_window_selector.findData(name)
                self.assertGreaterEqual(index, 0)
                page.preview_window_selector.setCurrentIndex(index)
                self.assertEqual(
                    page.preview_responsive_host.maximumWidth(),
                    width - 2 * UNITY_LAYOUT_SIZES_PX["page_margin"],
                )
                self.assertIn(f"{width} × {height}", page.preview_window_description.text())
                self.assertEqual(page.preview_responsive_columns, 3)
                self.assertEqual(
                    tuple(
                        page.preview_responsive_grid.getItemPosition(
                            page.preview_responsive_grid.indexOf(card)
                        )
                        for card in page.preview_responsive_cards
                    ),
                    stable_positions,
                )
            self.assertTrue(
                any(
                    page.preview_metrics.item(i, 0).text()
                    == "PROFILE_STANDARD_MODULE_GAP"
                    for i in range(page.preview_metrics.rowCount())
                )
            )
            self.assertTrue(all(
                card.objectName() == "card" for card in page.preview_responsive_cards
            ))
            self.assertEqual(page.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()



    def test_all_gallery_families_use_shared_geometry_on_each_window_size(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import atlas_stylesheet
        from app.ui.unity_palette import (
            UNITY_CONTROL_LIMITS, UNITY_CONTROL_SIZES_PX,
            UNITY_LAYOUT_SIZES_PX, UNITY_WINDOW_PRESETS_PX,
            unity_layout_metrics,
        )
        from app.ui.unity_skin import UnityBackdrop
        from PySide6.QtWidgets import QVBoxLayout

        previous_style = self.app.styleSheet()
        self.app.setStyleSheet(atlas_stylesheet())
        backdrop = UnityBackdrop()
        layout = QVBoxLayout(backdrop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        page = DevUiPage(parent=backdrop)
        layout.addWidget(page)
        try:
            original_order = tuple(page.gallery_family_widgets)
            self.assertEqual(len(page._gallery_section_layouts), len(original_order))
            self.assertEqual(
                page.gallery_navigation.maxVisibleItems(),
                UNITY_CONTROL_LIMITS["dropdown_visible_rows"],
            )
            for key, (width, height) in UNITY_WINDOW_PRESETS_PX.items():
                with self.subTest(viewport=key):
                    backdrop.resize(width, height)
                    backdrop.show()
                    self.app.processEvents()
                    expected = unity_layout_metrics(page.width())
                    margins = page._gallery_outer_layout.contentsMargins()
                    self.assertEqual(margins.left(), expected["page_margin"])
                    self.assertEqual(margins.right(), expected["page_margin"])
                    self.assertEqual(
                        page._gallery_content_layout.spacing(),
                        expected["module_gap"],
                    )
                    for section_layout in page._gallery_section_layouts:
                        self.assertEqual(
                            section_layout.contentsMargins().left(),
                            expected["module_padding"],
                        )
                        self.assertEqual(
                            section_layout.contentsMargins().right(),
                            expected["module_padding"],
                        )
                    self.assertEqual(tuple(page.gallery_family_widgets), original_order)
                    # Nested Preparation uses the same horizontal reference
                    # but stays inset under its own global disclosure.
                    page.gallery_scroll.ensureWidgetVisible(page.preview_compact_header)
                    for opened in (False, True):
                        for name in ("Progression globale", "Préparation", "Personnages"):
                            page.preview_header_controls[name].setChecked(opened)
                        self.app.processEvents()

                        def span(widget) -> tuple[int, int]:
                            left = widget.mapTo(page, widget.rect().topLeft()).x()
                            return left, left + widget.width()

                        full = span(page.preview_header_global_progress)
                        preparation = span(page.preview_header_metrics["Préparation"])
                        self.assertGreaterEqual(preparation[0], full[0])
                        self.assertLessEqual(preparation[1], full[1])
                        self.assertGreater(preparation[1], preparation[0])
                        if opened:
                            self.assertTrue(
                                page.preview_header_panels["Progression globale"].isVisibleTo(
                                    page.preview_compact_header
                                )
                            )
                            self.assertTrue(
                                page.preview_header_panels["Préparation"].isVisibleTo(
                                    page.preview_compact_header
                                )
                            )
            self.assertEqual(
                page.preview_header_global_progress.height(),
                UNITY_CONTROL_SIZES_PX["progress_primary"],
            )
            self.assertEqual(
                page.preview_header_metrics["Préparation"].height(),
                UNITY_CONTROL_SIZES_PX["progress_secondary"],
            )
            for toggle in page.preview_header_controls.values():
                if toggle.objectName() in ("GuideMetricDropdown", "GuideParticipantsButton"):
                    expected_width = (
                        UNITY_CONTROL_SIZES_PX["guide_character_button"]
                        if toggle.objectName() == "GuideParticipantsButton"
                        else UNITY_CONTROL_SIZES_PX["progress_toggle_width"]
                    )
                    self.assertEqual(toggle.width(), expected_width)
            row_names = {
                page.preview_metrics.item(i, 0).text()
                for i in range(page.preview_metrics.rowCount())
            }
            self.assertIn("LIMIT_DROPDOWN_VISIBLE_ROWS", row_names)
            self.assertIn("GUIDE_READING_ROW_SPACING", row_names)
            self.assertIn("GUIDE_READING_SOURCE_DRAWER_MAX_HEIGHT", row_names)
        finally:
            backdrop.close()
            page.deleteLater()
            backdrop.deleteLater()
            self.app.setStyleSheet(previous_style)

    def test_module_geometry_inventory_displays_actual_owner_and_values(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.unity_palette import (
            UNITY_MODULE_GEOMETRY_PX, UNITY_MODULE_GEOMETRY_OWNERS,
        )
        page = DevUiPage(on_back=lambda: None)
        try:
            table = page.preview_module_geometry
            self.assertFalse(table.isVisible())
            self.assertEqual(
                table.rowCount(),
                sum(map(len, UNITY_MODULE_GEOMETRY_PX.values())),
            )
            actual = {
                (table.item(row, 0).text(), table.item(row, 1).text())
                for row in range(table.rowCount())
            }
            expected = {
                (module, role)
                for module, roles in UNITY_MODULE_GEOMETRY_PX.items()
                for role in roles
            }
            self.assertEqual(actual, expected)
            for row in range(table.rowCount()):
                module = table.item(row, 0).text()
                self.assertEqual(
                    table.item(row, 0).toolTip(),
                    UNITY_MODULE_GEOMETRY_OWNERS[module],
                )
            self.assertEqual(page.styleSheet(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_responsive_reference_fits_all_real_window_presets(self) -> None:
        from app.pages.dev_ui_page import DevUiPage
        from app.ui.theme import atlas_stylesheet
        from app.ui.unity_palette import (
            UNITY_WINDOW_PRESETS_PX,
        )
        from app.ui.unity_skin import UnityBackdrop
        from PySide6.QtWidgets import QVBoxLayout
        # Same true widget tree as tools.dev_ui_snapshot: the viewport must
        # belong to a styled shell, not a free-floating QWidget.
        previous_style = self.app.styleSheet()
        self.app.setStyleSheet(atlas_stylesheet())
        backdrop = UnityBackdrop()
        layout = QVBoxLayout(backdrop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        page = DevUiPage(on_back=lambda: None, parent=backdrop)
        layout.addWidget(page)
        try:
            for key, (width, height) in UNITY_WINDOW_PRESETS_PX.items():
                with self.subTest(preset=key):
                    # The real capture also selects the reference profile
                    # before resizing; otherwise the standard 1148px cap
                    # remains active during the 900px fixture.
                    index = page.preview_window_selector.findData(key)
                    self.assertGreaterEqual(index, 0)
                    page.preview_window_selector.setCurrentIndex(index)
                    backdrop.resize(width, height)
                    backdrop.show()
                    self.app.processEvents()
                    # Real horizontal-fit proof is owned by the exact-SHA
                    # styled Windows capture at all four presets. A standalone
                    # test can retain native min-size hints from other tests;
                    # it checks the responsive algorithm, not those hints.
                    self.assertEqual(page.preview_responsive_columns, 3)
                    self.assertEqual(
                        tuple(
                            page.preview_responsive_grid.getItemPosition(
                                page.preview_responsive_grid.indexOf(card)
                            )
                            for card in page.preview_responsive_cards
                        ),
                        ((0, 0, 1, 2), (0, 2, 1, 1), (0, 3, 1, 1)),
                    )
                    self.assertLessEqual(
                        page.preview_responsive_host.width(), width
                    )
        finally:
            backdrop.close()
            page.deleteLater()
            backdrop.deleteLater()
            self.app.setStyleSheet(previous_style)

    def test_gallery_renders_real_qt_full_height_in_reduced_window(self) -> None:
        """Viewport and full scroll content must be real, grab-able Qt pixels."""
        from app.pages.dev_ui_page import DevUiPage

        page = DevUiPage(on_back=lambda: None)
        try:
            page.resize(900, 680)
            page.show()
            self.app.processEvents()
            combo = page.gallery_navigation
            label = next(label for label in page.findChildren(QLabel) if label.buddy() is combo)
            self.assertLess(combo.x() - label.geometry().right(), 16)
            self.assertEqual(page.gallery_navigation.count(), len(page.gallery_sections))
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
            combo = page.gallery_navigation
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key_End)
            self.app.processEvents()
            self.assertGreater(bar.maximum(), 0)
            self.assertGreater(bar.value(), 0)
            self.assertEqual(combo.currentText(), "Palette Unity · source de vérité")

            bar.setValue(0)
            combo.showPopup()
            self.app.processEvents()
            view = combo.view()
            current = view.model().index(combo.currentIndex(), 0)
            QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(current).center())
            self.app.processEvents()
            self.assertGreater(bar.value(), 0)
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
