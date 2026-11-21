from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage


class EncyclopediaLazyTabVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_page(self):
        tabs = QTabWidget()
        labels = ("QUÊTES", "SUCCÈS", "GUIDES", "DONJONS", "MONSTRES")
        for label in labels:
            tabs.addTab(QWidget(), label)
        page = SimpleNamespace(tabs=tabs, _lazy_slots={})
        page.tab_labels = lambda: [tabs.tabText(i) for i in range(tabs.count())]
        page.current_tab_label = lambda: tabs.tabText(tabs.currentIndex())
        self.addCleanup(tabs.close)
        self.addCleanup(tabs.deleteLater)
        return page

    def test_bestiary_unavailable_title_uses_shared_page_component(self):
        from app.ui.components import AtlasPageTitle

        page = self.make_page()
        page._lazy_slots["DONJONS"] = page.tabs.widget(3)
        page.replace_tab_widget = lambda label, widget: (
            EncyclopediaPage.replace_tab_widget(page, label, widget)
        )
        unavailable = EncyclopediaPage.ensure_tab_loaded(page, "DONJONS")
        title = unavailable.findChild(AtlasPageTitle, "PageTitle")
        self.assertIsNotNone(title)
        self.assertEqual(title.text(), "Donjons")
        self.assertIs(page.tabs.widget(3), unavailable)

    def test_current_bestiary_tab_replacement_preserves_all_hidden_siblings(self):
        # The first actual Bestiary view replaces the *selected* lazy slot.
        # Every hidden Encyclopedia tab must remain hidden afterwards.
        page = self.make_page()
        bar = page.tabs.tabBar()
        for index in (0, 1, 2):
            bar.setTabVisible(index, False)
        page.tabs.setCurrentIndex(3)
        page._lazy_slots["DONJONS"] = page.tabs.widget(3)
        page.replace_tab_widget = lambda label, widget: (
            EncyclopediaPage.replace_tab_widget(page, label, widget)
        )
        view = EncyclopediaPage.ensure_tab_loaded(page, "DONJONS")
        self.assertIs(page.tabs.currentWidget(), view)
        self.assertEqual(page.current_tab_label(), "DONJONS")
        self.assertEqual(
            [page.tabs.tabText(i) for i in range(page.tabs.count())
             if bar.isTabVisible(i)],
            ["DONJONS", "MONSTRES"],
        )

    def test_hidden_encyclopedia_tabs_stay_hidden_after_lazy_hydration(self):
        page = self.make_page()
        bar = page.tabs.tabBar()
        bar.setTabVisible(0, False)
        bar.setTabVisible(1, False)
        bar.setTabVisible(2, False)
        page.tabs.setCurrentIndex(3)
        self.assertEqual(page.current_tab_label(), "DONJONS")
        replacement = QWidget()
        EncyclopediaPage.replace_tab_widget(page, "SUCCÈS", replacement)
        self.assertIs(page.tabs.widget(1), replacement)
        self.assertFalse(bar.isTabVisible(0))
        self.assertFalse(bar.isTabVisible(1))
        self.assertFalse(bar.isTabVisible(2))
        self.assertTrue(bar.isTabVisible(3))
        self.assertEqual(page.current_tab_label(), "DONJONS")

    def test_replacing_current_tab_preserves_selection_and_signal_block(self):
        page = self.make_page()
        page.tabs.setCurrentIndex(0)
        page.tabs.blockSignals(True)
        replacement = QWidget()
        EncyclopediaPage.replace_tab_widget(page, "QUÊTES", replacement)
        self.assertIs(page.tabs.currentWidget(), replacement)
        self.assertTrue(page.tabs.tabBar().isTabVisible(0))
        self.assertEqual(page.current_tab_label(), "QUÊTES")
        self.assertTrue(page.tabs.signalsBlocked())


if __name__ == "__main__":
    unittest.main()
