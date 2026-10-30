"""Doctor RAM inventory: provenance, object ownership and partial status."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from PySide6.QtCore import QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from tools.atlas_doctor_lib.ram_inventory import (
    ROUTE_CHECKPOINTS, ram_checkpoints_summary, ram_ownership_snapshot,
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
        finally:
            sub.deleteLater()
            quetes.deleteLater()
            world.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_summary_never_invents_rss_for_missing_or_unobserved_checkpoints(self):
        def checkpoint(name, rss, widgets):
            return {
                "label": name,
                "memory": {"tree_rss_mb": rss, "process_rss_mb": rss},
                "ownership": {
                    "status": "OBSERVED_PARTIAL", "qt": {"total_live_widgets": widgets},
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
        self.assertEqual(result["home_widget_count_delta"], 1)
        self.assertNotIn("bad", result["checkpoints"])
        self.assertNotIn("home_rss_delta_mib", ram_checkpoints_summary([]))

    def test_ram_checkpoints_are_bounded_not_per_widget_history(self):
        self.assertEqual(ROUTE_CHECKPOINTS,
                         {"organizer", "guide", "world_map", "crafts"})


if __name__ == "__main__":
    unittest.main()
