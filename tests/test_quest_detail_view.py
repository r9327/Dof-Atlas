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
            sheet.right_layout.insertWidget(0, QLabel("Détail local"))
            self.app.processEvents()
            # An explicit range tests the scrollbar contract independently of
            # offscreen Qt platform geometry and its varying size hints.
            bar = sheet.right_scroll.verticalScrollBar()
            bar.setRange(0, 240)
            bar.setValue(120)
            expected = bar.value()
            self.assertEqual(expected, 120)
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertIs(sheet.splitter.widget(1), sheet.right_panel)
            self.assertEqual(sheet.right_panel_toggle.objectName(), "GuideRightPanelToggle")
            self.assertEqual(sheet.right_panel_toggle.text(), "›")

            sheet.right_panel_toggle.click()
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet._right_panel_collapsed)
            self.assertEqual(sheet._right_panel_scroll_position, expected)
            self.assertEqual(sheet.right_panel_toggle.text(), "‹")
            self.assertIn("Réafficher", sheet.right_panel_toggle.accessibleName())

            sheet.right_panel_toggle.click()
            self.app.processEvents()
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet._right_panel_collapsed)
            self.assertGreaterEqual(sheet.splitter.sizes()[1], 240)
            self.assertEqual(bar.value(), min(expected, bar.maximum()))
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

    def test_embedded_guide_context_uses_same_reversible_control(self) -> None:
        from PySide6.QtCore import Qt
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestViewContext

        sheet = QuestDetailView(object(), object(), object())
        sheet.context = QuestViewContext(host="guides", guide_id="guide_local")
        context = sheet.context
        try:
            self.assertTrue(bool(sheet.right_panel_toggle.focusPolicy() & Qt.TabFocus))
            sheet.set_right_panel_collapsed(True)
            self.assertTrue(sheet.right_panel.isHidden())
            self.assertTrue(sheet.right_panel_toggle.property("collapsed"))
            sheet.set_right_panel_collapsed(True)  # Repeated signal is inert.
            sheet.set_right_panel_collapsed(False)
            self.assertFalse(sheet.right_panel.isHidden())
            self.assertFalse(sheet.right_panel_toggle.property("collapsed"))
            self.assertIs(sheet.context, context)
            self.assertEqual(context.host, "guides")
        finally:
            sheet.deleteLater()
            self.app.processEvents()

    def test_right_toggle_uses_shared_unity_theme(self) -> None:
        css = atlas_stylesheet()
        self.assertIn("QToolButton#GuideRightPanelToggle", css)
        self.assertIn("border: 1px solid " + THEME_TOKENS["BORDER"], css)
        self.assertIn('QToolButton#GuideRightPanelToggle[collapsed="true"]', css)


if __name__ == "__main__":
    unittest.main()
