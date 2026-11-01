from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QBoxLayout, QListView

from app.modules.encyclopedia.models.guide import Guide
from app.modules.encyclopedia.views.guide_catalog_view import GuideCatalogView
from app.modules.encyclopedia.widgets.guide_card import (
    GUIDE_GROUP_ROLE,
    GUIDE_ID_ROLE,
    GuideListModel,
)


def _guide(guide_id: str, category: str, title: str) -> Guide:
    return Guide(id=guide_id, category=category, title=title, search_text=title.casefold())


class _CatalogProvider:
    def __init__(self) -> None:
        self.guides = [
            _guide("guide_complet", "aventure", "Guide Succès"),
            _guide("dofus_sylvestre", "aventure", "Lanyel Sylvestre"),
            _guide("dofus_turquoise", "dofus", "Turquoise"),
            _guide("dofus_cawotte", "dofus", "Cawotte"),
            _guide("alignement_bonta", "alignements", "Bonta"),
            _guide("alignement_brakmar", "alignements", "Brâkmar"),
        ]

    def search(self, query: str):
        value = str(query or "").casefold().strip()
        return [guide for guide in self.guides if not value or value in guide.search_text]

    def load_all(self):
        return list(self.guides)


class GuideHomeTwoColumnsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _ids(model: GuideListModel) -> list[str]:
        return [
            str(model.index(i, 0).data(GUIDE_ID_ROLE))
            for i in range(model.rowCount())
            if model.index(i, 0).data(GUIDE_ID_ROLE) is not None
        ]

    @staticmethod
    def _headings(model: GuideListModel) -> list[str]:
        return [
            str(model.index(i, 0).data(GUIDE_GROUP_ROLE))
            for i in range(model.rowCount())
            if model.index(i, 0).data(GUIDE_GROUP_ROLE)
        ]

    def test_model_keeps_left_guide_order_and_dofus_in_right_column(self) -> None:
        provider = _CatalogProvider()
        left, right = GuideListModel(), GuideListModel()
        left.set_home_column(provider.guides, "left")
        right.set_home_column(provider.guides, "right")
        self.assertEqual(
            self._headings(left),
            ["GUIDE SUCCÈS", "GUIDES OPTIMISÉS", "ALIGNEMENTS"],
        )
        self.assertEqual(
            self._ids(left),
            ["guide_complet", "dofus_sylvestre", "alignement_bonta", "alignement_brakmar"],
        )
        self.assertEqual(self._headings(right), [])  # No empty title-grid cell.
        self.assertEqual(self._ids(right), ["dofus_turquoise", "dofus_cawotte"])
        self.assertEqual(left.row_for_guide("dofus_turquoise"), -1)
        self.assertEqual(right.row_for_guide("dofus_sylvestre"), -1)
        self.assertEqual(right.rowCount(), 2)

    def test_identical_guide_refresh_keeps_model_and_progress_idle(self) -> None:
        provider = _CatalogProvider()
        model = GuideListModel()
        resets = QSignalSpy(model.modelReset)
        changes = QSignalSpy(model.dataChanged)
        model.set_home_column(provider.guides, "right")
        self.assertEqual(resets.count(), 1)
        before_ids = self._ids(model)
        model.set_home_column(list(provider.guides), "right")
        self.assertEqual(resets.count(), 1)
        self.assertEqual(self._ids(model), before_ids)
        model.set_progress({"dofus_turquoise": (1, 3, "En cours")})
        self.assertEqual(changes.count(), 1)
        model.set_progress({"dofus_turquoise": (1, 3, "En cours")})
        self.assertEqual(changes.count(), 1)
        model.set_progress({"dofus_turquoise": (2, 3, "En cours")})
        self.assertEqual(changes.count(), 2)
        # Only a genuine replacement of the underlying Guide must reset Qt.
        model.set_home_column([_guide("dofus_turquoise", "dofus", "Turquoise")], "right")
        self.assertEqual(resets.count(), 2)
        self.assertEqual(self._ids(model), ["dofus_turquoise"])

    def test_icons_decode_only_once_until_guide_replacement(self) -> None:
        model = GuideListModel()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "turquoise.png"
            path.write_bytes(b"image-file-fixture")
            guide = replace(_guide("dofus_turquoise", "dofus", "Turquoise"),
                            image_path=str(path))
            model.set_home_column([guide], "right")
            with patch(
                "app.modules.encyclopedia.widgets.guide_card.ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled",
                return_value=QPixmap(16, 16),
            ) as decode:
                index = model.index(0, 0)
                for _ in range(12):
                    self.assertIsNotNone(model.data(index, Qt.DecorationRole))
                self.assertEqual(decode.call_count, 1)
                model.set_home_column([guide], "right")
                self.assertIsNotNone(model.data(model.index(0, 0), Qt.DecorationRole))
                self.assertEqual(decode.call_count, 1)
                # Replaced metadata needs a fresh icon decision.
                model.set_home_column([replace(guide, title="Turquoise +")], "right")
                self.assertIsNotNone(model.data(model.index(0, 0), Qt.DecorationRole))
                self.assertEqual(decode.call_count, 2)

    def test_grid_balances_five_dofus_instead_of_leaving_one_orphan(self) -> None:
        columns = GuideCatalogView._balanced_grid_columns
        self.assertEqual(columns(1024, 5), 3)  # 3 + 2, not 4 + 1
        self.assertEqual(columns(1024, 6), 3)  # Two full rows
        self.assertEqual(columns(1024, 7), 4)  # 4 + 3
        self.assertEqual(columns(1024, 9), 3)  # Three full rows
        self.assertEqual(columns(1024, 11), 4)  # 4 + 4 + 3
        self.assertEqual(columns(1024, 22), 2)  # No orphan if exact fit exists
        self.assertEqual(columns(610, 5), 2)   # Never squeeze 3 narrow cards
        self.assertEqual(columns(180, 5), 1)
        self.assertEqual(columns(1024, 1), 1)
        self.assertEqual(columns(1024, 0), 1)

    def test_grid_cells_fit_narrow_and_scaled_viewports(self) -> None:
        # High DPI / vertically stacked columns may leave less than 215px.
        self.assertEqual(GuideCatalogView._grid_cell_width(0), 0)
        for viewport_width in (1, 120, 180, 214, 229, 230, 319, 320, 459, 460, 610, 730, 1024):
            with self.subTest(viewport_width=viewport_width):
                cell_width = GuideCatalogView._grid_cell_width(viewport_width)
                self.assertGreaterEqual(cell_width, 1)
                self.assertLessEqual(cell_width, viewport_width)
                self.assertLessEqual(cell_width, 320)

    def test_lazy_home_search_navigation_and_responsive_grid(self) -> None:
        provider = _CatalogProvider()
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "app.modules.encyclopedia.views.guide_catalog_view.catalog_route_map_count_hint",
                return_value=0,
            ):
                view = GuideCatalogView(
                    lambda _text: None,
                    provider=provider,
                    quest_progress_path=Path(directory) / "quest_progress.json",
                    defer_runtime=True,
                )
                view._progress_snapshot = lambda: {}
                view.hydrate_runtime()
                view.resize(1200, 750)
                view.show()
                view.refresh_home()
                self.app.processEvents()
                try:
                    self.assertEqual(
                        view.home_columns.layout().direction(),
                        QBoxLayout.LeftToRight,
                    )
                    self.assertGreater(view.home_columns._left.maximumHeight(), 1000)
                    self.assertEqual(
                        view.home_dofus_list.viewMode(), QListView.IconMode
                    )
                    self.assertTrue(view.home_dofus_list.isVisibleTo(view))
                    self.assertEqual(
                        self._ids(view.home_dofus_model),
                        ["dofus_turquoise", "dofus_cawotte"],
                    )
                    requested: list[str] = []
                    view.guideRequested.connect(requested.append)
                    row = view.home_dofus_model.row_for_guide("dofus_turquoise")
                    self.assertGreaterEqual(row, 0)
                    view.home_dofus_list.clicked.emit(
                        view.home_dofus_model.index(row, 0)
                    )
                    self.assertEqual(requested, ["dofus_turquoise"])
                    # Alignements have real nested entries in the left menu;
                    # changing the menu does NOT overwrite the right Dofus grid.
                    alignments = view._category_nodes["alignements"]
                    self.assertEqual(
                        sum(bool(alignments.child(i).data(0, Qt.UserRole + 1))
                            for i in range(alignments.childCount())),
                        2,
                    )
                    view.library_categories.setCurrentItem(alignments)
                    self.assertEqual(
                        self._ids(view.home_dofus_model),
                        ["dofus_turquoise", "dofus_cawotte"],
                    )
                    view.library_categories.setCurrentItem(alignments.child(0))
                    self.assertEqual(requested[-1], "alignement_bonta")
                    self.assertEqual(
                        self._ids(view.home_dofus_model),
                        ["dofus_turquoise", "dofus_cawotte"],
                    )
                    view.set_search_text("bonta")
                    self.assertEqual(self._ids(view.result_model), ["alignement_bonta"])
                    self.assertEqual(self._ids(view.home_dofus_model), [])
                    self.assertFalse(view.home_dofus_list.isVisible())
                    view.set_search_text("")
                    self.assertEqual(
                        self._ids(view.home_dofus_model),
                        ["dofus_turquoise", "dofus_cawotte"],
                    )
                    view.resize(610, 750)
                    self.app.processEvents()
                    self.assertEqual(
                        view.home_columns.layout().direction(),
                        QBoxLayout.TopToBottom,
                    )
                    self.assertEqual(view.home_columns._left.maximumHeight(), 220)
                    view.resize(1200, 750)
                    self.app.processEvents()
                    self.assertGreater(view.home_columns._left.maximumHeight(), 1000)
                finally:
                    view.close()
                    view.deleteLater()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
