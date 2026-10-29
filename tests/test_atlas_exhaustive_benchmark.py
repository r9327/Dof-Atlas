"""Contract tests for exhaustive Guide performance evidence."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from tools.benchmark_atlas_exhaustive import (
    ganymede_inventory, guide_visible, percentile, summarize_samples,
)


class ExhaustiveGuideBenchmarkTests(unittest.TestCase):
    def test_nearest_rank_percentiles_are_explicit(self):
        self.assertIsNone(percentile([], 95))
        self.assertEqual(percentile([10, 50, 20, 30], 50), 20)
        self.assertEqual(percentile([10, 50, 20, 30], 95), 50)
        self.assertEqual(percentile([10, 50, 20, 30], 99), 50)
        with self.assertRaises(ValueError):
            percentile([1], 120)

    def test_failed_guide_cannot_be_summarized_as_pass(self):
        samples = [
            {"guide_id": "g1", "title": "G1", "cycle": 1,
             "status": "PASS", "open_ms": 111,
             "open_ui": {"stall_250ms": 1}, "home_ui": {"stall_250ms": 2}},
            {"guide_id": "g2", "title": "G2", "cycle": 1,
             "status": "FAIL", "error": "Timeout"},
        ]
        summary = summarize_samples(samples)
        self.assertEqual(summary["planned"], 2)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["freeze_count_250ms"], 3)
        self.assertEqual(summary["slowest_guides"][0]["guide_id"], "g1")

    def test_selected_id_without_actual_view_is_not_complete(self):
        detail = object()
        stack = SimpleNamespace(currentWidget=lambda: detail)
        view = SimpleNamespace(_runtime_ready=True, current_guide_id="g1",
                               state="OVERVIEW", GUIDE_OVERVIEW="OVERVIEW", stack=stack, detail_page=detail)
        page = SimpleNamespace(guides_view=view, _pending_guide_id="")
        self.assertTrue(guide_visible(page, "g1"))
        self.assertFalse(guide_visible(page, "g2"))
        page._pending_guide_id = "g1"
        self.assertFalse(guide_visible(page, "g1"))
        page._pending_guide_id = ""
        view.stack = SimpleNamespace(currentWidget=lambda: None)
        self.assertFalse(guide_visible(page, "g1"))

    def test_optimized_manual_guide_requires_real_loaded_runtime(self):
        # Sylvestre uses SharedGuideManualView rather than the standard detail_page.
        manual = object()
        stack = SimpleNamespace(currentWidget=lambda: manual)
        service = SimpleNamespace(available=True, cards=[object()])
        view = SimpleNamespace(
            _runtime_ready=True, current_guide_id="dofus_sylvestre",
            state="OVERVIEW", GUIDE_OVERVIEW="OVERVIEW",
            stack=stack, detail_page=object(),
            _catalog_manual_views={"dofus_sylvestre": manual},
            _catalog_manual_services={"dofus_sylvestre": service},
        )
        page = SimpleNamespace(guides_view=view, _pending_guide_id="")
        self.assertTrue(guide_visible(page, "dofus_sylvestre"))
        service.cards = []
        self.assertFalse(guide_visible(page, "dofus_sylvestre"))
        service.cards = [object()]
        view.stack = SimpleNamespace(currentWidget=lambda: object())
        self.assertFalse(guide_visible(page, "dofus_sylvestre"))
        view.stack = stack
        service.available = False
        self.assertFalse(guide_visible(page, "dofus_sylvestre"))

    def test_metadata_only_ganymede_does_not_count_as_runnable(self):
        rows = ganymede_inventory({"dofus_argente"})
        from app.modules.encyclopedia.views.guide_library_sources import load_ganymede_listings
        self.assertEqual(len(rows), len(load_ganymede_listings()))
        mapped = next(x for x in rows if x["source_id"] == 2203)
        self.assertEqual(mapped["coverage"], "atlas_equivalent_benchmarked")
        unrelated = next(x for x in rows if x["source_id"] == 2251)
        self.assertEqual(unrelated["coverage"], "metadata_only_not_executable")
        self.assertTrue(all(x["coverage"] in {
            "atlas_equivalent_benchmarked", "metadata_only_not_executable",
        } for x in rows))


if __name__ == "__main__":
    unittest.main()
