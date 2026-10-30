"""Doctor RAM inventory: provenance, object ownership and partial status."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PySide6.QtCore import QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from tools.atlas_doctor_lib.ram_inventory import (
    ROUTE_CHECKPOINTS, ram_checkpoints_summary, ram_ownership_snapshot,
    ram_scope_status,
)


class DoctorRamInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_qt_page_ownership_and_native_image_budget_are_observed(self):
        quetes = QWidget()
        sub = QFrame(quetes)
        world = QWidget()
        world.canvas = SimpleNamespace(pixmap=QPixmap(100, 50))
        world._image_suspended = True
        window = SimpleNamespace(
            page_widgets={"Quetes": quetes, "Scan Monde": world},
            page_factories={"Craft": lambda: None, "Equipement": lambda: None},
        )
        try:
            detail = ram_ownership_snapshot(window, "after_guide_home")
            self.assertEqual(detail["status"], "OBSERVED_PARTIAL")
            pages = {row["name"]: row["count"] for row in detail["qt"]["by_page"]}
            self.assertGreaterEqual(pages["Quetes"], 2)
            self.assertGreaterEqual(pages["Scan Monde"], 1)
            self.assertEqual(detail["page_lifecycle"]["Craft"]["state"], "LAZY")
            self.assertEqual(detail["page_lifecycle"]["Quetes"]["state"], "LOADED")
            self.assertEqual(
                detail["native_image_indicators"]["world_canvas"]["estimated_rgba_bytes"],
                100 * 50 * 4,
            )
            self.assertTrue(detail["native_image_indicators"]["world_canvas"]["image_suspended"])
            self.assertGreaterEqual(detail["native_image_indicators"]["qt_global_pixmap_cache_limit_kib"], 0)
            self.assertIn("cannot identify native RSS", " ".join(detail["limits"]))
            self.assertEqual(
                detail["loaded_application_modules"],
                sorted(detail["loaded_application_modules"]),
            )
            self.assertTrue(all(
                name == "app" or name.startswith("app.")
                for name in detail["loaded_application_modules"]
            ))
        finally:
            sub.deleteLater()
            quetes.deleteLater()
            world.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_success_worker_breakdown_is_read_without_loading_cold_provider(self):
        detail = {
            "thread": "MainThread",
            "total_ms": 5283.0,
            "synchronous_subprocess_ms": 5100.0,
            "decode_ms": 183.0,
            "subprocess_path_used": True,
        }
        class ExistingService:
            def __init__(self):
                self.calls = 0

            def peek_achievement_provider(self):
                self.calls += 1
                return SimpleNamespace(last_detail_breakdown_ms=detail)

        service = ExistingService()
        quetes = QWidget()
        quetes.service = service
        window = SimpleNamespace(
            page_widgets={"Quetes": quetes},
            page_factories={},
        )
        try:
            snapshot = ram_ownership_snapshot(window, "last_home")
            self.assertEqual(snapshot["last_success_detail_timing"], {
                "status": "OBSERVED", **detail,
            })
            self.assertEqual(service.calls, 1)
        finally:
            quetes.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_thread_handle_inventory_exposes_finished_owners_without_rss_guess(self):
        from threading import Thread

        page = QWidget()
        completed = Thread(target=lambda: None, name="atlas-done")
        completed.start()
        completed.join(timeout=2)
        self.assertFalse(completed.is_alive())
        page._runtime_threads = [completed]
        window = SimpleNamespace(
            page_widgets={"Quetes": page},
            page_factories={},
        )
        try:
            result = ram_ownership_snapshot(window, "last_home")
            self.assertEqual(result["runtime_thread_handles"]["Quetes"], {
                "retained_handles": 1, "active": 0, "inactive": 1,
            })
            self.assertNotIn("rss_bytes", result["runtime_thread_handles"]["Quetes"])
            self.assertIn("do not establish native memory attribution", " ".join(result["limits"]))
        finally:
            page.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_home_checkpoint_keeps_success_detail_subprocess_breakdown(self):
        snapshot = {
            "status": "OBSERVED_PARTIAL",
            "qt": {"total_live_widgets": 120},
            "last_success_detail_timing": {
                "status": "OBSERVED", "thread": "MainThread",
                "total_ms": 5080.0, "synchronous_subprocess_ms": 5000.0,
                "decode_ms": 80.0, "subprocess_path_used": True,
            },
        }
        report = ram_checkpoints_summary([{
            "label": "last_home",
            "memory": {"process_rss_mb": 105.0, "tree_rss_mb": 117.0},
            "ownership": snapshot,
        }])
        self.assertEqual(
            report["checkpoints"]["last_home"]["last_success_detail_timing"],
            snapshot["last_success_detail_timing"],
        )
        self.assertNotIn("home_rss_delta_mib", report)
        self.assertNotIn("home_inactive_thread_handle_delta", report)

    def test_home_summary_reports_thread_handles_without_inventing_rss(self):
        def checkpoint(label: str, finished: int):
            return {
                "label": label,
                "memory": {"process_rss_mb": 80.0, "tree_rss_mb": 100.0},
                "ownership": {
                    "status": "OBSERVED_PARTIAL",
                    "qt": {"total_live_widgets": 120},
                    "runtime_thread_handles": {
                        "Quetes": {
                            "retained_handles": finished,
                            "active": 0,
                            "inactive": finished,
                        },
                    },
                },
            }

        report = ram_checkpoints_summary([
            checkpoint("initial_home", 5),
            checkpoint("last_home", 1),
        ])
        self.assertEqual(report["home_inactive_thread_handle_delta"], -4)
        self.assertEqual(
            report["checkpoints"]["last_home"]["runtime_thread_handles_inactive"], 1
        )
        self.assertTrue(report["thread_counts_are_not_native_rss_attribution"])
        self.assertNotIn("home_private_commit_delta_mib", report)

    def test_summary_never_invents_rss_for_missing_or_unobserved_checkpoints(self):
        def checkpoint(name, rss, widgets):
            return {
                "label": name,
                "memory": {"tree_rss_mb": rss, "process_rss_mb": rss},
                "ownership": {
                    "status": "OBSERVED_PARTIAL", "qt": {"total_live_widgets": widgets},
                    "windows_process_private": {
                        "status": "OBSERVED", "private_commit_mib": rss + 5.0,
                    },
                },
            }

        result = ram_checkpoints_summary([
            checkpoint("initial_home", 80.0, 30),
            {"label": "bad", "memory": {"tree_rss_mb": 900},
             "ownership": {"status": "UNAVAILABLE"}},
            checkpoint("last_home", 105.25, 31),
        ])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["home_rss_delta_mib"], 25.25)
        self.assertEqual(result["home_private_commit_delta_mib"], 25.25)
        self.assertEqual(result["home_widget_count_delta"], 1)
        self.assertNotIn("bad", result["checkpoints"])
        self.assertNotIn("home_rss_delta_mib", ram_checkpoints_summary([]))

    def test_summary_identifies_new_imports_without_inventing_memory_attribution(self):
        def checkpoint(name, names):
            return {
                "label": name,
                "memory": {"tree_rss_mb": 90.0},
                "ownership": {
                    "status": "OBSERVED_PARTIAL",
                    "qt": {"total_live_widgets": 200},
                    "loaded_application_modules": names,
                },
            }
        report = ram_checkpoints_summary([
            checkpoint("initial_home", ["app", "app.main"]),
            checkpoint("last_home", ["app", "app.main", "app.services.craft", "app.ui.world"]),
        ])
        self.assertEqual(report["app_modules_imported_count"], 2)
        self.assertEqual(report["app_modules_imported_between_home_checkpoints"], [
            "app.services.craft", "app.ui.world",
        ])
        self.assertTrue(report["module_imports_are_not_native_rss_attribution"])
        self.assertNotIn("home_private_commit_delta_mib", report)

    def test_fifty_workstreams_have_exact_scope_and_partial_verdict(self):
        result = ram_scope_status()
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["workstreams_total"], 50)
        self.assertEqual(result["missing_ids"], [])
        self.assertGreater(result["not_instrumented"], 0)
        self.assertFalse(result["native_heap_attribution_confirmed"])
        self.assertFalse(result["real_windows_release_certified"])

    def test_scope_rejects_missing_and_duplicate_ids_without_false_complete(self):
        manifest = Path(__file__).resolve().parents[1] / (
            "docs/performance/atlas-ram-inventory-v1.json"
        )
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "scope.json"
            rows = json.loads(manifest.read_text(encoding="utf-8"))
            rows["workstreams"].pop()
            file.write_text(json.dumps(rows), encoding="utf-8")
            self.assertEqual(ram_scope_status(file)["status"], "BLOCKED")
            rows["workstreams"].append(dict(rows["workstreams"][-1]))
            file.write_text(json.dumps(rows), encoding="utf-8")
            self.assertEqual(ram_scope_status(file)["status"], "BLOCKED")

    def test_ram_checkpoints_are_bounded_not_per_widget_history(self):
        self.assertEqual(ROUTE_CHECKPOINTS,
                         {"organizer", "guide", "world_map", "crafts"})


if __name__ == "__main__":
    unittest.main()
