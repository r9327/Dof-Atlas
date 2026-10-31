from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QImage, QPixmap
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

    def test_hidden_map_evicts_world_buttons_without_losing_view_selection(self) -> None:
        with (
            patch.object(world_scan_module, "WorldService", _FakeWorldService),
            patch.object(world_scan_module, "Thread", _FakeThread),
        ):
            panel = WorldScanPanel()
            try:
                panel._initial_load_pending = False
                panel.show()
                first = set(panel.world_buttons)
                self.assertTrue(first)
                panel.current_world_name = next(iter(first))
                panel.history = ["world-previous"]
                panel.hide()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                self.assertEqual(panel.world_buttons, {})
                self.assertTrue(panel._world_menu_suspended)
                self.assertEqual(panel.history, ["world-previous"])
                panel.show()
                self.assertEqual(set(panel.world_buttons), first)
                self.assertFalse(panel._world_menu_suspended)
                self.assertEqual(panel.history, ["world-previous"])
                self.assertEqual(panel.current_world_name, next(iter(first)))
            finally:
                self._dispose_panel(panel)

    def test_hidden_map_drops_native_pixels_but_keeps_selected_world(self) -> None:
        with (
            patch.object(world_scan_module, "WorldService", _FakeWorldService),
            patch.object(world_scan_module, "Thread", _FakeThread),
        ):
            panel = WorldScanPanel()
            try:
                panel._initial_load_pending = False
                panel.current_view_key = "world-a"
                panel.history = ["world-before"]
                panel.selected_map = {"x": 4, "y": 5}
                panel.show()
                pixels = QPixmap(1400, 880)
                pixels.fill()
                panel.canvas.set_view(
                    {"view_key": "world-a"}, pixels, [], [], "map.png", False
                )
                self.assertFalse(panel.canvas.pixmap.isNull())
                panel.hide()
                self.assertTrue(panel.canvas.pixmap.isNull())
                self.assertTrue(panel._image_suspended)
                self.assertEqual(panel.current_view_key, "world-a")
                self.assertEqual(panel.history, ["world-before"])
                self.assertEqual(panel.selected_map, {"x": 4, "y": 5})
                panel.show()
                self.assertEqual(len(_FakeThread.created), 1)
                self.assertTrue(panel._load_in_flight)
                self.assertFalse(panel._image_suspended)
                self.assertEqual(panel._pending_load_request, None)
                self.assertEqual(panel._load_generation, 1)
                self.assertEqual(panel.history, ["world-before"])
            finally:
                self._dispose_panel(panel)

    def test_home_snapshot_restores_world_history_and_selected_map_without_pixels(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            first = WorldScanPanel()
            second = WorldScanPanel()
            try:
                first.current_view_key = "world-astrub"
                first.current_world_name = "Astrub"
                first.history = ["previous-world"]
                first.selected_map = {"x": 12, "y": -4, "rich": ["not cached"]}
                state = first.export_lightweight_navigation_state()
                self.assertEqual(state, {
                    "view_key": "world-astrub",
                    "world_name": "Astrub",
                    "history": ("previous-world",),
                    "select_coord": (12, -4),
                })
                self.assertNotIn("maps", state)
                first.history.append("later")
                second.restore_navigation_state(state)
                self.assertEqual(second.history, ["previous-world"])
                self.assertEqual(second.current_view_key, "world-astrub")
                self.assertIsNone(second.selected_map)
                with patch.object(second, "_queue_cartography_load") as queue:
                    second.show()
                queue.assert_called_once_with(
                    mode="reload", view_key="world-astrub",
                    push_history=False, select_coord=(12, -4),
                )
                self.assertIsNone(second._restore_selected_coord)
            finally:
                self._dispose_panel(first)
                self._dispose_panel(second)

    def test_hidden_worker_completion_preserves_latest_selected_world_and_history(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            panel = WorldScanPanel()
            try:
                panel._initial_load_pending = False
                panel.current_view_key = "world-old"
                panel.current_world_name = "Astrub"
                panel.history = ["world-before"]
                panel.selected_map = {"x":4, "y":5}
                panel._load_generation = 3
                panel._load_in_flight = True
                image = QImage(1400, 880, QImage.Format_ARGB32)
                image.fill(0)
                panel._on_cartography_load_finished(3, {
                    "mode": "view",
                    "view_key": "world-new",
                    "view": {"view_key": "world-new"},
                    "world_name": "Frigost",
                    "push_history": True,
                    "select_coord": (7, 8),
                    "image": image,
                    "error": "",
                })
                self.assertTrue(panel._deferred_load_result[1]["image"].isNull())
                state = panel.export_lightweight_navigation_state()
                self.assertEqual(state, {
                    "view_key": "world-new",
                    "world_name": "Frigost",
                    "history": ("world-before", "world-old"),
                    "select_coord": (7, 8),
                })
                self.assertFalse(any(isinstance(v, QImage) for v in state.values()))
                with patch.object(panel, "_queue_cartography_load") as load:
                    panel.show()
                self.assertEqual(panel.current_view_key, "world-new")
                self.assertEqual(panel.current_world_name, "Frigost")
                self.assertEqual(panel.history, ["world-before", "world-old"])
                self.assertIsNone(panel.selected_map)
                load.assert_called_once_with(
                    mode="view", view_key="world-new", push_history=False,
                    select_coord=(7, 8),
                )
            finally:
                self._dispose_panel(panel)

    def test_failed_hidden_worker_is_not_silently_dropped_on_home(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            panel = WorldScanPanel()
            try:
                panel._load_generation = 2
                panel._load_in_flight = False
                panel._deferred_load_result = (2, {"error": "source missing"})
                self.assertIsNone(panel.export_lightweight_navigation_state())
                panel._image_suspended = True
                panel._initial_load_pending = False
                with patch.object(panel, "_queue_cartography_load"):
                    panel.show()
                self.assertIn("source missing", panel.status_label.text())
            finally:
                self._dispose_panel(panel)

    def test_active_cartography_worker_prevents_home_hibernation_snapshot(self) -> None:
        with patch.object(world_scan_module, "WorldService", _FakeWorldService):
            panel = WorldScanPanel()
            try:
                panel._load_in_flight = True
                self.assertIsNone(panel.export_lightweight_navigation_state())
                panel._load_in_flight = False
                panel._pending_load_request = {"generation": 9}
                self.assertIsNone(panel.export_lightweight_navigation_state())
                panel._pending_load_request = None
                self.assertIsInstance(panel.export_lightweight_navigation_state(), dict)
            finally:
                self._dispose_panel(panel)

    def test_background_map_result_does_not_retain_pixels_on_home(self) -> None:
        with (
            patch.object(world_scan_module, "WorldService", _FakeWorldService),
            patch.object(world_scan_module, "Thread", _FakeThread),
        ):
            panel = WorldScanPanel()
            try:
                panel._initial_load_pending = False
                panel._load_generation = 1
                panel._load_in_flight = True
                image = QImage(1400, 880, QImage.Format_ARGB32)
                image.fill(0)
                panel._on_cartography_load_finished(1, {
                    "mode": "view", "view_key": "world-b",
                    "image": image, "error": "",
                })
                self.assertIsNotNone(panel._deferred_load_result)
                self.assertTrue(panel._deferred_load_result[1]["image"].isNull())
                self.assertTrue(panel._image_suspended)
                panel.show()
                self.assertIsNone(panel._deferred_load_result)
                self.assertEqual(panel.current_view_key, "world-b")
                self.assertEqual(len(_FakeThread.created), 1)
                self.assertEqual(panel.history, [])
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
