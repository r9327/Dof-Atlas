"""Real Qt click/navigation regressions for the Guide catalogue.

Only guides with playable Atlas records may appear. Source-index references
remain in their owner data module, not as dead-end UI entries.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidget, QTabWidget, QWidget

from app.modules.encyclopedia.constants import GUIDES_TAB
from app.modules.encyclopedia.models.guide import Guide
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
from app.ui.unity_skin import unity_skin_stylesheet
from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView


class _Provider:
    def __init__(self):
        self.guides = [
            Guide(id="guide_complet", category="aventure", title="Ultime", search_text="ultime"),
            Guide(id="dofus_sylvestre", category="aventure", title="Sylvestre", search_text="sylvestre"),
            Guide(id="dofus_cawotte", category="dofus", title="Cawotte", search_text="cawotte"),
            Guide(id="region_test", category="regions", title="Guide région jouable", search_text="région"),
        ]

    def load_all(self):
        return list(self.guides)

    def search(self, query):
        text = str(query or "").strip().casefold()
        return [guide for guide in self.guides if not text or text in guide.search_text]


class GuideCatalogInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_view(self):
        with tempfile.TemporaryDirectory() as directory:
            # The UI must never load metadata-only Ganymède references.
            with (
                patch(
                    "app.modules.encyclopedia.views.guide_library_sources.load_ganymede_listings",
                    side_effect=AssertionError("Reference catalogue must stay out of Guide UI"),
                ),
                patch(
                    "app.modules.encyclopedia.views.guide_catalog_view.catalog_route_map_count_hint",
                    return_value=0,
                ),
            ):
                view = GuideCatalogView(
                    lambda _text: None, provider=_Provider(),
                    quest_progress_path=Path(directory) / "progress.json",
                    defer_runtime=True,
                )
                view._progress_snapshot = lambda: {}
                view.hydrate_runtime()
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        view.resize(1100, 740)
        view.show()
        self.app.processEvents()
        return view

    def _click_category(self, view, category):
        tree = view.library_categories
        item = view._category_nodes[category]
        tree.scrollToItem(item)
        self.app.processEvents()
        rect = tree.visualItemRect(item)
        self.assertTrue(rect.isValid())
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.center())
        self.app.processEvents()
        return item

    def test_no_reference_or_preference_ui_even_after_category_changes(self):
        view = self.make_view()
        self.assertFalse(view.findChildren(QListWidget, "GuideLibraryUnavailableList"))
        self.assertFalse(hasattr(view, "unavailable_title"))
        self.assertFalse(hasattr(view, "unavailable_list"))
        all_titles = []
        tree = view.library_categories
        for i in range(tree.topLevelItemCount()):
            parent = tree.topLevelItem(i)
            all_titles.extend(parent.child(j).text(0) for j in range(parent.childCount()))
        self.assertNotIn("Zone Nord", all_titles)
        self.assertNotIn("Dimension A", all_titles)
        self.assertIn("Guide région jouable", all_titles)

        requested = []
        view.guideRequested.connect(requested.append)
        self._click_category(view, "dimensions")
        self.assertEqual(view.library_results_title.text(), "DIMENSIONS DIVINES")
        self.assertFalse(view.home_dofus_list.isVisible())
        self.assertTrue(view.home_empty.isVisibleTo(view))
        self.assertEqual(requested, [])
        self._click_category(view, "regions")
        self.assertEqual(view.library_results_title.text(), "ZONES ET RÉGIONS")
        self.assertTrue(view.home_dofus_list.isVisibleTo(view))
        self.assertEqual(view.home_dofus_model.rowCount(), 1)
        self.assertEqual(requested, [])

    def test_real_mouse_click_on_guide_card_emits_correct_route(self):
        view = self.make_view()
        requested = []
        view.guideRequested.connect(requested.append)
        index = view.home_dofus_model.index(0, 0)
        self.assertTrue(index.isValid())
        view.home_dofus_list.scrollTo(index)
        self.app.processEvents()
        rect = view.home_dofus_list.visualRect(index)
        self.assertTrue(rect.isValid())
        QTest.mouseClick(view.home_dofus_list.viewport(), Qt.LeftButton, pos=rect.center())
        self.assertEqual(requested, ["dofus_cawotte"])
        self.assertEqual(view.current_guide_id, "dofus_cawotte")

    def test_real_mouse_click_on_tree_child_opens_its_guide(self):
        view = self.make_view()
        requested = []
        view.guideRequested.connect(requested.append)
        parent = view._category_nodes["regions"]
        parent.setExpanded(True)
        self.app.processEvents()
        self.assertEqual(requested, [])
        child = parent.child(0)
        self.assertEqual(child.data(0, Qt.UserRole + 1), "region_test")
        tree = view.library_categories
        tree.scrollToItem(child)
        self.app.processEvents()
        rect = tree.visualItemRect(child)
        self.assertTrue(rect.isValid())
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, pos=rect.center())
        self.assertEqual(requested, ["region_test"])
        self.assertEqual(view.current_guide_id, "region_test")
        # Qt may activate the same item after a click or double-click.
        # That must not dispatch the guide a second time.
        tree.itemActivated.emit(child, 0)
        self.assertEqual(requested, ["region_test"])

    def test_featured_mouse_and_keyboard_both_reach_guide_signal(self):
        view = self.make_view()
        requested = []
        view.guideRequested.connect(requested.append)
        card = view.featured_cards["guide_complet"]
        self.assertTrue(card.open_button.isEnabled())
        QTest.mouseClick(card, Qt.LeftButton, pos=card.rect().center())
        self.assertEqual(requested, ["guide_complet"])
        card.setFocus()
        QTest.keyClick(card, Qt.Key_Return)
        self.assertEqual(requested, ["guide_complet", "guide_complet"])

    def test_featured_card_uses_shared_unity_colors_without_losing_click(self):
        view = self.make_view()
        card = view.featured_cards["guide_complet"]
        self.assertEqual(card.styleSheet(), "")
        self.assertEqual(card.title.styleSheet(), "")
        self.assertEqual(card.subtitle.styleSheet(), "")
        self.assertEqual(card.progress.styleSheet(), "")
        self.assertEqual(card.title.objectName(), "GuideFeaturedTitle")
        self.assertEqual(card.progress.objectName(), "GuideFeaturedProgress")
        self.assertEqual(card.focusPolicy(), Qt.StrongFocus)

        stylesheet = unity_skin_stylesheet({
            "PANEL_ACTIVE": "#123456",
            "PANEL": "#234567",
            "GREEN_BORDER": "#345678",
            "TEXT": "#456789",
            "TEXT_MUTED": "#56789A",
            "GREEN": "#6789AB",
        })
        card_style = stylesheet.rsplit("QFrame#GuideFeaturedCard {", 1)[1].split("}", 1)[0]
        title_style = stylesheet.split("QFrame#GuideFeaturedCard QLabel#GuideFeaturedTitle {", 1)[1].split("}", 1)[0]
        progress_style = stylesheet.split("QFrame#GuideFeaturedCard QProgressBar#GuideFeaturedProgress::chunk {", 1)[1].split("}", 1)[0]
        self.assertIn("stop:0 #123456, stop:1 #234567", card_style)
        self.assertIn("border: 1px solid #345678", card_style)
        self.assertIn("color: #456789", title_style)
        self.assertIn("background: #6789AB", progress_style)

        opened = []
        view.guideRequested.connect(opened.append)
        QTest.mouseClick(card, Qt.LeftButton, pos=card.rect().center())
        self.assertEqual(opened, ["guide_complet"])

    def test_click_flows_from_catalog_signal_to_encyclopedia_routing(self):
        from types import SimpleNamespace

        view = self.make_view()
        tabs = QTabWidget()
        tabs.addTab(QWidget(), GUIDES_TAB)
        self.addCleanup(tabs.deleteLater)
        self.addCleanup(tabs.close)
        opened = []
        status = []
        detail = SimpleNamespace(select_guide=lambda guide_id: opened.append(guide_id))
        owner = SimpleNamespace(
            tabs=tabs,
            _pending_guide_id="",
            _pending_lazy_tab="",
            _pending_achievement_context_id=None,
            _guide_runtime_ready=True,
            _achievement_ready=False,
            _last_ready_tab_index=-1,
            tab_labels=lambda: [tabs.tabText(i) for i in range(tabs.count())],
            ensure_full_guides_view=lambda: detail,
            ensure_guides_view=lambda: view,
            sync_tab_accent=lambda _label: None,
            sync_search_visibility=lambda: None,
            sync_character_to_children=lambda: None,
            status_callback=status.append,
        )
        owner.open_pending_lazy_tab = lambda: EncyclopediaPage.open_pending_lazy_tab(owner)
        view.guideRequested.connect(
            lambda guide_id: EncyclopediaPage.navigate_to_guide(owner, guide_id)
        )

        # A physical Qt click must traverse the real Encyclopedia routing
        # functions (not stop at a mocked signal).
        index = view.home_dofus_model.index(0, 0)
        view.home_dofus_list.scrollTo(index)
        self.app.processEvents()
        rect = view.home_dofus_list.visualRect(index)
        QTest.mouseClick(view.home_dofus_list.viewport(), Qt.LeftButton, pos=rect.center())
        self.assertEqual(opened, ["dofus_cawotte"])
        self.assertEqual(owner._pending_guide_id, "")
        self.assertEqual(owner._pending_lazy_tab, "")
        self.assertEqual(owner._last_ready_tab_index, 0)
        self.assertEqual(status, [f"Encyclopédie : {GUIDES_TAB}"])

    def test_missing_guide_never_dispatches_or_opens(self):
        view = self.make_view()
        requested = []
        view.guideRequested.connect(requested.append)
        self.assertFalse(view.select_guide("ganymede-only-900001"))
        self.assertFalse(view.select_guide(""))
        self.assertEqual(requested, [])

    def test_catalog_filter_and_refresh_show_only_real_routes(self):
        view = self.make_view()
        view.library_categories.setCurrentItem(view._category_nodes["regions"])
        view.refresh_home()
        self.assertEqual(view.home_dofus_model.rowCount(), 1)
        view.set_search_text("introuvable")
        self.assertEqual(view.home_dofus_model.rowCount(), 0)
        self.assertTrue(view.home_empty.isVisible())
        view.set_search_text("")
        self.assertEqual(view.home_dofus_model.rowCount(), 1)
        view.library_categories.setCurrentItem(view._category_nodes["dofus"])
        self.app.processEvents()
        self.assertTrue(view.home_dofus_list.isVisibleTo(view))
        self.assertGreater(view.home_dofus_list.height(), 280)


if __name__ == "__main__":
    unittest.main()
