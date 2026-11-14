"""Direct Qt contracts for the shared UI components — no DOFUS runtime."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.components import (
    AtlasButton,
    AtlasDialog,
    AtlasPageTitle,
    AtlasPanelToggle,
    AtlasStatusBadge,
    BUTTON_OBJECT_NAMES,
)
from app.ui.theme import atlas_stylesheet


class SharedUiComponentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
