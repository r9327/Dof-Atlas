from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QListWidgetItem, QTreeWidgetItem

from app.modules.encyclopedia.views.achievements_view import AchievementsView


class AchievementsThirdColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_view(self):
        provider = Mock()
        provider._recent_rich_details = None
        provider._detail_cache_id = None
        provider._detail_cache = None
        provider.get_by_id.side_effect = lambda achievement_id: SimpleNamespace(
            id=int(achievement_id), name="Succès de test"
        )
        provider.is_retained.return_value = True
        provider.get_detail_by_id.side_effect = lambda achievement_id: SimpleNamespace(
            id=int(achievement_id), name="Succès de test"
        )
        view = AchievementsView(
            lambda _status: None,
            provider,
            Mock(),
            quest_provider=Mock(),
            quest_graph=Mock(),
            quest_progress_service=Mock(),
            defer_runtime=True,
        )
        self.addCleanup(view.close)
        self.addCleanup(view.deleteLater)
        return view, provider

    @staticmethod
    def add_success(view, achievement_id: int) -> QListWidgetItem:
        item = QListWidgetItem(f"Succès {achievement_id}")
        item.setData(Qt.UserRole, achievement_id)
        view.list_widget.addItem(item)
        return item

    def test_third_column_is_visible_and_has_help_before_first_selection(self):
        view, provider = self.make_view()
        self.assertEqual(view.splitter.count(), 3)
        self.assertIs(view.splitter.widget(2), view.detail_stack)
        self.assertFalse(view.splitter.isCollapsible(2))
        self.assertGreaterEqual(view.detail_stack.minimumWidth(), 240)
        from app.ui.unity_palette import UNITY_SPACING_PX
        self.assertEqual(view.layout().spacing(), UNITY_SPACING_PX["md"])
        for panel in (view.category_panel, view.success_panel):
            layout = panel.layout()
            self.assertEqual(layout.spacing(), UNITY_SPACING_PX["md"])
            margins = layout.contentsMargins()
            self.assertEqual(
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
                (UNITY_SPACING_PX["lg"],) * 4,
            )
        self.assertIs(view.detail_stack.currentWidget(), view.detail_scroll)
        self.assertIn(
            "Sélectionnez un succès",
            " ".join(label.text() for label in view.detail_content.findChildren(QLabel)),
        )
        provider.get_detail_by_id.assert_not_called()

    def test_clicking_selected_success_twice_keeps_detail_open(self):
        view, provider = self.make_view()
        rendered = []
        view._display_achievement = lambda achievement: (
            rendered.append(achievement.id),
            setattr(view, "_detail_open", True),
        )
        item = self.add_success(view, 42)
        view.on_achievement_clicked(item)
        view.on_achievement_clicked(item)
        self.assertEqual(rendered, [42])
        self.assertEqual(view.current_achievement_id, 42)
        self.assertTrue(view._detail_open)
        self.assertEqual(provider.get_detail_by_id.call_count, 1)

    def test_category_change_cancels_debounced_search_and_refreshes_immediately(self):
        view, _provider = self.make_view()
        view.search.setText("ancienne recherche")
        self.assertTrue(view._search_debounce_timer.isActive())

        target = QTreeWidgetItem(["Nouvelle catégorie"])
        target.setData(0, Qt.UserRole, 19)
        with patch.object(view, "refresh") as refresh:
            view.on_category_changed(target, None)
            refresh.assert_called_once_with()

        self.assertEqual(view.selected_category_id, 19)
        self.assertEqual(view.search.text(), "")
        self.assertFalse(view._search_debounce_timer.isActive())

    def test_direct_link_in_current_category_refreshes_stale_search(self):
        view, provider = self.make_view()
        category = QTreeWidgetItem(["Quêtes"])
        category.setData(0, Qt.UserRole, 19)
        view.category_tree.addTopLevelItem(category)
        view._tree_items[19] = category
        view.category_tree.setCurrentItem(category)
        view.selected_category_id = 19

        view._runtime_ready = True
        view.progress_service.state_for.return_value = SimpleNamespace(
            completed_achievements=set()
        )
        provider.catalogue_ids.return_value = [42]
        provider.get_by_id.side_effect = lambda achievement_id: SimpleNamespace(
            id=int(achievement_id), name="Cible", category_id=19,
            subcategory_id=None,
        )
        view.filtered = [SimpleNamespace(id=99)]
        view.search.setText("ancien filtre")
        view.list_widget.clear()
        view.show_achievement = Mock()

        self.assertTrue(view.select_achievement(42))
        self.assertEqual(view.search.text(), "")
        self.assertEqual([row.id for row in view.filtered], [42])
        self.assertFalse(view._search_debounce_timer.isActive())
        view.show_achievement.assert_called_once_with(42)

    def test_tall_viewport_continues_loading_until_it_can_scroll(self):
        view, provider = self.make_view()
        view.resize(1600, 1200)
        view.show()
        self.app.processEvents()

        provider.catalogue_row_by_id.side_effect = (
            lambda achievement_id: (achievement_id, f"Succès {achievement_id}", None, 0)
        )
        # defer_runtime adds a loading placeholder; hydrated catalogues
        # replace it before rendering their first real row.
        view.list_widget.clear()
        view._achievement_completed_ids = frozenset()
        view._achievement_pending_rows = list(range(1, 41))
        view._achievement_rows_dirty = True

        # First batch is followed by the usual initial batch.
        view._render_next_achievement_batch()
        view._achievement_batch_timer.stop()
        view._render_next_achievement_batch()

        self.assertEqual(view.list_widget.count(), 16)
        self.assertEqual(view.list_widget.verticalScrollBar().maximum(), 0)
        self.assertGreater(view.list_widget.viewport().height(), 0)
        self.assertTrue(
            view._achievement_batch_timer.isActive(),
            "Pending achievements must remain reachable on a tall window with no scrollbar",
        )

    def test_keyboard_item_activation_opens_details_without_extra_load(self):
        view, provider = self.make_view()
        rendered = []
        view._display_achievement = lambda achievement: (
            rendered.append(achievement.id),
            setattr(view, "_detail_open", True),
        )
        item = self.add_success(view, 84)
        view.list_widget.itemActivated.emit(item)
        self.assertEqual(rendered, [84])
        view.list_widget.itemActivated.emit(item)
        self.assertEqual(rendered, [84])
        self.assertEqual(provider.get_detail_by_id.call_count, 1)


if __name__ == "__main__":
    unittest.main()
