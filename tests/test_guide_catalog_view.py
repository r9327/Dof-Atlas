"""Right-column UI must distinguish local Guide routes from indexed references."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.models.guide import Guide
from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing


class _Provider:
    def __init__(self):
        self.guides = [
            Guide(id="guide_complet", category="aventure", title="Ultime", search_text="ultime"),
            Guide(id="dofus_sylvestre", category="aventure", title="Sylvestre", search_text="sylvestre"),
            Guide(id="dofus_cawotte", category="dofus", title="Cawotte", search_text="cawotte"),
        ]

    def load_all(self):
        return list(self.guides)

    def search(self, query):
        text = str(query or "").strip().casefold()
        return [row for row in self.guides if not text or text in row.search_text]


class GuideCatalogRightColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_view(self):
        references = (
            GanymedeListing(900001, "Zone Nord", "regions", None, 8, "local://fixture"),
            GanymedeListing(900002, "Zone Sud", "regions", None, 5, "local://fixture"),
            GanymedeListing(900003, "Dimension A", "dimensions", None, 4, "local://fixture"),
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "app.modules.encyclopedia.views.guide_catalog_view.load_ganymede_listings",
                    return_value=references,
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

    def test_category_displays_local_references_without_fake_progress_or_actions(self):
        view = self.make_view()
        requested = []
        view.guideRequested.connect(requested.append)
        view.library_categories.setCurrentItem(view._category_nodes["regions"])
        self.app.processEvents()
        self.assertEqual(view.library_results_title.text(), "ZONES ET RÉGIONS")
        self.assertFalse(view.home_dofus_list.isVisible())
        self.assertTrue(view.unavailable_list.isVisibleTo(view))
        self.assertFalse(view.home_empty.isVisible())
        self.assertEqual(
            [view.unavailable_list.item(i).text() for i in range(view.unavailable_list.count())],
            ["Zone Nord", "Zone Sud"],
        )
        self.assertTrue(all(
            view.unavailable_list.item(i).flags() == Qt.NoItemFlags
            for i in range(view.unavailable_list.count())
        ))
        view.unavailable_list.itemActivated.emit(view.unavailable_list.item(0))
        self.assertEqual(requested, [])
        self.assertEqual(view.home_dofus_model.rowCount(), 0)

    def test_expanding_arrow_selects_category_without_launching_a_guide(self):
        view = self.make_view()
        calls = []
        view.guideRequested.connect(calls.append)
        self.assertEqual(view.library_category, "dofus")
        regions = view._category_nodes["regions"]
        self.assertGreater(regions.childCount(), 0)

        # The expander arrow does not necessarily change currentItem in Qt.
        regions.setExpanded(True)
        self.app.processEvents()
        self.assertIs(view.library_categories.currentItem(), regions)
        self.assertEqual(view.library_category, "regions")
        self.assertEqual(view.library_results_title.text(), "ZONES ET RÉGIONS")
        self.assertEqual(view.unavailable_list.count(), 2)
        self.assertTrue(view.unavailable_list.isVisibleTo(view))
        self.assertFalse(view.home_dofus_list.isVisible())
        self.assertEqual(calls, [])

        # Re-expanding the selected category must remain idempotent.
        regions.setExpanded(False)
        regions.setExpanded(True)
        self.app.processEvents()
        self.assertEqual(view.library_category, "regions")
        self.assertEqual(calls, [])

    def test_filter_and_refresh_reuse_rows_without_changing_real_cards(self):
        view = self.make_view()
        view.library_categories.setCurrentItem(view._category_nodes["regions"])
        item = view.unavailable_list.item(0)
        view.refresh_home()
        self.assertIs(view.unavailable_list.item(0), item)
        view.set_search_text("Sud")
        self.assertEqual(view.unavailable_list.count(), 1)
        self.assertEqual(view.unavailable_list.item(0).text(), "Zone Sud")
        view.set_search_text("introuvable")
        self.assertFalse(view.unavailable_list.isVisible())
        self.assertTrue(view.home_empty.isVisible())
        view.set_search_text("")
        view.library_categories.setCurrentItem(view._category_nodes["dofus"])
        self.assertFalse(view.unavailable_list.isVisible())
        self.assertTrue(view.home_dofus_list.isVisibleTo(view))


if __name__ == "__main__":
    unittest.main()
