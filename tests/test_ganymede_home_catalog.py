"""Contracts for real Ganymède home entries and aligned additional categories."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.build_ganymede_home_catalog import (
    CATALOG, CROSSWALK, DESTINATION, GROUPS, INDEX, LAYOUT,
    build_home_catalog, render_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


class GanymedeHomeCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for source in (INDEX, CROSSWALK, CATALOG):
            target = self.root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / source).read_bytes())

    def edit(self, relative: Path, edit) -> None:
        path = self.root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        edit(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_all_95_real_guides_have_unique_source_ids(self) -> None:
        result = build_home_catalog(self.root)
        records = result["guides"]
        self.assertEqual(len(records), 95)
        self.assertEqual(len({x["ganymede_guide_id"] for x in records}), 95)
        self.assertEqual(sum(x["listed_source_step_count"] for x in records), 7705)
        self.assertEqual(sum(x["guide_count"] for x in result["groups"]), 95)
        self.assertEqual(len(GROUPS), 9)
        self.assertTrue(all(
            row["source_url"].endswith("/" + str(row["ganymede_guide_id"]))
            for row in records
        ))

    def test_existing_home_unchanged_below_uses_exact_two_column_rows(self) -> None:
        groups = build_home_catalog(self.root)["groups"]
        self.assertEqual(
            [(row["key"], row["placement"]) for row in groups],
            [
                ("optimized", "top_left"),
                ("alignments", "top_left"),
                ("dofus", "top_right"),
                ("dimensions", "below_left_1"),
                ("eliocalypse", "below_right_1"),
                ("regions", "below_left_2"),
                ("events", "below_right_2"),
                ("other", "below_left_3"),
                ("islands", "below_right_3"),
            ],
        )

    def test_metadata_only_never_becomes_fake_playable_guide(self) -> None:
        result = build_home_catalog(self.root)
        self.assertEqual(result["routes_certified"], 0)
        self.assertEqual(result["playable_claimed"], 0)
        self.assertTrue(all(
            row["source_status"] == "metadata_only"
            and row["playable"] is False
            and row["launch_enabled"] is False
            for row in result["guides"]
        ))
        # A crosswalk entry is a candidate identity, never route certification.
        mapped = [row for row in result["guides"] if row["atlas_guide_ids"]]
        self.assertTrue(mapped)
        self.assertTrue(all(not row["launch_enabled"] for row in mapped))

    def test_generated_catalog_matches_canonical_index(self) -> None:
        expected = render_catalog(build_home_catalog(ROOT))
        self.assertEqual((ROOT / DESTINATION).read_text(encoding="utf-8"), expected)

    def test_missing_guide_from_public_index_blocks_entire_catalog(self) -> None:
        self.edit(INDEX, lambda data: data["guides"].pop())
        with self.assertRaisesRegex(ValueError, "95-guide index"):
            build_home_catalog(self.root)

    def test_mislabeled_or_unverified_source_never_appears_playable(self) -> None:
        self.edit(INDEX, lambda data: data["guides"][0].update(status="complete"))
        with self.assertRaisesRegex(ValueError, "Untrusted"):
            build_home_catalog(self.root)

    def test_duplicate_guide_id_blocks_entire_catalog(self) -> None:
        self.edit(INDEX, lambda data: data["guides"][1].update(
            ganymede_guide_id=data["guides"][0]["ganymede_guide_id"]
        ))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_home_catalog(self.root)

    def test_crosswalk_cannot_link_to_an_invented_local_guide(self) -> None:
        self.edit(CROSSWALK, lambda data: data["guides"][0].update(
            atlas_guide_ids=["guide_qui_n_existe_pas"]
        ))
        with self.assertRaisesRegex(ValueError, "Nonexistent Atlas navigation targets"):
            build_home_catalog(self.root)

    def test_disabled_atlas_guide_is_not_a_valid_destination(self) -> None:
        self.edit(CATALOG, lambda data: data["guides"][0].update(enabled=False))
        with self.assertRaisesRegex(ValueError, "Nonexistent Atlas navigation targets"):
            build_home_catalog(self.root)

    def test_unknown_crosswalk_source_cannot_create_navigation(self) -> None:
        self.edit(CROSSWALK, lambda data: data["guides"][0].update(
            ganymede_guide_id=999999
        ))
        with self.assertRaisesRegex(ValueError, "Unknown"):
            build_home_catalog(self.root)

    def test_public_prerequisites_reject_orphan_and_self_cycle(self) -> None:
        self.edit(INDEX, lambda data: data["guides"][0].update(
            public_tree_prerequisite_guide_ids=[999999]
        ))
        with self.assertRaisesRegex(ValueError, "Invalid public prerequisite"):
            build_home_catalog(self.root)
        self.edit(INDEX, lambda data: data["guides"][0].update(
            public_tree_prerequisite_guide_ids=[2251]
        ))
        with self.assertRaisesRegex(ValueError, "Invalid public prerequisite"):
            build_home_catalog(self.root)


if __name__ == "__main__":
    unittest.main()
