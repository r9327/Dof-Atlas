"""Direct Qt contracts for the shared UI components — no DOFUS runtime."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSpinBox, QWidget

from app.ui.components import (
    AtlasButton,
    AtlasBreadcrumb,
    AtlasDialog,
    AtlasPageTitle,
    AtlasPanelToggle,
    AtlasStatusBadge,
    BUTTON_OBJECT_NAMES,
    fit_unity_number_spinbox,
)
from app.ui.theme import atlas_stylesheet


class SharedUiComponentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
                "guide_breadcrumb", "guide_quest_link", "guide_achievement_link",
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
