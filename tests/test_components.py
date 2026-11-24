"""Direct Qt contracts for the shared UI components — no DOFUS runtime."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QSizePolicy, QSpinBox, QWidget

from app.ui.components import (
    AtlasButton,
    AtlasBreadcrumb,
    AtlasDialog,
    AtlasPageTitle,
    AtlasPanelToggle,
    AtlasStatusBadge,
    BUTTON_OBJECT_NAMES,
    fit_unity_number_spinbox,
    refresh_unity_widget_style,
    set_unity_widget_property,
    set_unity_widget_object_name,
    release_transient_dialog,
    clear_current_dialog_reference,
    fill_unity_navigation_menu,
    configure_unity_scroll_area,
)
from app.ui.theme import atlas_stylesheet


class SharedUiComponentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_shared_guide_portrait_donut_and_symbol_geometry(self) -> None:
        from app.ui.components import (
            AtlasGuideParticipantPortrait, AtlasGuideProgressDonut, atlas_guide_symbol_icon,
        )
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX
        portrait = AtlasGuideParticipantPortrait("character:1", progress=150)
        donut = AtlasGuideProgressDonut()
        try:
            self.assertEqual(portrait.progress, 100)
            self.assertEqual(portrait.width(), UNITY_CONTROL_SIZES_PX["guide_portrait_button"])
            self.assertEqual(donut.width(), UNITY_CONTROL_SIZES_PX["guide_donut_box"])
            donut.set_percent(-5)
            self.assertEqual(donut._percent, 0)
            first = atlas_guide_symbol_icon(portrait, "people")
            second = atlas_guide_symbol_icon(donut, "people")
            self.assertFalse(first.isNull())
            self.assertEqual(first.cacheKey(), second.cacheKey())
            from app.ui.components import atlas_quest_shortcut_icon
            self.assertEqual(atlas_quest_shortcut_icon().cacheKey(), atlas_quest_shortcut_icon().cacheKey())
        finally:
            portrait.deleteLater()
            donut.deleteLater()

    def test_shared_symbol_icons_scale_without_clipping(self) -> None:
        from app.ui.components import atlas_guide_symbol_icon, atlas_quest_shortcut_icon
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        parent = QWidget()
        try:
            for size in (12, 18, 36):
                pixmap = atlas_guide_symbol_icon(parent, "cube", size=size).pixmap(size, size)
                image = pixmap.toImage()
                self.assertEqual((image.width(), image.height()), (size, size))
                # The icon should have artwork in both halves, not be clipped
                # at the former fixed 18-pixel coordinates.
                for left, right in ((0, size // 2), (size // 2, size)):
                    self.assertTrue(any(
                        image.pixelColor(x, y).alpha() > 0
                        for x in range(left, right) for y in range(size)
                    ))
            with patch.dict(UNITY_CONTROL_SIZES_PX, {"guide_quest_shortcut_icon": 30}):
                self.assertEqual(atlas_quest_shortcut_icon().availableSizes()[0].width(), 30)
        finally:
            parent.deleteLater()

    def test_shared_guide_header_owns_controls_and_sheet_navigation(self) -> None:
        from app.ui.components import AtlasGuideReadingHeader, AtlasGuideSheetHeader
        header = AtlasGuideReadingHeader("Guide exemple")
        sheet = AtlasGuideSheetHeader("Fiche exemple", total=20, page=4)
        panel = QWidget()
        header.attach_preparation(panel)
        try:
            self.assertIs(header.content_layout.itemAt(1).widget(), header.participants_panel)
            self.assertIs(header.preparation_bar.parentWidget(), header.global_details_panel)
            header.global_details_button.click()
            header.preparation_button.click()
            self.assertTrue(panel.isVisibleTo(header))
            header.participants_button.click()
            self.assertTrue(header.participants_panel.isVisibleTo(header))
            self.assertTrue(panel.isVisibleTo(header))
            seen = []
            sheet.page_jump.valueChanged.connect(seen.append)
            sheet.set_page(10, 20)
            self.assertEqual(seen, [])
            self.assertEqual(sheet.page_jump.value(), 10)
            self.assertEqual(sheet.page_jump.suffix(), "/20")
            sheet.page_jump.setValue(11)
            self.assertEqual(seen, [11])
        finally:
            header.deleteLater()
            sheet.deleteLater()

    def test_guide_overview_uses_same_shell_without_invented_preparation(self) -> None:
        from app.ui.components import AtlasGuideReadingHeader
        header = AtlasGuideReadingHeader("Guide classique", overview=True)
        try:
            self.assertEqual(header.objectName(), "GuideHeader")
            self.assertFalse(hasattr(header, "preparation_button"))
            self.assertFalse(hasattr(header, "participants_button"))
            header.set_overview_progress(2, 5)
            self.assertEqual(header.global_progress_label.text(), "2/5")
            self.assertEqual(header.global_progress_bar.value(), 2)
            self.assertEqual(header.global_progress_bar.maximum(), 5)
            header.set_overview_progress(0, 0)
            self.assertEqual(header.global_progress_label.text(), "—")
            header.set_overview_progress(2, 5, visible=False)
            self.assertTrue(header.global_progress_bar.isHidden())
            self.assertTrue(header.global_progress_label.isHidden())
        finally:
            header.deleteLater()

    def test_shared_dialog_add_header_preserves_single_indexed_widget(self) -> None:
        from app.ui.components import AtlasDialogHeader

        dialog = AtlasDialog()
        try:
            title = dialog.add_header("Titre", "Sous-titre")
            self.assertIsInstance(title, AtlasDialogHeader)
            self.assertIs(title.parentWidget(), dialog)
            self.assertIs(dialog.content_layout.itemAt(0).widget(), title)
            self.assertEqual(len(dialog.findChildren(AtlasDialogHeader)), 1)
            self.assertEqual(title.title_label.text(), "Titre")
            self.assertEqual(title.subtitle_label.text(), "Sous-titre")
            self.assertEqual(title.styleSheet(), "")
        finally:
            dialog.deleteLater()

    def test_progress_geometry_and_format_use_shared_configuration(self) -> None:
        from PySide6.QtWidgets import QProgressBar
        from app.ui.components import configure_unity_progress_bar
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        for role in ("progress_primary", "progress_secondary",
                     "progress_home_compact", "progress_route", "progress_generated_route"):
            with self.subTest(role=role):
                bar = QProgressBar()
                try:
                    self.assertIs(configure_unity_progress_bar(
                        bar, maximum=3, text_visible=True, height_role=role,
                        expanding=True, display_format="%p %"), bar)
                    bar.setValue(2)
                    self.assertEqual((bar.minimum(), bar.maximum(), bar.value()), (0, 3, 2))
                    self.assertEqual(bar.minimumHeight(), UNITY_CONTROL_SIZES_PX[role])
                    self.assertEqual(bar.maximumHeight(), UNITY_CONTROL_SIZES_PX[role])
                    self.assertEqual(bar.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
                    self.assertEqual(bar.sizePolicy().verticalPolicy(), QSizePolicy.Fixed)
                    self.assertEqual(bar.format(), "%p %")
                    self.assertTrue(bar.isTextVisible())
                finally:
                    bar.deleteLater()

    def test_shared_tool_button_keeps_native_state_and_callbacks(self) -> None:
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QToolButton
        from app.ui.components import configure_unity_tool_button

        button = QToolButton()
        button.setCheckable(True)
        calls = []
        button.clicked.connect(calls.append)
        try:
            self.assertIs(configure_unity_tool_button(
                button, object_name="ResourceTile", box=(56, 42), icon_size=16,
                text="Test", pointing=True, focus_policy=Qt.NoFocus,
            ), button)
            self.assertEqual(button.minimumSize(), QSize(56, 42))
            self.assertEqual(button.maximumSize(), QSize(56, 42))
            self.assertEqual(button.iconSize(), QSize(16, 16))
            self.assertEqual(button.objectName(), "ResourceTile")
            self.assertEqual(button.cursor().shape(), Qt.PointingHandCursor)
            self.assertEqual(button.focusPolicy(), Qt.NoFocus)
            button.click()
            self.assertEqual(calls, [True])
        finally:
            button.deleteLater()

    def test_shared_scroll_defaults_preserve_native_frame_and_optional_vertical_policy(self) -> None:
        from PySide6.QtWidgets import QFrame, QScrollArea

        area = QScrollArea()
        original_frame = area.frameShape()
        try:
            self.assertIs(configure_unity_scroll_area(area), area)
            self.assertTrue(area.widgetResizable())
            self.assertEqual(area.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertEqual(area.frameShape(), original_frame)
            configure_unity_scroll_area(
                area, borderless=True, vertical_policy=Qt.ScrollBarAlwaysOn,
            )
            self.assertEqual(area.frameShape(), QFrame.NoFrame)
            self.assertEqual(area.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOn)
            self.assertEqual(area.styleSheet(), "")
        finally:
            area.deleteLater()

    def test_shared_dialog_scroll_slot_keeps_native_scrolling(self) -> None:
        from PySide6.QtWidgets import QLabel, QScrollArea

        dialog = AtlasDialog(density="compact")
        try:
            rows = dialog.add_scroll_rows()
            rows.addWidget(QLabel("Ligne de test"))
            area = dialog.findChild(QScrollArea)
            self.assertIsNotNone(area)
            self.assertTrue(area.widgetResizable())
            self.assertEqual(area.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertIs(rows.parentWidget(), area.widget())
            self.assertEqual(area.widget().layout().count(), 1)
            self.assertEqual(area.styleSheet(), "")
        finally:
            dialog.deleteLater()

    def test_shared_dialog_footer_retains_order_and_click_behaviour(self) -> None:
        dialog = AtlasDialog()
        dismiss = AtlasButton("Annuler", variant="secondary")
        confirm = AtlasButton("Valider", variant="primary")
        dismiss.clicked.connect(dialog.reject)
        confirm.clicked.connect(dialog.accept)
        try:
            row = dialog.add_action_row(dismiss, confirm)
            self.assertEqual(row.count(), 3)
            self.assertIs(row.itemAt(1).widget(), dismiss)
            self.assertIs(row.itemAt(2).widget(), confirm)
            confirm.click()
            self.assertEqual(dialog.result(), dialog.Accepted)
        finally:
            dialog.deleteLater()

    def test_transient_dialog_cleanup_is_deferred_until_close(self) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QDialog
        from shiboken6 import isValid

        dialog = QDialog()
        release_transient_dialog(dialog)
        self.assertTrue(isValid(dialog))
        dialog.show()
        dialog.reject()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(dialog))

    def test_shared_navigation_menu_preserves_action_order_and_dispatch(self) -> None:
        from PySide6.QtWidgets import QMenu

        visited: list[str] = []
        menu = QMenu()
        try:
            self.assertIs(
                fill_unity_navigation_menu(
                    menu, (("Premier", "one"), ("Deuxième", "two")), visited.append,
                ), menu,
            )
            self.assertEqual([a.text() for a in menu.actions()], ["Premier", "Deuxième"])
            menu.actions()[1].trigger()
            menu.actions()[0].trigger()
            self.assertEqual(visited, ["two", "one"])
            self.assertEqual(menu.styleSheet(), "")
        finally:
            menu.deleteLater()

    def test_transient_presenter_replaces_and_releases_dialogs(self) -> None:
        from types import SimpleNamespace
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QDialog
        from shiboken6 import isValid
        from app.ui.components import present_transient_dialog

        owner = SimpleNamespace(active=None)
        first, second = QDialog(), QDialog()
        present_transient_dialog(owner, "active", first)
        present_transient_dialog(owner, "active", second)
        self.assertIs(owner.active, second)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(first))
        second.reject()
        self.assertIsNone(owner.active)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(second))

    def test_parentless_transient_is_disposed_with_its_owner(self) -> None:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QDialog
        from shiboken6 import isValid
        from app.ui.components import present_transient_dialog

        owner = QWidget()
        owner.active = None
        dialog = QDialog()
        present_transient_dialog(owner, "active", dialog)
        owner.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(dialog))

    def test_shared_image_popup_keeps_popup_flags_and_indexed_zoom(self) -> None:
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QLabel
        from app.ui.components import AtlasImagePopup
        parent = QWidget()
        screen = parent.screen()
        if screen is not None:
            parent.move(screen.availableGeometry().bottomRight())
        source = QPixmap(200, 100)
        source.fill(Qt.transparent)
        dialog = AtlasImagePopup(source, parent, title="Agrandissement")
        try:
            self.assertEqual(dialog.windowType(), Qt.Popup)
            self.assertEqual(dialog.objectName(), "AtlasDialog")
            self.assertEqual(dialog.windowTitle(), "Agrandissement")
            image = dialog.findChild(QLabel, "QuestSolutionImage")
            self.assertIsNotNone(image)
            self.assertFalse(image.pixmap().isNull())
            self.assertLessEqual(abs(image.pixmap().width() - 2 * image.pixmap().height()), 1)
            if screen is not None:
                self.assertTrue(screen.availableGeometry().contains(dialog.geometry()))
        finally:
            dialog.deleteLater()
            parent.deleteLater()

    def test_stale_dialog_never_clears_its_newer_replacement(self) -> None:
        from types import SimpleNamespace
        from PySide6.QtWidgets import QDialog

        first, second = QDialog(), QDialog()
        owner = SimpleNamespace(active=second)
        try:
            self.assertFalse(clear_current_dialog_reference(owner, "active", first))
            self.assertIs(owner.active, second)
            self.assertTrue(clear_current_dialog_reference(owner, "active", second))
            self.assertIsNone(owner.active)
            self.assertFalse(clear_current_dialog_reference(owner, "active", first))
        finally:
            first.deleteLater()
            second.deleteLater()

    def test_qt_state_style_refresh_is_owned_by_shared_component(self) -> None:
        button = AtlasButton("Contrôle")
        badge = AtlasStatusBadge("Statut", "neutral")
        try:
            with patch("app.ui.components.refresh_unity_widget_style") as refresh:
                button.set_style_name("SharedStyleTest")
                badge.set_state("ready")
                self.assertEqual(refresh.call_count, 2)
                self.assertIs(refresh.call_args_list[0].args[0], button)
                self.assertIs(refresh.call_args_list[1].args[0], badge)
            refresh_unity_widget_style(button)
        finally:
            button.deleteLater()
            badge.deleteLater()

    def test_hide_completed_button_reuses_shared_style_refresh(self) -> None:
        from app.modules.encyclopedia.widgets.dashboard import HideCompletedButton

        toggle = HideCompletedButton()
        events: list[bool] = []
        toggle.stateChanged.connect(events.append)
        try:
            with patch("app.modules.encyclopedia.widgets.dashboard.refresh_unity_widget_style") as refresh:
                toggle.setChecked(True)
                self.assertEqual(toggle.text(), "✓ Terminées masquées")
                refresh.assert_called_once_with(toggle)
                toggle.setChecked(False)
                self.assertEqual(toggle.text(), "Masquer les terminées")
                self.assertEqual(refresh.call_count, 2)
                self.assertEqual(events, [True, False])
        finally:
            toggle.deleteLater()

    def test_shared_dynamic_property_avoids_repolish_for_same_state(self) -> None:
        control = QWidget()
        try:
            with patch("app.ui.components.refresh_unity_widget_style") as refresh:
                self.assertTrue(set_unity_widget_property(control, "state", "done"))
                self.assertFalse(set_unity_widget_property(control, "state", "done"))
                self.assertTrue(set_unity_widget_property(control, "state", "todo"))
                self.assertEqual(refresh.call_count, 2)
        finally:
            control.deleteLater()

    def test_shared_dynamic_property_updates_once_without_local_qss(self) -> None:
        label = QWidget()
        try:
            with patch("app.ui.components.refresh_unity_widget_style") as refresh:
                self.assertTrue(set_unity_widget_property(label, "atlasTestRole", "ready"))
                self.assertEqual(label.property("atlasTestRole"), "ready")
                self.assertFalse(set_unity_widget_property(label, "atlasTestRole", "ready"))
                self.assertTrue(set_unity_widget_property(label, "atlasTestRole", "error"))
                self.assertEqual(refresh.call_count, 2)
            self.assertEqual(label.styleSheet(), "")
        finally:
            label.deleteLater()

    def test_shared_object_name_change_repolishes_once(self) -> None:
        widget = AtlasButton("Style")
        try:
            with patch("app.ui.components.refresh_unity_widget_style") as refresh:
                self.assertTrue(set_unity_widget_object_name(widget, "AtlasCustomRole"))
                self.assertFalse(set_unity_widget_object_name(widget, "AtlasCustomRole"))
                self.assertEqual(widget.objectName(), "AtlasCustomRole")
                self.assertEqual(refresh.call_count, 1)
        finally:
            widget.deleteLater()

    def test_dialog_standard_and_compact_sizes_use_shared_tokens(self) -> None:
        from app.ui.unity_palette import UNITY_LAYOUT_SIZES_PX

        normal = AtlasDialog()
        compact = AtlasDialog(density="compact")
        try:
            for dialog, prefix in ((normal, "dialog_"), (compact, "dialog_compact_")):
                with self.subTest(density=dialog.layout_density):
                    x = UNITY_LAYOUT_SIZES_PX[f"{prefix}padding_x"]
                    y = UNITY_LAYOUT_SIZES_PX[f"{prefix}padding_y"]
                    self.assertEqual(
                        dialog.content_layout.getContentsMargins(), (x, y, x, y)
                    )
                    self.assertEqual(
                        dialog.content_layout.spacing(),
                        UNITY_LAYOUT_SIZES_PX[f"{prefix}gap"],
                    )
                    self.assertEqual(dialog.objectName(), "AtlasDialog")
                    self.assertEqual(dialog.styleSheet(), "")
            self.assertLess(
                compact.content_layout.spacing(), normal.content_layout.spacing()
            )
            with self.assertRaises(ValueError):
                AtlasDialog(density="unknown")
        finally:
            normal.deleteLater()
            compact.deleteLater()

    def test_shared_numeric_selector_fits_minimum_prefix_and_special_text(self) -> None:
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        selector = QSpinBox()
        try:
            selector.setRange(-123456, 99)
            selector.setPrefix("Niveau ")
            selector.setSuffix(" / 99")
            selector.setValue(99)
            width = fit_unity_number_spinbox(selector)
            metrics = selector.fontMetrics()
            expected_min = (
                metrics.horizontalAdvance("Niveau -123456 / 99")
                + UNITY_CONTROL_SIZES_PX["guide_quantity_chrome_width"]
            )
            self.assertGreaterEqual(width, expected_min)
            self.assertEqual(selector.width(), width)
            self.assertEqual(selector.styleSheet(), "")

            selector.setSpecialValueText("Aucune sélection disponible")
            width_with_special = fit_unity_number_spinbox(selector)
            expected_special = (
                metrics.horizontalAdvance("Aucune sélection disponible")
                + UNITY_CONTROL_SIZES_PX["guide_quantity_chrome_width"]
            )
            self.assertGreaterEqual(width_with_special, expected_special)
            self.assertGreaterEqual(width_with_special, width)
        finally:
            selector.deleteLater()

    def test_atlas_combo_owns_content_size_policy(self) -> None:
        from app.ui.components import AtlasComboBox

        combo = AtlasComboBox()
        try:
            self.assertEqual(combo.sizePolicy().horizontalPolicy(), QSizePolicy.Maximum)
            self.assertEqual(combo.sizePolicy().verticalPolicy(), QSizePolicy.Fixed)
            self.assertEqual(combo.sizeAdjustPolicy(), QComboBox.AdjustToContents)
        finally:
            combo.deleteLater()

    def test_shared_dropdown_popup_fits_available_screen(self) -> None:
        from app.ui.components import AtlasComboBox

        screen = self.app.primaryScreen()
        self.assertIsNotNone(screen)
        bounds = screen.availableGeometry()
        root = QWidget()
        root.setStyleSheet(atlas_stylesheet())
        root.move(bounds.right() - 180, bounds.bottom() - 100)
        root.resize(170, 90)
        combo = AtlasComboBox(root)
        combo.resize(110, 32)
        combo.move(45, 35)
        combo.addItems(
            ["Une option extrêmement longue pour vérifier la largeur du menu"]
            + [f"Choix {i}" for i in range(20)]
        )
        try:
            root.show()
            combo.show()
            self.app.processEvents()
            combo.showPopup()
            self.app.processEvents()
            popup = combo.view().window()
            rect = popup.geometry()
            available = combo.screen().availableGeometry()
            self.assertGreater(rect.width(), 0)
            self.assertGreater(rect.height(), 0)
            self.assertGreaterEqual(rect.left(), available.left())
            self.assertGreaterEqual(rect.top(), available.top())
            self.assertLessEqual(rect.right(), available.right())
            self.assertLessEqual(rect.bottom(), available.bottom())
            self.assertLessEqual(combo.maxVisibleItems(), 8)
        finally:
            combo.hidePopup()
            root.close()
            root.deleteLater()

    def test_number_selector_uses_polished_font_before_first_show(self) -> None:
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        selector = QSpinBox()
        try:
            selector.setRange(0, 999999)
            selector.setSuffix(" unités")
            selector.setStyleSheet("QSpinBox { font-size: 24px; }")
            width = fit_unity_number_spinbox(selector)
            expected = selector.fontMetrics().horizontalAdvance("999999 unités")
            self.assertGreaterEqual(width, expected +
                                    UNITY_CONTROL_SIZES_PX["guide_quantity_chrome_width"])
            self.assertEqual(selector.minimumWidth(), selector.maximumWidth())
        finally:
            selector.deleteLater()

    def test_guide_page_number_reserves_left_text_inset_without_widening_quantities(self) -> None:
        from app.ui.unity_palette import (
            UNITY_CONTROL_SIZES_PX, UNITY_SPACING_PX,
        )

        page = QSpinBox()
        quantity = QSpinBox()
        try:
            for widget in (page, quantity):
                widget.setRange(1, 123456)
                widget.setSuffix("/123456")
            page.setObjectName("GuideCompactPageJump")
            quantity.setObjectName("GuidePreparationQuantity")
            page_width = fit_unity_number_spinbox(page)
            quantity_width = fit_unity_number_spinbox(quantity)
            self.assertEqual(page_width - quantity_width, UNITY_SPACING_PX["sm"])
            self.assertGreaterEqual(
                page_width,
                page.fontMetrics().horizontalAdvance("123456/123456")
                + UNITY_CONTROL_SIZES_PX["guide_quantity_chrome_width"]
                + UNITY_SPACING_PX["sm"],
            )
            self.assertEqual(page.styleSheet(), "")
            self.assertEqual(quantity.styleSheet(), "")
        finally:
            page.deleteLater()
            quantity.deleteLater()

    def test_breadcrumb_insets_use_the_shared_size_index(self) -> None:
        from app.ui.unity_palette import UNITY_LAYOUT_SIZES_PX, UNITY_SPACING_PX

        values = UNITY_LAYOUT_SIZES_PX
        for compact, inset_key in (
            (True, "breadcrumb_compact_inset"),
            (False, "breadcrumb_normal_inset"),
        ):
            breadcrumb = AtlasBreadcrumb(compact=compact)
            try:
                inset = values[inset_key]
                self.assertEqual(
                    breadcrumb.row.getContentsMargins(),
                    (UNITY_SPACING_PX["md"], inset, UNITY_SPACING_PX["md"], inset),
                )
                self.assertEqual(breadcrumb.row.spacing(),
                                 values["breadcrumb_item_gap"])
            finally:
                breadcrumb.deleteLater()

    def test_shared_button_variant_roles_and_real_qt_click(self) -> None:
        root = QWidget()
        root.resize(480, 160)
        root.setStyleSheet(atlas_stylesheet())
        button = AtlasButton("Ouvrir", root, variant="secondary")
        button.resize(130, 34)
        calls: list[str] = []
        button.clicked.connect(lambda: calls.append(button.objectName()))
        try:
            root.show()
            button.show()
            self.app.processEvents()
            self.assertEqual(button.styleSheet(), "")
            self.assertEqual(button.objectName(), BUTTON_OBJECT_NAMES["secondary"])
            QTest.mouseClick(button, Qt.LeftButton)
            self.assertEqual(calls, ["SecondaryButton"])

            for variant in (
                "primary", "danger", "selected", "navigation", "navigation_active",
                "guide_breadcrumb", "guide_quest_link", "zaap_favorite",
                "guide_achievement_link",
            ):
                button.set_variant(variant)
                self.assertEqual(button.objectName(), BUTTON_OBJECT_NAMES[variant])
                self.assertEqual(button.styleSheet(), "")
            QTest.mouseClick(button, Qt.LeftButton)
            self.assertEqual(calls[-1], "GuideInlineAchievementButton")
            self.assertEqual(len(calls), 2)
        finally:
            root.close()
            root.deleteLater()

    def test_shared_toggle_updates_host_state_and_accessibility(self) -> None:
        root = QWidget()
        root.resize(300, 100)
        toggle = AtlasPanelToggle(root)
        toggle.resize(56, 36)
        events: list[bool] = []
        toggle.clicked.connect(
            lambda: (
                toggle.set_collapsed(not bool(toggle.property("collapsed"))),
                events.append(bool(toggle.property("collapsed"))),
            )
        )
        try:
            root.show()
            toggle.show()
            self.app.processEvents()
            QTest.mouseClick(toggle, Qt.LeftButton)
            self.assertEqual(events, [True])
            self.assertIn("Réafficher", toggle.accessibleName())
            QTest.mouseClick(toggle, Qt.LeftButton)
            self.assertEqual(events, [True, False])
            self.assertIn("Masquer", toggle.accessibleName())
            self.assertEqual(toggle.styleSheet(), "")
        finally:
            root.close()
            root.deleteLater()

    def test_compact_guide_controls_use_indexed_geometry(self) -> None:
        from app.ui.components import AtlasGuideDisclosure, AtlasGuideParticipantButton
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX as sizes

        participant = AtlasGuideParticipantButton()
        disclosure = AtlasGuideDisclosure()
        try:
            participant.setCheckable(True)
            participant.configure_compact()
            disclosure.configure_compact()
            self.assertTrue(participant.isCheckable())
            self.assertTrue(disclosure.isCheckable())
            self.assertEqual(participant.width(), sizes["guide_character_button"])
            self.assertEqual(participant.height(), sizes["guide_character_button"])
            self.assertEqual(participant.iconSize().width(), sizes["guide_character_icon"])
            self.assertEqual(disclosure.width(), sizes["progress_toggle_width"])
            self.assertEqual(disclosure.height(), sizes["progress_toggle_height"])
            self.assertEqual(disclosure.iconSize().width(), sizes["progress_toggle_icon"])
        finally:
            participant.deleteLater()
            disclosure.deleteLater()

    def test_guide_character_button_compatibility_with_importer(self) -> None:
        from app.ui.components import (
            AtlasGuideParticipantButton, AtlasGuideCharacterButton,
            GUIDE_CHARACTER_BUTTON_PX, GUIDE_CHARACTER_ICON_PX,
        )
        from app.ui.unity_palette import UNITY_CONTROL_SIZES_PX

        self.assertIs(AtlasGuideCharacterButton, AtlasGuideParticipantButton)
        self.assertEqual(
            GUIDE_CHARACTER_BUTTON_PX,
            UNITY_CONTROL_SIZES_PX["guide_character_button"],
        )
        self.assertEqual(
            GUIDE_CHARACTER_ICON_PX,
            UNITY_CONTROL_SIZES_PX["guide_character_icon"],
        )
        button = AtlasGuideCharacterButton()
        try:
            self.assertEqual(button.objectName(), "GuideParticipantsButton")
            self.assertEqual(button.styleSheet(), "")
        finally:
            button.deleteLater()
        qss = atlas_stylesheet()
        self.assertIn("QFrame#GuideGlobalDetailsPanel", qss)
        self.assertIn("QPushButton#GuidePreparationModeTab", qss)

    def test_status_badge_is_passive_and_uses_shared_state(self) -> None:
        root = QWidget()
        root.setStyleSheet(atlas_stylesheet())
        badge = AtlasStatusBadge("En travaux", state="blocked", parent=root)
        try:
            self.assertEqual(badge.objectName(), "StatusBadge")
            self.assertEqual(badge.property("state"), "blocked")
            self.assertEqual(badge.cursor().shape(), Qt.ArrowCursor)
            self.assertEqual(badge.styleSheet(), "")
            badge.set_state("done")
            self.assertEqual(badge.property("state"), "done")
            badge.set_state("danger")
            self.assertEqual(badge.property("state"), "danger")
            self.assertIn("Statut En travaux", badge.accessibleName())
        finally:
            root.close()
            root.deleteLater()

    def test_dialog_and_page_title_use_shared_styles_without_local_qss(self) -> None:
        dialog = AtlasDialog()
        page_title = AtlasPageTitle("Préférences")
        try:
            dialog.content_layout.addWidget(page_title)
            self.assertEqual(dialog.objectName(), "AtlasDialog")
            self.assertTrue(dialog.isModal())
            self.assertEqual(page_title.objectName(), "PageTitle")
            self.assertEqual(dialog.styleSheet(), "")
            self.assertEqual(page_title.styleSheet(), "")
        finally:
            dialog.close()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
