from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget, QWidget

from app.modules.encyclopedia.views.achievements_view import (
    AchievementsView,
    COMPLETED_ROLE,
    _RESULT_BATCH_SIZE,
)


class _FakeProvider:
    def __init__(self, achievements) -> None:
        self.achievements = list(achievements)

    def is_retained(self, _achievement_id: int) -> bool:
        return True

    def get_by_category(self, _category_id: int):
        return list(self.achievements)


class _FakeProgressService:
    def __init__(self, completed=()) -> None:
        self.completed = frozenset(int(value) for value in completed)

    def state_for(self, _character_key: str):
        return SimpleNamespace(completed_achievements=self.completed)


class _LightAchievementsView(AchievementsView):
    def __init__(self, achievements) -> None:
        QWidget.__init__(self)
        self.achievements = list(achievements)
        self.provider = _FakeProvider(self.achievements)
        self.progress_service = _FakeProgressService({2, 65})
        self.character_key = "slot:1"
        self.selected_category_id = 1
        self.current_achievement_id = None
        self.filtered = []
        self.search = QLineEdit(self)
        self.list_widget = QListWidget(self)
        self.status_messages = []
        self.status_callback = self.status_messages.append

        self._catalog_refresh_signature = None
        self._achievement_render_generation = 0
        self._achievement_pending_rows = []
        self._achievement_pending_selected_id = None
        self._achievement_rows_dirty = False
        self._achievement_completed_ids = frozenset()
        self._achievement_initializing = False
        self._detail_open = False

        self._achievement_batch_timer = QTimer(self)
        self._achievement_batch_timer.setSingleShot(True)
        self._achievement_batch_timer.setInterval(0)
        self._achievement_batch_timer.timeout.connect(self._render_next_achievement_batch)

    def close_detail_panel(self) -> None:
        self._detail_open = False

    def category_label(self, _category_id) -> str:
        return "Test"


def _achievement(ident: int, name: str):
    return SimpleNamespace(
        id=int(ident),
        name=name,
        level=ident % 200,
        points=5,
        search_text=name.casefold().replace(" ", "_"),
    )


class OptimizedAchievementsBatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def _view(self, count: int = 150) -> _LightAchievementsView:
        return _LightAchievementsView(
            [_achievement(index + 1, f"Succes test {index:03d}") for index in range(count)]
        )

    def test_hidden_refresh_keeps_rows_as_snapshot_without_qt_items(self) -> None:
        view = self._view()
        try:
            view.refresh()

            self.assertEqual(view.list_widget.count(), 0)
            self.assertEqual(len(view._achievement_pending_rows), 150)
            self.assertTrue(view._achievement_rows_dirty)
            self.assertEqual(view.current_achievement_id, 1)
        finally:
            view.deleteLater()
            self.app.processEvents()

    def test_visible_render_is_bounded_to_one_batch_per_callback(self) -> None:
        view = self._view()
        try:
            view.refresh()
            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            # showEvent may have consumed one or more zero-delay ticks depending
            # on the platform. Reset to the deterministic pending snapshot.
            view.hide()
            view.list_widget.clear()
            view._achievement_pending_rows = [
                (int(row.id), view._achievement_row_text(row), row.name)
                for row in view.filtered
            ]
            view._achievement_rows_dirty = True
            view.show()
            view._achievement_batch_timer.stop()

            view._render_next_achievement_batch()
            view._achievement_batch_timer.stop()

            self.assertEqual(view.list_widget.count(), _RESULT_BATCH_SIZE)
            self.assertEqual(len(view._achievement_pending_rows), 150 - _RESULT_BATCH_SIZE)
            self.assertTrue(view._achievement_rows_dirty)
            self.assertTrue(bool(view.list_widget.item(1).data(COMPLETED_ROLE)))
            self.assertFalse(bool(view.list_widget.item(0).data(COMPLETED_ROLE)))
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_new_search_discards_old_pending_generation(self) -> None:
        achievements = [
            *[_achievement(index + 1, f"Alpha succes {index:02d}") for index in range(90)],
            *[_achievement(index + 101, f"Beta succes {index:02d}") for index in range(40)],
        ]
        view = _LightAchievementsView(achievements)
        try:
            view.show()
            view.search.setText("alpha")
            view.refresh()
            view._achievement_batch_timer.stop()
            view._render_next_achievement_batch()
            view._achievement_batch_timer.stop()
            old_generation = view._achievement_render_generation
            self.assertEqual(view.list_widget.count(), _RESULT_BATCH_SIZE)
            self.assertTrue(view._achievement_pending_rows)

            view.search.setText("beta")
            view.refresh()
            view._achievement_batch_timer.stop()

            self.assertGreater(view._achievement_render_generation, old_generation)
            self.assertEqual(view.list_widget.count(), 0)
            self.assertEqual(len(view._achievement_pending_rows), 40)
            self.assertTrue(all(row[1].startswith("Beta succes") for row in view._achievement_pending_rows))
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_progress_refresh_updates_rendered_and_future_batches(self) -> None:
        view = self._view(80)
        try:
            view.refresh()
            view.show()
            view._achievement_batch_timer.stop()
            view._render_next_achievement_batch()
            view._achievement_batch_timer.stop()

            view.progress_service.completed = frozenset({1, 61})
            view.refresh_completion_styles()
            self.assertTrue(bool(view.list_widget.item(0).data(COMPLETED_ROLE)))
            self.assertFalse(bool(view.list_widget.item(1).data(COMPLETED_ROLE)))

            view._render_next_achievement_batch()
            view._achievement_batch_timer.stop()
            item_61 = next(
                view.list_widget.item(row)
                for row in range(view.list_widget.count())
                if int(view.list_widget.item(row).data(Qt.UserRole)) == 61
            )
            self.assertTrue(bool(item_61.data(COMPLETED_ROLE)))
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
