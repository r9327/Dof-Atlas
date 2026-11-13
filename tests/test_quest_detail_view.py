"""Qt regression for the shared Quêtes / Guide quest information rail."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView
from app.ui.theme import THEME_TOKENS, atlas_stylesheet


class QuestDetailViewColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_right_column_round_trip_preserves_quest_and_scroll(self) -> None:
        # clear() is sufficient for layout tests; no game catalogue is fetched.
        sheet = QuestDetailView(object(), object(), object())
        sheet.resize(1050, 700)
        sheet.show()
        try:
            sheet.right_layout.insertWidget(0, QLabel(chr(10).join(["Détail local"] * 100)))
            self.app.processEvents()
            bar = sheet.right_scroll.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(min(120, bar.maximum()))
            expected = bar.value()
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertIs(sheet.splitter.widget(1), sheet.right_panel)
            self.assertEqual(sheet.right_panel_toggle.objectName(), "GuideRightPanelToggle")
            self.assertEqual(sheet.right_panel_toggle.text(), "›")

            sheet.right_panel_toggle.click()
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet._right_panel_collapsed)
            self.assertEqual(sheet.right_panel_toggle.text(), "‹")
            self.assertIn("Réafficher", sheet.right_panel_toggle.accessibleName())

            sheet.right_panel_toggle.click()
            self.app.processEvents()
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet._right_panel_collapsed)
            self.assertGreaterEqual(sheet.splitter.sizes()[1], 240)
            self.assertEqual(bar.value(), expected)
            self.assertEqual(sheet.right_panel_toggle.text(), "›")
            self.assertIn("Masquer", sheet.right_panel_toggle.toolTip())

            sheet.right_panel_toggle.click()
            sheet.clear("Pas de quête sélectionnée")
            self.assertTrue(sheet.right_panel.isHidden())
            sheet.right_panel_toggle.click()
            self.assertFalse(sheet.right_panel.isHidden())
        finally:
            sheet.close()
            sheet.deleteLater()
            self.app.processEvents()

    def test_right_toggle_uses_shared_unity_theme(self) -> None:
        css = atlas_stylesheet()
        self.assertIn("QToolButton#GuideRightPanelToggle", css)
        self.assertIn("border: 1px solid " + THEME_TOKENS["BORDER"], css)
        self.assertIn('QToolButton#GuideRightPanelToggle[collapsed="true"]', css)


if __name__ == "__main__":
    unittest.main()
