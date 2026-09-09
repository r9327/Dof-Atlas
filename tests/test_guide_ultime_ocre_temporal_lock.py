from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_temporal_registry import load_temporal_registry


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeOcreTemporalLockTests(unittest.TestCase):
    def test_ocre_completion_depends_on_current_temporal_registry(self) -> None:
        route = json.loads((MANUAL / "ocre_completion_route_v2.json").read_text(encoding="utf-8"))
        self.assertIn("ocre_capture_registry_v1.json", route["depends_on"])
        self.assertIn("temporal_registry_v15.json", route["depends_on"])
        self.assertNotIn("temporal_registry_v13.json", route["depends_on"])
        self.assertTrue(any("temporal_registry_v15" in str(rule) for rule in route.get("rules", [])))

    def test_kralamoure_hook_exists_in_resolved_temporal_v15(self) -> None:
        route_v1 = json.loads((MANUAL / "ocre_completion_route_v1.json").read_text(encoding="utf-8"))
        stage = next(row for row in route_v1["stages"] if row.get("id") == "OCRE-F4")
        hook = str(stage.get("temporal_hook") or "")
        self.assertEqual(hook, "kralamoure_server_opening")

        registry = load_temporal_registry(MANUAL / "temporal_registry_v15.json")
        entries = {str(row.get("id") or ""): row for row in registry.get("entries", [])}
        self.assertIn(hook, entries)
        kralamoure = entries[hook]
        self.assertEqual(kralamoure.get("minimum_people_to_open"), 49)
        self.assertTrue(kralamoure.get("hard_wait_forbidden"))

    def test_ocre_alias_points_to_current_completion_route(self) -> None:
        alias = json.loads((MANUAL / "ocre_final_route_v2.json").read_text(encoding="utf-8"))
        self.assertEqual(alias.get("base_file"), "ocre_completion_route_v2.json")
        self.assertEqual(int(alias.get("stage_count") or 0), 5)


if __name__ == "__main__":
    unittest.main()
