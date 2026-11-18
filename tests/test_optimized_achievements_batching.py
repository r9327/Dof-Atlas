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
        self._by_id = {int(row.id): row for row in self.achievements}

    def is_retained(self, _achievement_id: int) -> bool:
        return True

    def get_by_category(self, _category_id: int):
        return list(self.achievements)

    def search(self, text: str):
        query = str(text or "").strip().casefold()
        return [
            row
            for row in self.achievements
            if query in str(row.name or "").casefold()
        ]

    def get_by_id(self, achievement_id: int):
        return self._by_id.get(int(achievement_id))

    def catalogue_row_by_id(self, achievement_id: int):
        row = self.get_by_id(achievement_id)
        if row is None:
            return None
        return (int(row.id), str(row.name), row.level, int(row.points))


class _BatchFakeProvider(_FakeProvider):
    def __init__(self, achievements) -> None:
        super().__init__(achievements)
        self.batch_calls: list[tuple[int, ...]] = []

    def catalogue_rows_by_ids(self, achievement_ids: list[int]):
        self.batch_calls.append(tuple(achievement_ids))
        return [self.catalogue_row_by_id(ident) for ident in achievement_ids]


class _FakeProgressService:
    def __init__(self, completed=()) -> None:
        self.completed = frozenset(int(value) for value in completed)

    def state_for(self, _character_key: str):
        return SimpleNamespace(completed_achievements=self.completed)


