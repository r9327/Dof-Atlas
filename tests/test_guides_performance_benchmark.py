"""Deterministic contracts for Guide navigation measurements in the canonical bench."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.tools import benchmark_guides_performance as perf


class _Selector:
    def __init__(self):
        self.index = 0
        self.options = {"dofus": 0, "islands": 1, "dimensions": 2, "alignements": 3}
        self.moves = []

    def findData(self, name):
        return self.options.get(name, -1)

    def currentIndex(self):
        return self.index

    def setCurrentIndex(self, index):
        self.index = index
        self.moves.append(index)


class _Dialog:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _GuideView:
    def __init__(self):
        self._runtime_ready = True
        self.category_selector = _Selector()
        self.ganymede_listings = [SimpleNamespace(source_id=2219)]
        self._ganymede_source_dialog = None
        self.opened = []

    def _open_source_by_id(self, source_id):
        self.opened.append(source_id)
        self._ganymede_source_dialog = _Dialog()


class _App:
    def processEvents(self):
        pass


class GuideCatalogBenchmarkContracts(unittest.TestCase):
    def test_navigation_report_samples_real_switches_and_restores_ui(self):
        view = _GuideView()
        with patch.object(
            perf, "current_encyclopedia_page",
            return_value=SimpleNamespace(guides_view=view),
        ), patch.object(
            perf, "current_rss_mb",
            side_effect=[120.0, 122.5, 123.0],
        ):
            result = perf.measure_guide_catalog_interactions(_App(), object())
        self.assertEqual(result["status"], "MEASURED")
        self.assertEqual(result["samples"], 16)
        self.assertEqual(result["catalog_rss_delta_mb"], 2.5)
        self.assertEqual(result["rss_after_offline_route_close_mb"], 123.0)
        self.assertEqual(view.category_selector.currentIndex(), 0)
        self.assertEqual(len(view.category_selector.moves), 17)
        self.assertEqual(view.opened, [2219])
        self.assertTrue(view._ganymede_source_dialog.closed)
        self.assertLessEqual(
            result["category_switch_p50_ms"], result["category_switch_p95_ms"],
        )
        self.assertLessEqual(
            result["category_switch_p95_ms"], result["category_switch_max_ms"],
        )

    def test_missing_catalog_has_explicit_not_available_status(self):
        with patch.object(
            perf, "current_encyclopedia_page",
            return_value=SimpleNamespace(guides_view=SimpleNamespace()),
        ):
            report = perf.measure_guide_catalog_interactions(_App(), object())
        self.assertEqual(report, {"status": "NOT_AVAILABLE"})


if __name__ == "__main__":
    unittest.main()
