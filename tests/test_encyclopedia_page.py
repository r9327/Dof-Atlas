from __future__ import annotations

import os
import unittest
from unittest.mock import patch
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

    def test_released_encyclopedia_drops_queued_results_and_never_joins_worker(self):
        from queue import Queue
        from threading import Event
        from unittest.mock import Mock
        page = SimpleNamespace(
            _runtime_released=Event(), _quest_load_timer=Mock(),
            _quest_load_queue=Queue(), quest_page=Mock(),
            _pending_lazy_tab="GUIDES", _pending_guide_id="test",
            _pending_achievement_id=1, _pending_achievement_context_id=2,
            status_callback=Mock(),
        )
        page._quest_load_queue.put(RuntimeError("old result"))
        with patch("app.modules.encyclopedia.views.encyclopedia_page._join_runtime_threads") as join:
            EncyclopediaPage.release_runtime(page)
            self.assertTrue(page._runtime_released.is_set())
            page._quest_load_timer.stop.assert_called_once()
            page.quest_page.release_runtime.assert_called_once()
            self.assertTrue(page._quest_load_queue.empty())
            self.assertTrue(page._quest_load_abandoned)
            EncyclopediaPage._collect_quest_runtime(page)
            EncyclopediaPage.collect_related_preload(page, RuntimeError("stale"))
            EncyclopediaPage._collect_achievement_runtime(page, RuntimeError("stale"))
            EncyclopediaPage.request_quest_runtime(page)
            EncyclopediaPage.request_related_preload(page)
            EncyclopediaPage._start_achievement_stage(page, open_success=True)
            EncyclopediaPage.release_runtime(page)
            join.assert_not_called()
            page.status_callback.assert_not_called()
            page.quest_page.release_runtime.assert_called_once()

    def test_connection_change_refreshes_guide_without_reselecting_character(self):
        from unittest.mock import Mock

        guide = Mock(current_character_key="character:1")
        page = SimpleNamespace(
            _syncing_character=False,
            guides_view=guide,
            current_character_key="character:1",
            quest_page=None,
            get_achievements_view=lambda: None,
        )
        EncyclopediaPage.sync_character_to_children(page)
        guide.set_character_key.assert_not_called()
        guide.refresh_connection_state.assert_called_once_with()
        self.assertFalse(page._syncing_character)

    def test_guide_tab_accent_uses_the_shared_style_refresh(self):
        page = self.make_page()
        tab_bar = page.tabs.tabBar()
        with patch("app.ui.components.refresh_unity_widget_style") as refresh:
            EncyclopediaPage.sync_tab_accent(page, "GUIDES")
            self.assertTrue(tab_bar.property("guideActive"))
            refresh.assert_called_once_with(tab_bar)
            EncyclopediaPage.sync_tab_accent(page, "GUIDES")
            refresh.assert_called_once_with(tab_bar)

    def test_encyclopedia_warmup_uses_indeterminate_progress_and_indexed_geometry(self):
        from PySide6.QtWidgets import QProgressBar
        from app.modules.encyclopedia.views.encyclopedia_bootstrap_views import EncyclopediaWarmupView
        from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX
        view = EncyclopediaWarmupView("Guides")
        try:
            progress = view.findChild(QProgressBar)
            self.assertEqual((progress.minimum(), progress.maximum()), (0, 0))
            self.assertFalse(progress.isTextVisible())
            self.assertEqual(progress.maximumWidth(),
                             UNITY_MODULE_GEOMETRY_PX["encyclopedia_warmup"]["progress_max_width"])
        finally:
            view.deleteLater()

    def test_navigation_group_uses_canonical_tab_ids_and_preserves_order(self):
        from app.modules.encyclopedia.constants import (
            ENCYCLOPEDIA_TABS, GUIDE_TABS, BESTIARY_TABS,
            encyclopedia_tab_group, encyclopedia_visible_tabs,
        )
        for label in GUIDE_TABS:
            self.assertEqual(encyclopedia_tab_group(label), "Encyclopédie")
            self.assertEqual(encyclopedia_visible_tabs(label, ENCYCLOPEDIA_TABS), GUIDE_TABS)
        for label in BESTIARY_TABS:
            self.assertEqual(encyclopedia_tab_group(label), "Bestiaire")
            self.assertEqual(encyclopedia_visible_tabs(label, ENCYCLOPEDIA_TABS), BESTIARY_TABS)
        self.assertEqual(encyclopedia_tab_group("unknown"), "")
        self.assertEqual(encyclopedia_visible_tabs("unknown", ENCYCLOPEDIA_TABS), ENCYCLOPEDIA_TABS)

    def test_bestiary_unavailable_title_uses_shared_page_component(self):
        from app.ui.components import AtlasPageTitle, AtlasUnavailablePage

        page = self.make_page()
        page._lazy_slots["DONJONS"] = page.tabs.widget(3)
        page.replace_tab_widget = lambda label, widget: (
            EncyclopediaPage.replace_tab_widget(page, label, widget)
        )
        unavailable = EncyclopediaPage.ensure_tab_loaded(page, "DONJONS")
        title = unavailable.findChild(AtlasPageTitle, "PageTitle")
        self.assertIsNotNone(title)
        self.assertEqual(title.text(), "Donjons")
        self.assertIsInstance(unavailable, AtlasUnavailablePage)
        self.assertEqual(unavailable.badge.text(), "En travaux")
        self.assertEqual(unavailable.message_label.objectName(), "EncyclopediaUnavailableMessage")
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
