from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QListWidgetItem

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
