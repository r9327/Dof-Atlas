"""Fast contracts for the short full-app Windows Qt navigation measurement."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from tools.doctor_quick_app_probe import ROUTES, assert_inventory, open_route, summarize_revisits


class ShortWholeAppProbeTests(unittest.TestCase):
    def test_every_existing_visible_menu_route_is_in_the_inventory(self):
        self.assertEqual([r[0] for r in ROUTES], [
            "home", "organizer", "guide", "quests", "achievements",
            "dungeons", "monsters", "archmonsters", "wanted",
            "crafts", "world_map", "treasure_hunt", "ocre",
            "stuffs_pvm", "stuffs_pvp", "stuffs_builders",
            "almanax", "settings", "tutorials", "dofus_noob",
        ])
        assert_inventory()
        self.assertEqual([r[0] for r in ROUTES if r[4]], [
            "treasure_hunt", "ocre", "almanax", "tutorials", "dofus_noob",
        ])

    def test_new_unreviewed_category_cannot_be_silent(self):
        rows = list(ROUTES)
        rows[0] = ("home", "unreviewed", "Home", "Home", False)
        with self.assertRaises(ValueError):
            assert_inventory(tuple(rows))
        with self.assertRaises(ValueError):
            assert_inventory(tuple(ROUTES[:-1]))
        with self.assertRaises(ValueError):
            assert_inventory(ROUTES + (ROUTES[0],))

    def test_placeholders_do_not_count_as_real_app_features(self):
        class FakePage:
            def objectName(self):
                return "PlaceholderPage"

        app = Mock()
        window = Mock()
        window.active_page_name.return_value = "Placeholder::Ocre"
        window.page_widgets = {"Placeholder::Ocre": FakePage()}
        open_route(app, window, ROUTES[12], 1)
        window.open_tools_tab.assert_called_once_with("Ocre")
        window.show_placeholder.assert_not_called()

    def test_revisit_summary_uses_actual_stabilized_home_evidence(self):
        rows = [
            {"id": "guide", "cycle": 1, "status": "PASS", "open_ms": 400.0,
             "home_stabilized": {"tree_rss_mb": 96.5}},
            {"id": "guide", "cycle": 2, "status": "PASS", "open_ms": 275.0,
             "home_stabilized": {"tree_rss_mb": 99.0}},
            {"id": "guide", "cycle": 3, "status": "PASS", "open_ms": 250.0,
             "home_stabilized": {"tree_rss_mb": 101.0}},
            {"id": "crafts", "cycle": 1, "status": "FAIL", "open_ms": 1.0,
             "home_stabilized": {"tree_rss_mb": 99.0}},
        ]
        result = summarize_revisits(rows, 3)
        self.assertEqual(result["guide"]["cold_open_ms"], 400.0)
        self.assertEqual(result["guide"]["warm_open_ms"], 250.0)
        self.assertEqual(result["guide"]["warm_vs_cold_ms"], -150.0)
        self.assertEqual(result["guide"]["home_tree_delta_first_to_last_mib"], 4.5)
        self.assertNotIn("crafts", result)
        self.assertEqual(summarize_revisits(rows[:-1], 2), {})

    def test_placeholders_require_actual_placeholder_page(self):
        class FakePage:
            def objectName(self):
                return "RealModule"

        app = Mock()
        window = Mock()
        window.active_page_name.return_value = "Placeholder::Ocre"
        window.page_widgets = {"Placeholder::Ocre": FakePage()}
        with self.assertRaisesRegex(RuntimeError, "placeholder classification mismatch"):
            open_route(app, window, ROUTES[12], 1)

if __name__ == "__main__":
    unittest.main()
