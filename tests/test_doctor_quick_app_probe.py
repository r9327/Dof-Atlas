"""Fast contracts for the short full-app Windows Qt navigation measurement."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.doctor_quick_app_probe import ROUTES, assert_inventory, open_route, summarize_revisits, run
from tools.atlas_doctor import command_perf
from tools.atlas_doctor_lib.parallel_app import validate_instance


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

    def test_full_campaign_bounds_fail_closed_without_starting_qt(self):
        with self.assertRaisesRegex(ValueError, "Unbounded"):
            run(output=Path("artifacts/quick_app/report.json"), cycles=11)
        with self.assertRaisesRegex(ValueError, "Unbounded"):
            run(output=Path("artifacts/quick_app/report.json"), cycles=10, idle_seconds=121)
        with self.assertRaisesRegex(ValueError, "Unbounded"):
            run(output=Path("artifacts/quick_app/report.json"), cycles=10, max_seconds=1900)

    def test_doctor_is_the_only_full_app_public_entrypoint(self):
        args = SimpleNamespace(
            app=True, deep=False, files_only=False, cycles=10,
            timeout=18.0, max_seconds=1200.0, idle_seconds=60.0,
            one_core=True, parallel_instances=1, output=Path("artifacts/quick_app/report.json"),
            json=True,
        )
        with patch("tools.doctor_quick_app_probe.run",
                   return_value={"status": "PASS", "measured_routes": 200}) as engine:
            result = command_perf(Path("/unused"), args)
        self.assertEqual(result["status"], "PASS")
        engine.assert_called_once_with(
            output=Path("/unused/artifacts/quick_app/report.json"),
            timeout=18.0, max_seconds=1200.0, cycles=10,
            idle_seconds=60.0, one_core=True,
        )
        args.deep = True
        with patch("tools.doctor_quick_app_probe.run") as engine:
            self.assertEqual(command_perf(Path("/unused"), args)["status"], "BLOCKED")
            engine.assert_not_called()


    def test_eight_processes_need_real_per_instance_coverage(self):
        samples = [
            {"id": key, "cycle": 1,
             "status": "PLACEHOLDER" if placeholder else "PASS",
             "home_stabilized": {"tree_rss_mb": 100.0}}
            for key, _group, _label, _page, placeholder in ROUTES
        ]
        good = {
            "git_head": "a" * 40, "status": "PASS", "cycles": 1,
            "planned_samples": 20, "measured_routes": 20,
            "functional_pass": 15, "placeholder_pass": 5,
            "preload_states": {"quests": "READY", "encyclopedia": "READY", "craft": "READY"},
            "routes": samples, "failed_routes": [],
            "peak_process_tree_rss_mib": 150.0,
        }
        self.assertEqual(validate_instance(good, sha="a" * 40), [])
        self.assertIn("WRONG_ROUTE_ORDER_DUPLICATE_OR_FALSE_STATUS",
                      validate_instance({**good, "routes": samples[:-1] + [samples[0]]},
                                        sha="a" * 40))
        self.assertIn("PRELOAD_NOT_READY", validate_instance(
            {**good, "preload_states": {"craft": "FAILED"}}, sha="a" * 40))
        self.assertIn("WRONG_COMMIT", validate_instance(good, sha="b" * 40))

    def test_doctor_routes_eight_real_processes_through_single_entrypoint(self):
        args = SimpleNamespace(
            app=True, deep=False, files_only=False, cycles=1,
            timeout=18.0, max_seconds=540.0, idle_seconds=0.0,
            one_core=False, parallel_instances=8,
            output=Path("artifacts/eight_atlas/summary.json"), json=True,
        )
        with patch("tools.atlas_doctor_lib.parallel_app.run_eight",
                   return_value={"status": "PASS", "instances": [object()] * 8}) as runner:
            result = command_perf(Path("/unused"), args)
        self.assertEqual(result["status"], "PASS")
        runner.assert_called_once_with(
            Path("/unused"), output=Path("/unused/artifacts/eight_atlas/summary.json"),
            max_seconds=540.0,
        )
        args.one_core = True
        with patch("tools.atlas_doctor_lib.parallel_app.run_eight") as runner:
            self.assertEqual(command_perf(Path("/unused"), args)["status"], "BLOCKED")
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
