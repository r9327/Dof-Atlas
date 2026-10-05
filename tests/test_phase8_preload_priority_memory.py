from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app.background_work as background_work
import app.modules.encyclopedia.services.related_data_service as related_data_service


class PreloadPriorityBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        with background_work._PRELOAD_PRIORITY_LOCK:
            background_work._PRELOAD_THREAD_IDS.clear()
            background_work._USER_PRIORITY_TASKS.clear()

    def tearDown(self) -> None:
        with background_work._PRELOAD_PRIORITY_LOCK:
            background_work._PRELOAD_THREAD_IDS.clear()
            background_work._USER_PRIORITY_TASKS.clear()

    def test_user_click_promotes_already_running_preload_without_restarting_it(self) -> None:
        owner = SimpleNamespace(preload_user_tasks=set())
        self.assertTrue(background_work.install_preload_priority_bridge(owner))
        self.assertIsInstance(owner.preload_user_tasks, background_work.PreloadUserTaskSet)

        with background_work._PRELOAD_PRIORITY_LOCK:
            background_work._PRELOAD_THREAD_IDS["craft"] = 4242

        with patch.object(
            background_work,
            "promote_background_thread",
            return_value=True,
        ) as promote:
            owner.preload_user_tasks.add("craft")

        promote.assert_called_once_with(4242)
        self.assertIn("craft", owner.preload_user_tasks)
        with background_work._PRELOAD_PRIORITY_LOCK:
            self.assertIn("craft", background_work._USER_PRIORITY_TASKS)

        owner.preload_user_tasks.discard("craft")
        with background_work._PRELOAD_PRIORITY_LOCK:
            self.assertNotIn("craft", background_work._USER_PRIORITY_TASKS)

    def test_click_before_worker_registration_makes_worker_start_foreground(self) -> None:
        owner = SimpleNamespace(preload_user_tasks=set())
        background_work.install_preload_priority_bridge(owner)
        owner.preload_user_tasks.add("encyclopedia")

        fake_thread = SimpleNamespace(name="DofusAtlasPreload-encyclopedia")
        with (
            patch.object(background_work, "current_thread", return_value=fake_thread),
            patch.object(background_work, "get_native_id", return_value=5151),
        ):
            task = background_work._current_preload_task()
            native_id, foreground = background_work._register_current_preload_worker(task)

        self.assertEqual(task, "encyclopedia")
        self.assertEqual(native_id, 5151)
        self.assertTrue(foreground)
        background_work._unregister_preload_worker(task, native_id)


class LightweightRelatedPreloadTests(unittest.TestCase):
    def setUp(self) -> None:
        with related_data_service._CACHE_LOCK:
            related_data_service._CACHED_CATALOG = None
            related_data_service._CACHED_DATA = None
            related_data_service._BUILD_COUNT = 0

    def tearDown(self) -> None:
        with related_data_service._CACHE_LOCK:
            related_data_service._CACHED_CATALOG = None
            related_data_service._CACHED_DATA = None
            related_data_service._BUILD_COUNT = 0

    def test_related_preload_keeps_heavy_success_and_guide_providers_cold(self) -> None:
        catalog = object()
        quest_provider = Mock(name="quest_provider")
        quest_graph = Mock(name="quest_graph")

        with (
            patch.object(related_data_service, "QuestProvider", return_value=quest_provider) as provider_type,
            patch.object(related_data_service, "QuestGraphService", return_value=quest_graph) as graph_type,
            patch.object(related_data_service, "_warm_achievement_source_indexes", return_value=7) as warm_success,
            patch.object(related_data_service, "_warm_guide_files", return_value=23) as warm_guides,
        ):
            first = related_data_service.build_related_encyclopedia_data(catalog)
            second = related_data_service.build_related_encyclopedia_data(catalog)

        self.assertIs(first, second)
        self.assertIsNone(first.achievement_provider)
        self.assertEqual(first.guide_provider.load_all(), [])
        self.assertIs(first.quest_graph, quest_graph)
        self.assertEqual(first.warmed_source_count, 7)
        self.assertEqual(first.warmed_guide_file_count, 23)
        provider_type.assert_called_once_with(catalog=catalog)
        graph_type.assert_called_once_with(quest_provider)
        warm_success.assert_called_once_with()
        warm_guides.assert_called_once_with()
        self.assertEqual(related_data_service.related_data_build_count(), 1)


if __name__ == "__main__":
    unittest.main()
