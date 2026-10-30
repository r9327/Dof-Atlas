"""Qt contract: uncached Success details never run a blocking reader in the UI thread."""
from __future__ import annotations

import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.views.achievements_view import AchievementsView


class SuccessAsyncDetailRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for view in getattr(self, "_views", []):
            view.close()
            view.deleteLater()
        self.app.processEvents()

    def view(self):
        provider = Mock()
        provider._detail_cache_id = None
        provider._detail_cache = None
        provider._recent_rich_details = {}
        provider.get_by_id.side_effect = lambda identifier: SimpleNamespace(
            id=identifier, name=f"Succès {identifier}",
        )
        provider.is_retained.return_value = True
        view = AchievementsView(
            lambda _status: None, provider, Mock(),
            quest_provider=Mock(), quest_graph=Mock(),
            quest_progress_service=Mock(), defer_runtime=True,
        )
        rendered = []
        view._display_achievement = lambda result: (
            rendered.append((result.id, threading.get_ident())),
            setattr(view, "_detail_open", True),
        )
        self._views = [*getattr(self, "_views", []), view]
        return view, provider, rendered

    def pump(self, condition, *, timeout=3.0):
        stop = time.monotonic() + timeout
        while time.monotonic() < stop:
            self.app.processEvents()
            if condition():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return condition()

    def test_cold_detail_reads_only_on_background_thread(self):
        view, provider, rendered = self.view()
        read_threads = []
        main_thread = threading.get_ident()

        def read(identifier):
            read_threads.append(threading.get_ident())
            return SimpleNamespace(id=identifier, name="Test")

        provider.get_detail_by_id.side_effect = read
        view.show_achievement(42)
        self.assertFalse(view._detail_open)
        self.assertTrue(self.pump(lambda: len(rendered) == 1))
        self.assertEqual(rendered, [(42, main_thread)])
        self.assertTrue(read_threads)
        self.assertNotEqual(read_threads[0], main_thread)
        self.assertFalse(view._detail_worker_running)

    def test_latest_navigation_wins_with_single_worker(self):
        view, provider, rendered = self.view()
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def read(identifier):
            calls.append(identifier)
            if identifier == 1:
                entered.set()
                self.assertTrue(release.wait(timeout=3))
            return SimpleNamespace(id=identifier, name="Test")

        provider.get_detail_by_id.side_effect = read
        view.show_achievement(1)
        self.assertTrue(entered.wait(timeout=2))
        view.show_achievement(2)
        view.show_achievement(3)
        self.assertFalse(view._detail_open)
        release.set()
        self.assertTrue(self.pump(lambda: bool(rendered)))
        self.assertEqual(calls, [1, 3])
        self.assertEqual([row[0] for row in rendered], [3])
        self.assertFalse(view._detail_worker_running)

    def test_hot_details_render_immediately_and_cancel_obsolete_worker(self):
        view, provider, rendered = self.view()
        release = threading.Event()
        entered = threading.Event()

        def read(identifier):
            if identifier == 1:
                entered.set()
                release.wait(timeout=2)
            return SimpleNamespace(id=identifier)

        provider.get_detail_by_id.side_effect = read
        view.show_achievement(1)
        self.assertTrue(entered.wait(timeout=2))
        provider._detail_cache_id = 2
        provider._detail_cache = SimpleNamespace(id=2)
        view.show_achievement(2)
        self.assertEqual([id_ for id_, _ in rendered], [2])
        release.set()
        self.assertTrue(self.pump(lambda: not view._detail_worker_running))
        self.assertEqual([id_ for id_, _ in rendered], [2])

    def test_closed_panel_ignores_late_async_result(self):
        view, provider, rendered = self.view()
        entered = threading.Event()
        release = threading.Event()

        def read(identifier):
            entered.set()
            release.wait(timeout=2)
            return SimpleNamespace(id=identifier)

        provider.get_detail_by_id.side_effect = read
        view.show_achievement(8)
        self.assertTrue(entered.wait(timeout=2))
        view.close_detail_panel()
        release.set()
        self.assertTrue(self.pump(lambda: not view._detail_worker_running))
        self.assertEqual(rendered, [])
        self.assertFalse(view._detail_open)

    def test_failed_cold_detail_recovers_without_crashing_ui(self):
        view, provider, rendered = self.view()
        provider.get_detail_by_id.side_effect = RuntimeError("bad source")
        view.show_achievement(9)
        self.assertTrue(self.pump(lambda: not view._detail_worker_running))
        self.assertEqual(rendered, [])
        self.assertFalse(view._detail_open)


if __name__ == "__main__":
    unittest.main()
