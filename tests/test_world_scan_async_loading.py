from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

import app.cartography.world_service as world_service_module
import app.ui.world_scan_panel as world_scan_module
from app.cartography.world_service import WorldService
from app.ui.world_scan_panel import WorldScanPanel


class _FakeWorldService:
    instances = []

    def __init__(self, *, initialize: bool = True) -> None:
        self.initialize = bool(initialize)
        self.view_calls = 0
        self.map_calls = 0
        self.link_calls = 0
        type(self).instances.append(self)

    def get_map_views(self):
        self.view_calls += 1
        return []

    def get_maps_for_view(self, _view_key):
        self.map_calls += 1
        return []

    def get_links_for_view(self, _view_key):
        self.link_calls += 1
        return []


class _FakeThread:
    created = []

    def __init__(self, *, target, name, daemon) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        type(self).created.append(self)

    def start(self) -> None:
        self.started = True


class WorldScanAsyncLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        _FakeWorldService.instances = []
        _FakeThread.created = []

    @staticmethod
    def _dispose_panel(panel: WorldScanPanel) -> None:
        panel.close()
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(panel, QEvent.DeferredDelete)

    def test_world_service_can_skip_constructor_init_without_changing_default(self) -> None:
        with patch.object(world_service_module.world_db, "init_db") as init_db:
            WorldService()
            self.assertEqual(init_db.call_count, 1)
            WorldService(initialize=False)
            self.assertEqual(init_db.call_count, 1)

    def test_panel_constructor_does_not_query_database(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            panel = WorldScanPanel()
            try:
                self.assertEqual(len(_FakeWorldService.instances), 1)
                service = _FakeWorldService.instances[0]
                self.assertFalse(service.initialize)
                self.assertEqual(service.view_calls, 0)
                self.assertEqual(service.map_calls, 0)
                self.assertEqual(service.link_calls, 0)
                self.assertTrue(panel._initial_load_pending)
            finally:
                self._dispose_panel(panel)

    def test_first_show_only_starts_worker_and_keeps_db_off_ui_thread(self) -> None:
        with (
            patch.object(world_scan_module, "WorldService", _FakeWorldService),
            patch.object(world_scan_module, "Thread", _FakeThread),
        ):
            panel = WorldScanPanel()
            try:
                service = _FakeWorldService.instances[0]
                panel.show()

                self.assertEqual(service.view_calls, 0)
                self.assertEqual(len(_FakeThread.created), 1)
                self.assertTrue(_FakeThread.created[0].started)
                self.assertEqual(_FakeThread.created[0].name, "DofusAtlasCartographyLoad")
                self.assertTrue(panel._load_in_flight)
                self.assertFalse(panel._initial_load_pending)
            finally:
                self._dispose_panel(panel)

    def test_rapid_view_requests_coalesce_to_latest_generation(self) -> None:
        with (
            patch.object(world_scan_module, "WorldService", _FakeWorldService),
            patch.object(world_scan_module, "Thread", _FakeThread),
        ):
            panel = WorldScanPanel()
            try:
                panel._initial_load_pending = False
                panel._queue_cartography_load(mode="view", view_key="a", push_history=True)
                panel._queue_cartography_load(mode="view", view_key="b", push_history=True)

                self.assertEqual(panel._load_generation, 2)
                self.assertEqual(len(_FakeThread.created), 1)
                self.assertEqual(panel._pending_load_request["view_key"], "b")

                panel._on_cartography_load_finished(1, {"mode": "view", "error": ""})

                self.assertEqual(len(_FakeThread.created), 2)
                self.assertTrue(_FakeThread.created[1].started)
                self.assertIsNone(panel._pending_load_request)
                self.assertTrue(panel._load_in_flight)
            finally:
                self._dispose_panel(panel)

    def test_stale_result_never_applies_over_newer_request(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            panel = WorldScanPanel()
            applied = []
            try:
                panel._initial_load_pending = False
                panel._load_generation = 2
                panel._load_in_flight = True
                panel._apply_cartography_payload = lambda payload: applied.append(payload)

                panel._on_cartography_load_finished(1, {"marker": "old"})

                self.assertEqual(applied, [])
            finally:
                self._dispose_panel(panel)

    def test_hidden_current_result_is_deferred_until_next_show(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            panel = WorldScanPanel()
            applied = []
            try:
                panel._initial_load_pending = False
                panel._load_generation = 1
                panel._load_in_flight = True
                panel._apply_cartography_payload = lambda payload: applied.append(payload)

                panel._on_cartography_load_finished(1, {"marker": "ready"})
                self.assertEqual(applied, [])
                self.assertIsNotNone(panel._deferred_load_result)

                panel.show()

                self.assertEqual(applied, [{"marker": "ready"}])
                self.assertIsNone(panel._deferred_load_result)
            finally:
                self._dispose_panel(panel)


if __name__ == "__main__":
    unittest.main()
