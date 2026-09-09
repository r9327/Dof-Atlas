from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    MANUAL_DIR,
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_generated_service import GuideUltimeGeneratedService


class GuideUltimeLazyFallbackTests(unittest.TestCase):
    def test_manual_route_can_open_without_reading_invalid_generated_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            invalid_route = tmp_path / "guide_ultime_gps_route.json"
            invalid_final = tmp_path / "guide_ultime_final.json"
            invalid_route.write_text("{ definitely not json", encoding="utf-8")
            invalid_final.write_text("{ definitely not json", encoding="utf-8")

            service = GuideUltimeManualRuntimeService(
                object(),
                object(),
                object(),
                manual_dir=MANUAL_DIR,
                route_path=invalid_route,
                final_path=invalid_final,
                autoload=False,
            )

            self.assertTrue(service.manual_manifest_active)
            self.assertTrue(service.available)
            self.assertGreater(len(service.cards), 0)
            self.assertEqual(
                service.route.get("source"),
                "data/routes/guide_ultime_manual/manifest_v1.json",
            )

    def test_generated_service_still_autoloads_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            route = tmp_path / "guide_ultime_gps_route.json"
            final = tmp_path / "guide_ultime_final.json"
            route.write_text(
                '{"schema_version": 5, "steps": [{"index": 1}]}',
                encoding="utf-8",
            )
            final.write_text("{}", encoding="utf-8")

            service = GuideUltimeGeneratedService(
                object(),
                object(),
                object(),
                route_path=route,
                final_path=final,
            )

            self.assertTrue(service.available)
            self.assertEqual(len(service.cards), 1)

    def test_generated_service_can_explicitly_defer_then_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            route = tmp_path / "guide_ultime_gps_route.json"
            final = tmp_path / "guide_ultime_final.json"
            route.write_text(
                '{"schema_version": 5, "steps": [{"index": 1}]}',
                encoding="utf-8",
            )
            final.write_text("{}", encoding="utf-8")

            service = GuideUltimeGeneratedService(
                object(),
                object(),
                object(),
                route_path=route,
                final_path=final,
                autoload=False,
            )
            self.assertFalse(service.available)
            self.assertEqual(service.cards, [])

            service.load()
            self.assertTrue(service.available)
            self.assertEqual(len(service.cards), 1)


if __name__ == "__main__":
    unittest.main()
