"""CLI source inventory is signed, read-only, and explicit."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from tools.audit_ganymede_start_correspondences import (
    GUIDES, GuideUltimeRouteAdapter, main, signed_source_quest_ids,
)


class GanymedeStartReviewCliTests(unittest.TestCase):
    def test_real_source_quest_ids_are_unique_sorted_and_strict(self):
        ids = signed_source_quest_ids(GUIDES, ("dofus_cawotte",))
        self.assertEqual(ids, tuple(sorted(set(ids))))
        self.assertIn(836, ids)
        self.assertIn(845, ids)
        with self.assertRaisesRegex(ValueError, "Untrusted signed guide"):
            signed_source_quest_ids(GUIDES, ("not_a_real_guide",))

    def test_start_review_adapter_rejects_missing_game_map_coordinates(self):
        # Both read-only CLIs now share this sentinel-aware adapter.
        adapter = GuideUltimeRouteAdapter.__new__(GuideUltimeRouteAdapter)
        adapter.raw_maps = {
            123: {"id": 123, "posX": -(2**31), "posY": -18},
            124: {"id": 124, "posX": 5, "posY": -18},
        }
        unavailable = adapter._location_from_map(123, None, zone="")
        self.assertIsNone(unavailable.x)
        self.assertIsNone(unavailable.y)
        self.assertEqual(adapter._location_from_map(124, None, zone="").x, 5)

    def test_cli_writes_only_explicit_review_output(self):
        example = {
            "status": "REVIEW_ONLY_NO_AUTOMATIC_TRAVEL",
            "runtime_verified_travel_plans": {},
            "ready_for_automatic_travel": False,
        }
        with TemporaryDirectory() as temp:
            target = Path(temp) / "review" / "summary.json"
            with patch("tools.audit_ganymede_start_correspondences.build_review_report",
                       return_value=example) as build:
                self.assertEqual(main(["--guide", "dofus_cawotte",
                                       "--output", str(target)]), 0)
            self.assertEqual(build.call_args.kwargs["guide_ids"], ("dofus_cawotte",))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), example)

    def test_missing_snapshot_does_not_generate_false_success(self):
        from tools.audit_ganymede_start_correspondences import build_review_report
        with TemporaryDirectory() as temp:
            with self.assertRaises((FileNotFoundError, ValueError, OSError)):
                build_review_report(raw_data_dir=Path(temp),
                                    guide_ids=("dofus_cawotte",))


if __name__ == "__main__":
    unittest.main()
