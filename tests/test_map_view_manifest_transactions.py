from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cartography import map_view_manifest, world_db


def _manifest(*, views=None):
    return {"views": views if views is not None else [
        {
            "view_key": "world",
            "name": "World",
            "kind": "main_world",
            "min_x": -5, "max_x": 5,
            "min_y": -5, "max_y": 5,
            "maps": [{"x": 1, "y": 2, "map_id": "seed", "status": "unverified",
                      "rect": {"x": 10, "y": 10, "w": 5, "h": 5}}],
            "links": [{"target_view_key": "cave", "from_x": 1, "from_y": 2}],
        },
        {"view_key": "cave", "name": "Cave", "parent_view_key": "world",
         "maps": [], "links": []},
    ]}


class MapManifestTransactionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.previous_path = world_db.WORLD_DB_PATH
        self.previous_identity = world_db._INITIALIZED_DB_IDENTITY
        world_db.WORLD_DB_PATH = Path(self.temp.name) / "world.sqlite"
        world_db._INITIALIZED_DB_IDENTITY = ""
        self.manifest = Path(self.temp.name) / "manifest.json"

    def tearDown(self) -> None:
        world_db.WORLD_DB_PATH = self.previous_path
        world_db._INITIALIZED_DB_IDENTITY = self.previous_identity
        self.temp.cleanup()

    def _import(self, data: dict) -> dict:
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        return map_view_manifest.import_map_view_manifest(self.manifest)

    def test_reimport_preserves_current_scan_count_and_last_seen(self) -> None:
        data = _manifest()
        self.assertEqual(self._import(data)["errors"], [])
        world_db.set_current_map("world", 1, 2)
        current = next(row for row in world_db.get_maps_for_view("world")
                       if (row["x"], row["y"]) == (1, 2))
        before = (current["status"], current["scan_count"], current["last_seen_at"])
        self.assertEqual(before[0], "current")
        self.assertEqual(before[1], 1)
        data["views"][0]["maps"][0]["rect"]["w"] = 17
        self.assertEqual(self._import(data)["errors"], [])
        self.assertEqual(self._import(data)["errors"], [])
        after = world_db.get_maps_for_view("world")[0]
        self.assertEqual(
            (after["status"], after["scan_count"], after["last_seen_at"]), before
        )
        self.assertEqual(json.loads(after["rect_json"])["w"], 17)
        self.assertEqual(len(world_db.get_links_for_view("world")), 1)

    def test_missing_seed_map_retains_verified_player_history(self) -> None:
        self.assertEqual(self._import(_manifest())["errors"], [])
        world_db.mark_map_verified("world", 1, 2)
        changed = _manifest()
        changed["views"][0]["maps"] = []
        self.assertEqual(self._import(changed)["errors"], [])
        self.assertEqual(world_db.get_maps_for_view("world")[0]["status"], "verified")

    def test_mid_import_failure_rolls_back_all_geometry_and_links(self) -> None:
        self.assertEqual(self._import(_manifest())["errors"], [])
        original_views = [row["view_key"] for row in world_db.get_map_views()]
        original_links = world_db.get_links_for_view("world")
        updated = _manifest()
        updated["views"][0]["name"] = "Changed name"
        updated["views"].append({
            "view_key": "new_cave", "name": "New cave",
            "maps": [{"x": 9, "y": 9, "fail_import": True}],
        })
        original_encoder = world_db.encode_json

        def fail_on_marker(row):
            if isinstance(row, dict) and row.get("fail_import"):
                raise RuntimeError("test injected mid-transaction exception")
            return original_encoder(row)

        with patch.object(world_db, "encode_json", side_effect=fail_on_marker):
            result = self._import(updated)
        self.assertTrue(result["errors"])
        self.assertEqual([row["view_key"] for row in world_db.get_map_views()],
                         original_views)
        self.assertEqual(world_db.get_map_view("world")["name"], "World")
        self.assertEqual(world_db.get_map_view("new_cave"), None)
        self.assertEqual(world_db.get_links_for_view("world"), original_links)

    def test_references_duplicates_bounds_and_parent_cycles_rejected(self) -> None:
        valid = _manifest()
        self.assertEqual(map_view_manifest.validate_manifest(valid), [])
        missing = copy.deepcopy(valid)
        missing["views"][0]["links"][0]["target_view_key"] = "missing_target"
        self.assertTrue(map_view_manifest.validate_manifest(missing))
        self.assertEqual(self._import(missing)["views"], 0)
        self.assertFalse(world_db.WORLD_DB_PATH.exists())

        duplicate = copy.deepcopy(valid)
        duplicate["views"][0]["maps"].append(copy.deepcopy(duplicate["views"][0]["maps"][0]))
        self.assertTrue(any("doublon" in item for item in
                            map_view_manifest.validate_manifest(duplicate)))
        invalid = copy.deepcopy(valid)
        invalid["views"][0]["maps"][0]["x"] = 6
        self.assertTrue(any("hors limites" in item for item in
                            map_view_manifest.validate_manifest(invalid)))
        invalid["views"][0]["maps"][0]["x"] = 1.5
        self.assertTrue(any("entier" in item for item in
                            map_view_manifest.validate_manifest(invalid)))
        cycle = copy.deepcopy(valid)
        cycle["views"][0]["parent_view_key"] = "cave"
        self.assertTrue(any("Cycle" in item for item in
                            map_view_manifest.validate_manifest(cycle)))
        unknown_parent = copy.deepcopy(valid)
        unknown_parent["views"][1]["parent_view_key"] = "not_defined"
        self.assertTrue(any("absent" in item for item in
                            map_view_manifest.validate_manifest(unknown_parent)))
        explicit = copy.deepcopy(valid)
        explicit["views"][0]["links"][0]["target_view_key"] = "external_world"
        explicit["external_view_keys"] = ["external_world"]
        self.assertEqual(map_view_manifest.validate_manifest(explicit), [])

    def test_canonical_manifest_is_valid_when_present(self) -> None:
        source = map_view_manifest.MAP_VIEWS_PATH
        if not source.is_file():
            self.skipTest("Canonical map_views.json not mounted")
        data, errors = map_view_manifest.load_manifest(source)
        self.assertIsNotNone(data)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
