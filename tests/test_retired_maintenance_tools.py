from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETIRED_MAINTENANCE_TOOLS = (
    "tools/audit_lot6_coverage.py",
    "tools/audit_lot6_forensic.py",
    "tools/audit_quest_images_fast.py",
    "tools/diagnose_quest_images.py",
    "tools/dump_worldmap_container.py",
    "tools/find_dofus_worldmaps.py",
    "tools/generate_missing_route_cards.py",
    "tools/match_worldmap_candidates.py",
    "tools/promote_verified_worldmaps.py",
    "tools/reconcile_guide_ultime_manifest_counts.py",
    "tools/repair_guides_full.py",
    "tools/validate_world_scan_panel.py",
)


class RetiredMaintenanceToolsTests(unittest.TestCase):
    def test_unconsumed_historical_entrypoints_stay_retired(self) -> None:
        restored = [path for path in RETIRED_MAINTENANCE_TOOLS if (ROOT / path).exists()]
        self.assertEqual(restored, [])


if __name__ == "__main__":
    unittest.main()