class _LightAchievementsView(AchievementsView):
    def __init__(self, achievements) -> None:
        QWidget.__init__(self)
        self._runtime_ready = True
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
        self._achievement_visible_row_by_id = {}
        self._achievement_pending_selected_id = None
        self._achievement_rows_dirty = False
        self._achievement_completed_ids = frozenset()
        self._achievement_rendering_batch = False
        self._achievement_initializing = False
        self._detail_open = False
        self._detail_generation = 0
        self._detail_requested = None
        self._detail_worker_running = False

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
        category_id=1,
        subcategory_id=None,
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

    def test_batch_provider_is_called_once_for_visible_rows(self) -> None:
        view = self._view(50)
        view.provider = _BatchFakeProvider(view.achievements)
        try:
            view.refresh()
            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            view.hide()
            view.list_widget.clear()
            view._achievement_pending_rows = [int(row.id) for row in view.filtered]
            view._achievement_rows_dirty = True
            view.show()
            view._achievement_batch_timer.stop()
            view.provider.batch_calls.clear()

            view._render_next_achievement_batch()
            view._achievement_batch_timer.stop()

            self.assertEqual(view.provider.batch_calls, [tuple(range(1, 9))])
            self.assertEqual(view.list_widget.count(), _RESULT_BATCH_SIZE)
            self.assertEqual(len(view._achievement_pending_rows), 50 - _RESULT_BATCH_SIZE)
            self.assertTrue(bool(view.list_widget.item(1).data(COMPLETED_ROLE)))
        finally:
            view.close()
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
                int(row.id)
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

    def test_repeated_refresh_preserves_deferred_success_batches(self) -> None:
        view = self._view(150)
        try:
            view.refresh()
            snapshot_generation = view._achievement_render_generation
            pending = tuple(view._achievement_pending_rows)
            view.refresh()  # Re-entrant update before the first visible frame.
            self.assertEqual(view._achievement_render_generation, snapshot_generation)
            self.assertEqual(tuple(view._achievement_pending_rows), pending)

            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            view._render_next_achievement_batch()
            view._achievement_batch_timer.stop()
            visible = view.list_widget.count()
            self.assertGreater(visible, 0)
            self.assertTrue(view._achievement_pending_rows)
            view.refresh()  # Activation without any filter/category change.
            self.assertEqual(view._achievement_render_generation, snapshot_generation)
            self.assertEqual(view.list_widget.count(), visible)
            self.assertGreater(len(view._achievement_pending_rows), 0)
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_search_uses_compact_ids_without_rich_catalogue_filter(self) -> None:
        view = self._view(100)
        try:
            view.provider = _BatchFakeProvider(view.achievements)
            requested = []

            def compact_search(query):
                requested.append(query)
                return (7, 40)

            def no_rich_search(_query):
                raise AssertionError("search must not hydrate rich Successes")

            view.provider.search_catalogue_ids = compact_search
            view.provider.search = no_rich_search
            view.search.setText("grand monstre")
            view.refresh()

            self.assertEqual(requested, ["grand monstre"])
            self.assertEqual([item.id for item in view.filtered], [7, 40])
            self.assertEqual(view._achievement_pending_rows, [7, 40])
            self.assertEqual(view.list_widget.count(), 0)
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
            self.assertTrue(
                all(
                    view.provider.get_by_id(row_id).name.startswith("Beta succes")
                    for row_id in view._achievement_pending_rows
                )
            )
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

            while view._achievement_pending_rows and not any(
                int(view.list_widget.item(row).data(Qt.UserRole)) == 61
                for row in range(view.list_widget.count())
            ):
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

    def test_visible_batch_selection_keeps_user_scroll_position(self) -> None:
        view = self._view(120)
        try:
            view.list_widget.setFixedHeight(110)
            view.refresh()
            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            while view.list_widget.count() < 48 and view._achievement_pending_rows:
                view._render_next_achievement_batch()
                view._achievement_batch_timer.stop()
            bar = view.list_widget.verticalScrollBar()
            self.app.processEvents()
            self.assertGreater(bar.maximum(), 0)
            self.assertEqual(view.list_widget.currentItem().data(Qt.UserRole), 1)
            bar.setValue(bar.maximum())
            before_scroll = bar.value()
            view._apply_pending_achievement_selection()
            self.assertEqual(bar.value(), before_scroll)
            self.assertEqual(view._achievement_visible_row_by_id[1], 0)
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_rebuilt_search_discards_old_achievement_row_index(self) -> None:
        view = self._view(60)
        try:
            view.refresh()
            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            self.assertIn(1, view._achievement_visible_row_by_id)
            view.search.setText("aucun succès correspondant")
            view.refresh()
            self.assertEqual(view._achievement_visible_row_by_id, {})
            self.assertEqual(view.list_widget.count(), 0)
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_opened_success_stays_selected_during_later_lazy_batches(self) -> None:
        view = self._view(90)
        try:
            view.refresh()
            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            view.provider.get_detail_by_id = lambda ident: SimpleNamespace(
                id=ident, name=f"Succès {ident}"
            )
            view._display_achievement = lambda _achievement: None

            view.show_achievement(24)
            self.assertEqual(view._achievement_pending_selected_id, 24)
            while view.list_widget.count() < 40 and view._achievement_pending_rows:
                view._render_next_achievement_batch()
                view._achievement_batch_timer.stop()
            view._apply_pending_achievement_selection()
            self.assertEqual(view.list_widget.currentItem().data(Qt.UserRole), 24)
            if view._achievement_pending_rows:
                view._render_next_achievement_batch()
                view._achievement_batch_timer.stop()
                self.assertEqual(view.list_widget.currentItem().data(Qt.UserRole), 24)
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_deep_link_does_not_materialize_offscreen_success_rows(self) -> None:
        from unittest.mock import Mock

        view = self._view(150)
        try:
            view._tree_items = {}
            view.refresh()
            view.show()
            self.app.processEvents()
            view._achievement_batch_timer.stop()
            before = view.list_widget.count()
            self.assertLess(before, 150)

            detail = Mock()
            view.show_achievement = detail
            self.assertTrue(view.select_achievement(150))
            detail.assert_called_once_with(150)
            self.assertEqual(view._achievement_pending_selected_id, 150)
            self.assertEqual(view.list_widget.count(), before)
            self.assertTrue(view._achievement_pending_rows)

            # A later normal list batch can still restore selection without
            # re-opening the already shown detail.
            while view._achievement_pending_rows:
                view._render_next_achievement_batch()
                view._achievement_batch_timer.stop()
            self.assertEqual(view.list_widget.currentItem().data(Qt.UserRole), 150)
            detail.assert_called_once_with(150)
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
