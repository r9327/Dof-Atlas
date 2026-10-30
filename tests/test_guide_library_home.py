"""Guide library and featured-card contracts for the compact 2026-10-24 UI."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QListView, QLineEdit, QListWidget

from app.modules.encyclopedia.models.guide import Guide
from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
from app.modules.encyclopedia.views.encyclopedia_page import _has_embedded_search
from app.modules.encyclopedia.views.guide_library_sources import (
    ATLAS_EQUIVALENTS, CATEGORIES, classify_title, displayable_listings,
    load_ganymede_listings,
)
from app.modules.encyclopedia.widgets.guide_card import GUIDE_ID_ROLE
from app.modules.encyclopedia.widgets.guide_card import GuideCardDelegate


def _guide(name, category):
    return Guide(id=name, category=category, title=name, search_text=name.casefold())


class _Provider:
    def __init__(self):
        self.guides = [
            _guide("guide_complet", "aventure"),
            _guide("dofus_sylvestre", "aventure"),
            _guide("alignement_bonta", "alignements"),
            _guide("alignement_brakmar", "alignements"),
            _guide("dofus_cawotte", "dofus"),
            _guide("dofus_ivoire", "dofus"),
        ]

    def load_all(self):
        return list(self.guides)

    def search(self, query):
        q = str(query or "").casefold().strip()
        return [g for g in self.guides if not q or q in g.id.casefold()]


class GuideLibraryHomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_95_unique_canonical_ids_are_classified_without_playable_routes(self):
        records = load_ganymede_listings()
        ids = [entry.source_id for entry in records]
        self.assertEqual(len(ids), 95)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue({entry.category for entry in records}.issubset(
            {key for key, _title in CATEGORIES}
        ))
        self.assertTrue(all(not entry.playable for entry in records))
        self.assertEqual(classify_title("Srambad 1"), "dimensions")
        self.assertEqual(classify_title("Kwismas"), "events")

    def test_existing_dofus_guides_are_not_duplicated_by_source_metadata(self):
        records = load_ganymede_listings()
        merged = displayable_listings(records, {"dofus_cawotte"}, "dofus")
        self.assertNotIn(2205, {entry.source_id for entry in merged})
        self.assertIn(2203, {entry.source_id for entry in merged})
        self.assertEqual(ATLAS_EQUIVALENTS[2205], "dofus_cawotte")
        aliases = {"dofus_nebuleux", "dofus_dom_de_pin", "dofus_sylvestre"}
        selected = displayable_listings(records, aliases, "dofus")
        visible_ids = {entry.source_id for entry in selected}
        self.assertTrue({2247, 2285, 2290}.isdisjoint(visible_ids))

    def test_unity_catalog_inner_roots_and_featured_card_alpha(self):
        from unittest.mock import patch

        with patch.dict(os.environ, {"ATLAS_THEME": "dofus_unity"}):
            with tempfile.TemporaryDirectory() as directory:
                view = GuideCatalogView(
                    lambda _message: None, provider=_Provider(),
                    quest_progress_path=Path(directory) / "progress.json",
                    defer_runtime=True,
                )
                try:
                    self.assertEqual(
                        view.home_scroll.widget().objectName(), "GuidesHomeContent"
                    )
                    self.assertEqual(view.library_right.objectName(), "GuideLibraryResults")
                    for card in view.featured_cards.values():
                        self.assertIn("rgba(27, 39, 70, 0.88)", card.styleSheet())
                    self.assertIsNone(
                        view.findChild(QListWidget, "GuideLibraryUnavailableList")
                    )
                finally:
                    view.deleteLater()
                    self.app.processEvents()

    def test_rich_guides_signals_and_external_catalog_navigation(self):
        from app.modules.encyclopedia.views.guides_view import GuidesView

        # The lazy Encyclopedia wires these Qt signals on the rich GuidesView.
        # Regression: both were missing, raising AttributeError on first open.
        self.assertTrue(hasattr(GuidesView, "catalogRequested"))
        self.assertTrue(hasattr(GuidesView, "achievementRuntimeRequested"))

        requested = []
        fake = SimpleNamespace(
            _catalog_external_owner=True,
            catalogRequested=SimpleNamespace(emit=lambda: requested.append("catalog")),
        )
        GuidesView.show_home(fake)
        self.assertEqual(requested, ["catalog"])

        # Outside Encyclopedia the historical embedded home still works.
        page = object()
        switched = []
        standalone = SimpleNamespace(
            _catalog_external_owner=False,
            catalogRequested=SimpleNamespace(emit=lambda: requested.append("wrong")),
            current_guide_id="guide_complet",
            current_quest_id=42,
            state="GUIDE_OVERVIEW",
            CATALOG="CATALOG",
            refresh_home=lambda: switched.append("refresh"),
            stack=SimpleNamespace(setCurrentWidget=switched.append),
            home_page=page,
            status_callback=lambda text: switched.append(text),
        )
        GuidesView.show_home(standalone)
        self.assertEqual(standalone.state, "CATALOG")
        self.assertIsNone(standalone.current_guide_id)
        self.assertIsNone(standalone.current_quest_id)
        self.assertIn(page, switched)
        self.assertEqual(requested, ["catalog"])

    def test_two_featured_cards_and_stable_alignment_tree(self):
        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "app.modules.encyclopedia.views.guide_catalog_view.catalog_route_map_count_hint",
                return_value=0,
            ):
                view = GuideCatalogView(
                    lambda _message: None,
                    provider=provider,
                    quest_progress_path=Path(directory) / "progress.json",
                    defer_runtime=True,
                )
                view._progress_snapshot = lambda: {}
                view.hydrate_runtime()
                view.resize(1180, 780)
                view.show()
                self.app.processEvents()
                try:
                    self.assertEqual(set(view.featured_cards), {
                        "guide_complet", "dofus_sylvestre",
                    })
                    # The agreed home keeps featured routes and Alignements
                    # together on the left, with the Dofus grid on the right.
                    self.assertIs(
                        view.home_columns.layout().itemAt(0).widget(), view.library_left
                    )
                    self.assertIs(
                        view.home_columns.layout().itemAt(1).widget(), view.library_right
                    )
                    self.assertIs(view.optimized_pair.parentWidget(), view.library_left)
                    self.assertIs(view.library_categories.parentWidget(), view.library_left)
                    self.assertEqual(view.library_category, "dofus")
                    # The narrower LEFT column stacks the two equal-size cards.
                    self.assertEqual(view.optimized_pair.pair_layout.direction(),
                                     QBoxLayout.TopToBottom)
                    self.assertTrue(view.featured_cards["guide_complet"].isVisibleTo(view))
                    self.assertIsNone(view.findChild(QLineEdit, "GuideLibrarySearch"))
                    alignments = view._category_nodes["alignements"]
                    playable = [
                        alignments.child(i)
                        for i in range(alignments.childCount())
                        if alignments.child(i).data(0, Qt.UserRole + 1)
                    ]
                    self.assertEqual(len(playable), 2)
                    self.assertGreaterEqual(alignments.childCount(), len(playable))
                    self.assertEqual(view.home_dofus_list.viewMode(), QListView.IconMode)
                    requested = []
                    view.guideRequested.connect(requested.append)
                    view.featured_cards["guide_complet"].open_button.click()
                    self.assertEqual(requested, ["guide_complet"])
                    alignments = view._category_nodes["alignements"]
                    requested.clear()
                    view.library_categories.setCurrentItem(alignments.child(0))
                    self.assertEqual(requested, ["alignement_bonta"])
                    view.library_categories.itemActivated.emit(alignments.child(0), 0)
                    self.assertEqual(requested, ["alignement_bonta"])
                    dimensions = view._category_nodes["dimensions"]
                    view.library_categories.setCurrentItem(dimensions)
                    self.assertEqual(view.library_category, "dimensions")
                    self.assertGreater(dimensions.childCount(), 0)
                    self.assertTrue(all(
                        not (dimensions.child(i).flags() & Qt.ItemIsEnabled)
                        for i in range(dimensions.childCount())
                    ))
                    view._toggle_library_category(dimensions, 0)
                    self.assertTrue(dimensions.isExpanded())
                    requested.clear()
                    # A catalogued-only reference must not launch a real guide.
                    view._on_category_changed(dimensions.child(0))
                    self.assertEqual(requested, [])
                    view.refresh_home()
                    self.assertTrue(dimensions.isExpanded())
                    self.assertEqual(view.library_results_title.text(), "DOFUS")
                    self.assertTrue(view.home_dofus_list.isVisible())
                    self.assertIsNone(
                        view.findChild(QListWidget, "GuideLibraryUnavailableList")
                    )
                    alignments.setExpanded(False)
                    view.set_search_text("no-matching-library-entry")
                    self.assertTrue(view.featured_cards["guide_complet"].isVisibleTo(view))
                    self.assertFalse(alignments.isExpanded())
                    self.assertFalse(view.home_dofus_list.isVisible())
                    view.resize(610, 780)
                    self.app.processEvents()
                    self.assertEqual(view.home_columns.layout().direction(),
                                     QBoxLayout.TopToBottom)
                finally:
                    view.close()
                    view.deleteLater()
                    self.app.processEvents()

    def test_entire_featured_card_is_clickable_and_keyboard_accessible(self):
        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            view = GuideCatalogView(
                lambda _message: None,
                provider=provider,
                quest_progress_path=Path(directory) / "progress.json",
                defer_runtime=True,
            )
            view._progress_snapshot = lambda: {}
            view.hydrate_runtime()
            view.resize(1200, 800)
            view.show()
            self.app.processEvents()
            try:
                events = []
                view.guideRequested.connect(events.append)
                card = view.featured_cards["guide_complet"]
                QTest.mouseClick(card, Qt.LeftButton)
                QTest.keyClick(card, Qt.Key_Return)
                self.assertEqual(events, ["guide_complet", "guide_complet"])
                self.assertTrue(card.accessibleName())
                model = view.home_dofus_model
                row = model.row_for_guide("dofus_cawotte")
                self.assertGreaterEqual(row, 0)
                self.assertNotIn("0 %", model.index(row, 0).data(Qt.DisplayRole))
                self.assertIn("Progression inconnue", model.index(row, 0).data(Qt.DisplayRole))
            finally:
                view.close()
                view.deleteLater()
                self.app.processEvents()

    def test_global_encyclopedia_search_is_absent(self):
        # The common header has no QLineEdit; Quêtes/Sommaire search is separate.
        import inspect
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        self.assertNotIn("EncyclopediaSearch", inspect.getsource(EncyclopediaPage))
        self.assertFalse(_has_embedded_search(type("GuideCatalogView", (), {})()))

    def test_progress_bar_geometry_never_escapes_later_grid_columns(self):
        second_column = QRect(280, 96, 280, 96)
        bar = GuideCardDelegate.progress_rect(
            second_column,
            second_column.left() + 71,
            second_column.right() - 10,
        )
        self.assertGreaterEqual(bar.left(), second_column.left())
        self.assertLessEqual(bar.right(), second_column.right())
        self.assertEqual(bar.height(), 4)

    def test_rich_guide_return_restores_canonical_lightweight_library(self):
        """The detail view must never leave its legacy home after a return."""
        from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage
        from app.modules.encyclopedia.views.deferred_achievement_guides_view import (
            DeferredAchievementGuidesView,
        )
        import inspect

        # Genuine production signal: Guide card's back action -> GuidesView
        # show_home -> Encyclopedia owner -> lightweight approved catalogue.
        self.assertIn(
            "self.catalogRequested.emit()",
            inspect.getsource(DeferredAchievementGuidesView.show_home),
        )
        selected = []
        catalog = SimpleNamespace(
            _runtime_ready=False, hydrate_runtime=lambda **kw: selected.append(("hydrate", kw)),
            set_search_text=lambda query: selected.append(("search", query)),
        )
        owner = SimpleNamespace(
            guides_view=SimpleNamespace(search_text="cawotte"),
            _guide_runtime_ready=True,
            _quest_graph=None,
            _guide_progress_by_guide={},
            _guide_progress_character_key="",
            sync_search_visibility=lambda: selected.append(("sync",)),
            status_callback=lambda text: selected.append(("status", text)),
        )

        def ensure_catalog():
            self.assertIsNone(owner.guides_view)
            owner.guides_view = catalog
            return catalog

        owner.ensure_guides_view = ensure_catalog
        EncyclopediaPage._restore_guides_catalog_home(owner)
        self.assertIs(owner.guides_view, catalog)
        self.assertEqual(selected[0][0], "hydrate")
        self.assertIn(("search", "cawotte"), selected)
        self.assertIn(("sync",), selected)



if __name__ == "__main__":
    unittest.main()
