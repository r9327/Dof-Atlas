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

    def test_corrupt_list_item_id_does_not_replace_open_success(self):
        view, provider = self.make_view()
        view.current_achievement_id = 42
        view._detail_open = True
        view.show_achievement = Mock()
        for bad in (None, "", "bad", -7, True, 1.2):
            with self.subTest(raw=repr(bad)):
                item = QListWidgetItem("Enregistrement corrompu")
                item.setData(Qt.UserRole, bad)
                view.on_achievement_clicked(item)
        view.show_achievement.assert_not_called()
        self.assertEqual(view.current_achievement_id, 42)
        self.assertTrue(view._detail_open)
        provider.get_detail_by_id.assert_not_called()

    def test_malformed_show_success_id_does_not_close_current_detail(self):
        view, provider = self.make_view()
        view.current_achievement_id = 42
        view._detail_open = True
        for bad in (None, "bad", 0, -1, True, 1.5):
            with self.subTest(raw=repr(bad)):
                view.show_achievement(bad)
        self.assertEqual(view.current_achievement_id, 42)
        self.assertTrue(view._detail_open)
        provider.is_retained.assert_not_called()
        provider.get_detail_by_id.assert_not_called()

    def test_loading_and_error_drop_old_lazy_success_batches(self):
        view, _provider = self.make_view()
        for label, announce in (
            ("chargement", lambda: view.show_runtime_loading()),
            ("erreur", lambda: view.show_runtime_error("Données indisponibles")),
        ):
            with self.subTest(state=label):
                view._achievement_pending_rows = [42, 43, 44]
                view._achievement_visible_row_by_id = {42: 0}
                view._achievement_pending_selected_id = 42
                view._achievement_rows_dirty = True
                view._catalog_refresh_signature = (7, "ancien")
                view.filtered = [SimpleNamespace(id=42)]
                view._achievement_batch_timer.start()
                generation = view._achievement_render_generation
                announce()

                self.assertFalse(view._achievement_batch_timer.isActive())
                self.assertEqual(view._achievement_render_generation, generation + 1)
                self.assertEqual(view._achievement_pending_rows, [])
                self.assertEqual(view._achievement_visible_row_by_id, {})
                self.assertIsNone(view._achievement_pending_selected_id)
                self.assertFalse(view._achievement_rows_dirty)
                self.assertIsNone(view._catalog_refresh_signature)
                self.assertEqual(view.filtered, [])
                self.assertEqual(view.list_widget.count(), 1)
                self.assertFalse(view.list_widget.item(0).flags() & Qt.ItemIsEnabled)

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

    def test_malformed_success_deep_link_is_rejected_without_qt_exception(self):
        view, provider = self.make_view()
        provider.get_by_id.side_effect = AssertionError("no summary read")
        for malformed in (None, "", "not-an-id", "42/other", -1, 0, True, 1.5e999):
            with self.subTest(value=repr(malformed)):
                self.assertFalse(view.select_achievement(malformed))
        provider.is_retained.assert_not_called()
        provider.get_by_id.assert_not_called()
        provider.get_detail_by_id.assert_not_called()

    def test_every_cross_module_entity_link_rejects_invalid_numeric_ids(self):
        view, provider = self.make_view()
        view.navigate_callback = Mock(return_value=True)
        view.quest_provider.get_quest.return_value = SimpleNamespace(id=42)
        for invalid in (None, "", "abc", "42-other", -1, 0, True, 1.5, "9" * 5000):
            with self.subTest(value=repr(invalid)[:50]):
                self.assertFalse(view.show_quest(invalid))
                self.assertFalse(view.open_quest_in_quests(invalid))
                self.assertFalse(view.open_linked_entity("quest", invalid))
                self.assertFalse(view.open_linked_entity("achievement", invalid))
                self.assertFalse(view.open_linked_entity("monster", invalid))
                self.assertFalse(view.open_prerequisite_in_quests(invalid))
                self.assertFalse(view.open_shared_entity("quest", invalid))
                self.assertFalse(view.open_shared_entity("achievement", invalid))
                view.on_alignment_quest_activated("quest", invalid)
        view.navigate_callback.assert_not_called()
        view.quest_provider.get_quest.assert_not_called()
        provider.is_retained.assert_not_called()

    def test_cross_module_entity_links_preserve_valid_ids_and_context(self):
        view, _provider = self.make_view()
        view.navigate_callback = Mock(return_value=True)
        view.quest_provider.get_quest.side_effect = (
            lambda quest_id: SimpleNamespace(id=quest_id) if quest_id == 42 else None
        )
        view.current_achievement_id = 8
        self.assertTrue(view.open_shared_entity("quest", " 42 "))
        view.navigate_callback.assert_called_once_with(
            "quest", 42, source="achievement_link", achievement_id=8,
        )
        view.navigate_callback.reset_mock()
        self.assertTrue(view.open_linked_entity("monster", "42"))
        view.navigate_callback.assert_called_once_with(
            "monster", 42, source="achievement",
        )
        view.navigate_callback.reset_mock()
        self.assertTrue(view.open_prerequisite_in_quests("42"))
        view.navigate_callback.assert_called_once_with(
            "quest", 42, source="achievement_prerequisite", achievement_id=8,
        )
        with patch.object(view, "select_achievement", return_value=True) as select:
            self.assertTrue(view.open_shared_entity("achievement", "42"))
            self.assertTrue(view.open_linked_entity("achievement", "42"))
            self.assertEqual(select.call_count, 2)

    def test_invalid_success_direct_link_skips_compatibility_jsonl_read(self):
        view, provider = self.make_view()
        provider.is_retained.return_value = False
        provider.get_by_id.side_effect = AssertionError(
            "A missing Success ID must never hydrate on the Qt thread"
        )
        with patch.object(view.category_tree, "setCurrentItem") as select:
            self.assertFalse(view.select_achievement(999999))
            provider.is_retained.assert_called_once_with(999999)
            provider.get_by_id.assert_not_called()
            provider.get_detail_by_id.assert_not_called()
            select.assert_not_called()

    def test_cold_detail_click_skips_compatibility_summary_on_qt_thread(self):
        view, provider = self.make_view()
        provider._recent_rich_details = {}
        provider.detail_sources_ready = False
        provider.detail_source_index_required.return_value = False
        provider.get_by_id.side_effect = AssertionError(
            "A cold click must not read the compact summary on the UI thread"
        )
        view._display_achievement = Mock()

        with patch("app.modules.encyclopedia.views.achievements_view.Thread") as thread:
            view.show_achievement(93)
            provider.is_retained.assert_called_with(93)
            provider.get_by_id.assert_not_called()
            provider.get_detail_by_id.assert_not_called()
            thread.assert_called_once()

            # The real rich read belongs only to the existing detail worker.
            thread.call_args.kwargs["target"]()
            self.app.processEvents()

        provider.get_detail_by_id.assert_called_once_with(93)

    def test_invalid_detail_id_does_not_start_worker_or_read_summary(self):
        view, provider = self.make_view()
        provider.is_retained.return_value = False
        provider.get_by_id.side_effect = AssertionError(
            "An unknown Success should fail membership before reading detail"
        )

        with patch("app.modules.encyclopedia.views.achievements_view.Thread") as thread:
            view.show_achievement(9999)
            provider.get_by_id.assert_not_called()
            provider.get_detail_by_id.assert_not_called()
            thread.assert_not_called()
        self.assertIsNone(view.current_achievement_id)

    def test_catalogue_only_preload_skips_reward_source_index(self):
        from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider

        provider = AchievementProvider()
        with (
            patch.object(provider, "_ensure_loaded") as catalogue,
            patch.object(provider, "prepare_detail_sources") as rewards,
        ):
            self.assertIsNone(provider.load_catalogue_only())
            catalogue.assert_called_once_with()
            rewards.assert_not_called()
            self.assertEqual(provider.load_all(), [])
            self.assertEqual(catalogue.call_count, 2)
            rewards.assert_called_once_with()

    def test_installed_provider_defers_reward_index_until_detail(self):
        from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
            MemoryBoundAchievementProvider,
        )

        provider = MemoryBoundAchievementProvider()
        with (
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.sys.frozen",
                True, create=True,
            ),
            patch.object(provider, "_ensure_loaded") as catalogue,
            patch.object(provider, "prepare_detail_sources") as rewards,
        ):
            self.assertTrue(provider.detail_source_index_required())
            provider.load_runtime()
            catalogue.assert_called_once_with()
            rewards.assert_not_called()
        # A development subprocess never needs an in-process index.
        with patch(
            "app.modules.encyclopedia.providers.memory_bound_achievement_provider.sys.frozen",
            False, create=True,
        ):
            self.assertFalse(provider.detail_source_index_required())

    def test_subprocess_detail_skips_unneeded_reward_index(self):
        view, provider = self.make_view()
        provider._recent_rich_details = {}
        provider.detail_sources_ready = False
        provider.detail_source_index_required.return_value = False
        view._display_achievement = Mock()
        with patch("app.modules.encyclopedia.views.achievements_view.Thread") as thread:
            view.show_achievement(93)
            provider.get_detail_by_id.assert_not_called()
            thread.assert_called_once()
            thread.call_args.kwargs["target"]()
            self.app.processEvents()
        provider.prepare_detail_sources.assert_not_called()
        provider.get_detail_by_id.assert_called_once_with(93)

    def test_first_cold_detail_prepares_rewards_only_on_worker(self):
        view, provider = self.make_view()
        provider.detail_sources_ready = False
        provider.prepare_detail_sources.side_effect = (
            lambda: setattr(provider, "detail_sources_ready", True)
        )
        view._display_achievement = Mock()
        with patch("app.modules.encyclopedia.views.achievements_view.Thread") as thread:
            view.show_achievement(42)
            # The Qt click may schedule work but must not index reward sources.
            provider.prepare_detail_sources.assert_not_called()
            provider.get_detail_by_id.assert_not_called()
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()
            self.assertEqual(view._detail_requested[1], 42)

            # Execute the captured task deterministically without spinning a
            # background thread; the real threaded path uses this same target.
            task = thread.call_args.kwargs["target"]
            task()
            self.app.processEvents()

        provider.prepare_detail_sources.assert_called_once_with()
        provider.get_detail_by_id.assert_called_once_with(42)
        self.assertTrue(provider.detail_sources_ready)
        self.assertEqual(view._detail_worker_running, False)

    def test_compact_direct_link_avoids_qt_summary_read(self):
        view, provider = self.make_view()
        calls = []

        class _CompactCategoryProvider:
            def __init__(self, delegate):
                self.delegate = delegate

            def __getattr__(self, name):
                return getattr(self.delegate, name)

            def catalogue_category_for_id(self, achievement_id):
                calls.append(achievement_id)
                return 19

        view.provider = _CompactCategoryProvider(provider)
        provider.get_by_id.side_effect = AssertionError(
            "Direct links must use compact category membership"
        )
        category = QTreeWidgetItem(["Catégorie rapide"])
        category.setData(0, Qt.UserRole, 19)
        view.category_tree.addTopLevelItem(category)
        view._tree_items[19] = category
        view.filtered = [SimpleNamespace(id=42)]
        view.show_achievement = Mock()

        self.assertTrue(view.select_achievement(42))
        self.assertEqual(calls, [42])
        self.assertIs(view.category_tree.currentItem(), category)
        provider.get_by_id.assert_not_called()
        view.show_achievement.assert_called_once_with(42)

    def test_direct_link_selects_actual_visible_id_after_a_skipped_cache_row(self):
        view, provider = self.make_view()
        provider.get_by_id.side_effect = lambda achievement_id: SimpleNamespace(
            id=int(achievement_id), name="Cible",
            subcategory_id=None, category_id=19,
        )
        category = QTreeWidgetItem(["Succès"])
        category.setData(0, Qt.UserRole, 19)
        view.category_tree.addTopLevelItem(category)
        view._tree_items[19] = category
        view.category_tree.setCurrentItem(category)
        view.filtered = [
            SimpleNamespace(id=10),
            SimpleNamespace(id=20),
            SimpleNamespace(id=42),
        ]
        view.list_widget.clear()
        self.add_success(view, 10)
        self.add_success(view, 42)
        # The compact row for ID 20 was skipped; filtered index 2 is not a
        # widget row. The actual Success 42 is widget row 1.
        view._achievement_visible_row_by_id = {10: 0, 42: 1}
        view.list_widget.setCurrentRow(0)
        view.show_achievement = Mock()

        self.assertTrue(view.select_achievement(42))
        self.assertEqual(view.list_widget.currentRow(), 1)
        self.assertEqual(
            view.list_widget.currentItem().data(Qt.UserRole), 42
        )
        view.show_achievement.assert_called_once_with(42)

    def test_direct_link_does_not_select_wrong_item_when_target_not_yet_visible(self):
        view, provider = self.make_view()
        provider.get_by_id.side_effect = lambda achievement_id: SimpleNamespace(
            id=int(achievement_id), name="Cible",
            subcategory_id=None, category_id=19,
        )
        category = QTreeWidgetItem(["Succès"])
        category.setData(0, Qt.UserRole, 19)
        view.category_tree.addTopLevelItem(category)
        view._tree_items[19] = category
        view.category_tree.setCurrentItem(category)
        view.filtered = [
            SimpleNamespace(id=10),
            SimpleNamespace(id=42),
            SimpleNamespace(id=99),
        ]
        view.list_widget.clear()
        self.add_success(view, 10)
        self.add_success(view, 99)
        view._achievement_visible_row_by_id = {10: 0, 99: 1}
        view.list_widget.setCurrentRow(0)
        view.show_achievement = Mock()

        self.assertTrue(view.select_achievement(42))
        # The detail can open before the target row is rendered, but the
        # previously selected Success 10 must no longer appear selected.
        self.assertEqual(view.list_widget.currentRow(), -1)
        self.assertEqual(view._achievement_pending_selected_id, 42)
        view.show_achievement.assert_called_once_with(42)

        # Lazy render later materializes exactly the intended Success.
        self.add_success(view, 42)
        view._achievement_visible_row_by_id[42] = 2
        view._apply_pending_achievement_selection()
        self.assertEqual(view.list_widget.currentRow(), 2)
        self.assertEqual(view.list_widget.currentItem().data(Qt.UserRole), 42)

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

        # If the user leaves before the next batch, showing the tab must
        # restore the timer even when the initial 16 items already exist.
        view._achievement_batch_timer.stop()
        view.hide()
        view.show()
        self.assertTrue(
            view._achievement_batch_timer.isActive(),
            "Returning to a tall Success tab must resume pending rows",
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
