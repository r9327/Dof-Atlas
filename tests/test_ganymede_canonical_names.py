from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_canonical_names import audit_ganymede_canonical_names
from tools.audit_ganymede_quest_candidates import CROSSWALK, GUIDES_DIR, INDEX


class GanymedeCanonicalNameReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.quests_path = self.root / "doduda" / "quests.json"
        self.language_path = self.root / "doduda" / "languages/fr.json"
        self.index = {"guides": [{"ganymede_guide_id": 2205, "listed_step_count": 1}]}
        self.mapping = {"guides": [{
            "ganymede_guide_id": 2205, "atlas_guide_ids": ["dofus_cawotte"],
            "status": "metadata_only", "quest_mapping_verified": False,
            "route_parity_verified": False,
        }]}
        self.atlas = {
            "id": "dofus_cawotte",
            "sections": [{"steps": [{"type": "quest", "entity_id": 100}]}],
        }
        self.external = {
            "schema_version": 1,
            "source": {
                "guide_id": 2205,
                "source_url": "https://ganymede-app.com/guides/2205",
                "page_count": 1, "steps_per_page": 50,
                "extraction_scope": "factual_link_occurrences_only",
                "editorial_text_imported": False,
            },
            "coverage": {
                "observed_steps": 1,
                "distinct_linked_guide_ids": 0,
                "linked_main_index_guide_ids": 0,
                "linked_outside_main_index_guide_ids": [],
                "step_guide_links": 0,
                "dofusdb_step_link_counts": {
                    "quest": 1, "dungeon": 0, "object": 0, "monster": 0,
                },
                "coordinate_mentions": 0,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [{
                "source_step_number": 1, "source_page": 1,
                "linked_guide_ids": [],
                "external_dofusdb_ids": {
                    "quest": [100], "dungeon": [], "object": [], "monster": [],
                },
                "coordinate_mentions": [],
            }],
        }
        self.evidence = {
            "schema_version": 1, "source_guide_id": 2205,
            "atlas_guide_id": "dofus_cawotte",
            "evidence_level": "NAMED_QUEST_CANDIDATES_ONLY",
            "quest_objectives_verified": False, "route_verified": False,
            "sources": {
                "dpln_quest_list": "https://www.dofuspourlesnoobs.com/example.html",
                "ganymede_guide": "https://ganymede-app.com/guides/2205",
            },
            "main_quests": [{
                "quest_id": 100, "name": "Le voyage",
                "achievement_group": "Groupe de quêtes",
                "dofusdb_url": "https://dofusdb.fr/fr/database/quest/100",
                "identity_status": "REVIEW_TRIANGULATED_ID_NAME",
            }],
            "access_and_prerequisites": [],
        }
        self._write_fixtures()
        self._write_canonical("Le voyage")

    def _write(self, path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def _write_fixtures(self) -> None:
        for path, value in (
            (INDEX, self.index),
            (CROSSWALK, self.mapping),
            (GUIDES_DIR / "dofus_cawotte.json", self.atlas),
            (GUIDES_DIR / "ganymede_cawotte_observed_links.json", self.external),
            (GUIDES_DIR / "ganymede_dpln_example_evidence.json", self.evidence),
        ):
            self._write(self.root / path, value)

    def _write_canonical(self, name: str | None, *, row_id: int = 100) -> None:
        self._write(self.quests_path, {
            "RefIds": {"100": {"data": {"id": row_id, "nameId": 300}}}
        })
        self._write(self.language_path, {
            "entries": {"300": name} if name is not None else {}
        })

    def _audit(self) -> dict:
        return audit_ganymede_canonical_names(
            self.root, raw_quests_path=self.quests_path,
            french_language_path=self.language_path,
        )

    def test_same_localized_name_is_only_corroboration(self) -> None:
        report = self._audit()
        self.assertEqual(report["status"], "PASS_CANONICAL_NAMES_ONLY", report["issues"])
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["matching_names"], 1)
        self.assertEqual(report["review_name_variants"], 0)
        self.assertEqual(report["certified_quest_objectives"], 0)
        self.assertEqual(report["certified_routes"], 0)
        self.assertFalse(report["reviews"][0]["candidate_identity_confirmed"])
        self.assertFalse(report["reviews"][0]["required_quest_objectives_confirmed"])

    def test_name_difference_requires_review(self) -> None:
        self._write_canonical("Le voyage changé")
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_CANONICAL_NAME_GAPS")
        self.assertEqual(report["review_name_variants"], 1)
        self.assertEqual(
            report["reviews"][0]["status"], "REVIEW_CANONICAL_NAME_VARIANT"
        )
        self.assertEqual(report["reviews"][0]["canonical_quest_name"], "Le voyage changé")

    def test_incomplete_localization_does_not_become_empty_evidence(self) -> None:
        self._write_canonical(None)
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_CANONICAL_NAME_GAPS")
        self.assertEqual(report["missing_quest_or_name"], 1)
        self.assertEqual(
            report["reviews"][0]["status"], "REVIEW_FRENCH_LOCALIZATION_MISSING"
        )

    def test_mismatched_raw_row_id_rejected(self) -> None:
        self._write_canonical("Le voyage", row_id=101)
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_CANONICAL_NAME_GAPS")
        self.assertEqual(
            report["reviews"][0]["status"],
            "REVIEW_CANONICAL_QUEST_MISSING_OR_WRONG_ID",
        )

    def test_missing_quest_source_is_blocked_not_certified(self) -> None:
        self.quests_path.unlink()
        report = self._audit()
        self.assertEqual(report["status"], "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE")
        self.assertIsNone(report["verified_names"])
        self.assertEqual(report["certified_routes"], 0)

    def test_upstream_invalid_snapshots_cannot_be_used(self) -> None:
        self.external["steps"][0]["source_step_number"] = 2
        self._write_fixtures()
        report = self._audit()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "unvalidated_candidates", [issue["code"] for issue in report["issues"]]
        )
        self.assertEqual(report["certified_quest_objectives"], 0)


if __name__ == "__main__":
    unittest.main()
