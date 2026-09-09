from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_ultime_route_adapter import (
    GuideUltimeRouteAdapter,
    SENTINEL_COORD,
)
from tools import organize_guide_ultime_artifacts as organizer


class FakeCatalog:
    def __init__(self) -> None:
        self.by_id = {
            1: SimpleNamespace(
                id=1,
                name="Quête test",
                source_info={
                    "launch_position": {"position": "[4,-3]"},
                    "source_meta": {"startCoords": "[4,-3]", "zone": "Astrub"},
                },
                zones=("Astrub",),
            )
        }
        self.quests = tuple(self.by_id.values())
        self.loaded_from = None


class RouteSanitizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = GuideUltimeRouteAdapter(FakeCatalog(), SimpleNamespace(quest_ids=(1,)))

    def test_raw_map_sentinel_is_rejected_and_documentary_fallback_is_used(self):
        self.adapter.raw_maps = {
            123: {"id": 123, "posX": SENTINEL_COORD, "posY": SENTINEL_COORD}
        }
        location = self.adapter._location_from_map(
            123,
            {"x": 4, "y": -3},
            zone="Astrub",
        )
        self.assertEqual(location.map_id, 123)
        self.assertEqual((location.x, location.y), (4, -3))
        self.assertNotIn(str(SENTINEL_COORD), location.display())

    def test_map_id_zero_is_not_a_geographical_identity(self):
        self.adapter.raw_maps = {0: {"id": 0, "posX": 0, "posY": 0}}
        location = self.adapter._location_from_map(
            0,
            {"x": 10, "y": 16},
            zone="Astrub",
        )
        self.assertIsNone(location.map_id)
        self.assertEqual((location.x, location.y), (10, 16))

    def test_start_location_uses_documentary_coordinate_when_raw_map_is_sentinel(self):
        self.adapter.raw_quests = {1: {"id": 1, "startPosition": [{"mapId": 123}]}}
        self.adapter.raw_maps = {
            123: {"id": 123, "posX": SENTINEL_COORD, "posY": SENTINEL_COORD}
        }
        location = self.adapter._start_location(1)
        self.assertEqual(location.map_id, 123)
        self.assertEqual((location.x, location.y), (4, -3))


class ArtifactOrganizerTests(unittest.TestCase):
    def test_only_old_guide_ultime_files_are_archived_and_nothing_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            canonical = artifacts / "guide_ultime_final.json"
            old = artifacts / "guide_ultime_old_debug.json"
            unrelated = artifacts / "lot7_work.json"
            canonical.write_text("{}", encoding="utf-8")
            old.write_text("{}", encoding="utf-8")
            unrelated.write_text("{}", encoding="utf-8")

            with patch.object(organizer, "ROOT", root), patch.object(organizer, "ARTIFACTS", artifacts):
                result = organizer.organize(apply=True)

            self.assertTrue(canonical.exists())
            self.assertTrue(unrelated.exists())
            self.assertFalse(old.exists())
            self.assertEqual(result["archive_candidate_count"], 1)
            moved_to = root / result["moved"][0]["to"]
            self.assertTrue(moved_to.exists())
            self.assertTrue((moved_to.parent / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
