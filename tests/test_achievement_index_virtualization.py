from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.views import encyclopedia_bootstrap_views as bootstrap


_ROWS = [
    (1, "Premier succès", "Quêtes", "Astrub", 20, 10, 1),
    (2, "Deuxième succès", "Quêtes", "Astrub", 30, 10, 2),
    (3, "Troisième succès", "Quêtes", "Amakna", 40, 20, 3),
    (4, "Boss test", "Donjons", "Donjons 1-50", 50, 10, 1),
]


class AchievementIndexVirtualizationTests(unittest.TestCase):
    def _view(self) -> bootstrap.AchievementIndexView:
        # The test injects rows directly: no background catalogue read is needed.
        with patch.object(bootstrap, "Thread") as thread_cls:
            view = bootstrap.AchievementIndexView(data_dir=Path("."))
            thread_cls.return_value.start.assert_called_once_with()
        view._apply_rows(list(_ROWS))
        return view

    def test_initial_tree_materializes_only_collapsed_top_categories(self) -> None:
        view = self._view()
        try:
            self.assertEqual(view.tree.topLevelItemCount(), 2)
            first = view.tree.topLevelItem(0)
            second = view.tree.topLevelItem(1)
            self.assertFalse(first.isExpanded())
            self.assertFalse(second.isExpanded())
            self.assertEqual(first.childCount(), 1)
            self.assertEqual(second.childCount(), 1)
            self.assertEqual(
                first.child(0).data(0, bootstrap._ACHIEVEMENT_NODE_KIND_ROLE),
                "placeholder",
            )
        finally:
            view.deleteLater()

    def test_expansion_materializes_only_requested_branch(self) -> None:
        view = self._view()
        try:
            top = view.tree.topLevelItem(0)
            other_top = view.tree.topLevelItem(1)
            view._on_item_expanded(top)

            self.assertEqual(top.childCount(), 2)
            self.assertEqual(other_top.childCount(), 1)
            self.assertEqual(
                other_top.child(0).data(0, bootstrap._ACHIEVEMENT_NODE_KIND_ROLE),
                "placeholder",
            )

            sub = top.child(0)
            view._on_item_expanded(sub)
            self.assertEqual(sub.childCount(), 1)
            self.assertIsNotNone(sub.child(0).data(0, bootstrap._ACHIEVEMENT_ID_ROLE))

            untouched_sub = top.child(1)
            self.assertEqual(untouched_sub.childCount(), 1)
            self.assertEqual(
                untouched_sub.child(0).data(0, bootstrap._ACHIEVEMENT_NODE_KIND_ROLE),
                "placeholder",
            )
        finally:
            view.deleteLater()

    def test_explicit_search_materializes_only_matching_success(self) -> None:
        view = self._view()
        try:
            view.search.setText("Boss test")
            self.assertEqual(view.tree.topLevelItemCount(), 1)
            top = view.tree.topLevelItem(0)
            self.assertEqual(top.text(0), "Donjons")
            self.assertEqual(top.childCount(), 1)
            sub = top.child(0)
            self.assertEqual(sub.childCount(), 1)
            self.assertEqual(sub.child(0).data(0, bootstrap._ACHIEVEMENT_ID_ROLE), 4)
        finally:
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
