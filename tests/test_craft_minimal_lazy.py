from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main
from app.pages.craft_page import CraftPage


class CraftMinimalLazyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_deferred_constructor_builds_shell_without_loading_data(self) -> None:
        with (
            patch.object(CraftPage, "load_items") as load_items,
            patch.object(CraftPage, "load_leveling_guides") as load_guides,
            patch.object(CraftPage, "load_jobs") as load_jobs,
            patch.object(CraftPage, "load_selection") as load_selection,
        ):
            page = CraftPage(Mock(), defer_runtime=True)

        load_items.assert_not_called()
        load_guides.assert_not_called()
        load_jobs.assert_not_called()
        load_selection.assert_not_called()
        self.assertFalse(page._runtime_ready)
        self.assertEqual(page.results.count(), 1)
        page.deleteLater()

    def test_factory_returns_stable_craft_page_before_preload_finishes(self) -> None:
        captured = {}

        class Page:
            def __init__(self, _status_callback, **kwargs) -> None:
                captured.update(kwargs)

        shell = SimpleNamespace(
            preload_results={},
            start_preload=Mock(),
            set_status=Mock(),
        )
        with patch.object(main, "CraftPage", Page):
            page = main.AtlasWindow.create_craft_page(shell)

        self.assertIsInstance(page, Page)
        self.assertTrue(captured["defer_runtime"])
        shell.start_preload.assert_called_once_with(prefer_quests=False)

    def test_search_icons_are_materialized_in_small_batches(self) -> None:
        page = CraftPage(Mock(), defer_runtime=True)
        page._runtime_ready = True
        page.items = [
            {
                "name": f"Test {index}",
                "level": index,
                "type": "Ressource",
                "_search_name": f"test_{index}",
                "_craft_category": "equipment",
            }
            for index in range(20)
        ]
        page.search.setText("test")
        page.result_batch_timer.stop()

        page.refresh_results()
        page.result_batch_timer.stop()
        self.assertEqual(page.results.count(), 0)
        self.assertEqual(len(page._pending_result_items), 20)

        page._render_next_result_batch()
        page.result_batch_timer.stop()
        self.assertEqual(page.results.count(), 8)
        self.assertEqual(len(page._pending_result_items), 12)
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
