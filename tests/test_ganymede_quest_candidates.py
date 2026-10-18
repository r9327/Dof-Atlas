from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_master_refs import INDEX
from tools.audit_ganymede_quest_candidates import (
    CROSSWALK, GUIDES_DIR, ROOT, audit_ganymede_quest_candidates,
)


class GanymedeQuestCandidateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = {
            "guides": [
                {"ganymede_guide_id": 2251, "listed_step_count": 2},
            ]
        }
        self.crosswalk = {
            "guides": [
                {
                    "ganymede_guide_id": 2251,
                    "atlas_guide_ids": ["guide_complet"],
                    "status": "metadata_only",
                    "quest_mapping_verified": False,
                    "route_parity_verified": False,
                }
            ]
        }
        self.atlas = {
            "id": "guide_complet",
            "sections": [
                {"steps": [
                    {"type": "quest", "entity_id": 1631},
                    {"type": "quest", "entity_id": 2000},
                ]}
            ]
        }
        self.source = {
            "schema_version": 1,
            "source": {
                "guide_id": 2251,
                "source_url": "https://ganymede-app.com/guides/2251",
                "page_count": 1,
                "steps_per_page": 50,
                "extraction_scope": "factual_link_occurrences_only",
                "editorial_text_imported": False,
            },
            "coverage": {
                "observed_steps": 2,
                "distinct_linked_guide_ids": 0,
                "linked_main_index_guide_ids": 0,
                "linked_outside_main_index_guide_ids": [],
                "step_guide_links": 0,
                "dofusdb_step_link_counts": {
                    "quest": 2, "dungeon": 0, "object": 0, "monster": 0,
                },
                "coordinate_mentions": 0,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [
                {
                    "source_step_number": number,
                    "source_page": 1,
                    "linked_guide_ids": [],
                    "external_dofusdb_ids": {
                        "quest": [quest_id], "dungeon": [],
                        "object": [], "monster": [],
                    },
                    "coordinate_mentions": [],
                }
                for number, quest_id in ((1, 1631), (2, 9999))
            ],
        }
        self._write()

    def _write(self) -> None:
        data = (
            (INDEX, self.index),
            (CROSSWALK, self.crosswalk),
            (GUIDES_DIR / "guide_complet.json", self.atlas),
            (GUIDES_DIR / "ganymede_master_observed_links.json", self.source),
        )
        for path, payload in data:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

    def test_numeric_equality_is_review_not_certification(self) -> None:
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])
        self.assertEqual(report["numeric_id_candidates_per_guide"], 1)
        self.assertEqual(report["certified_quest_mappings"], 0)
        self.assertEqual(report["certified_quest_objectives"], 0)
        row = report["guide_reports"][0]
        self.assertEqual(row["external_only_quest_ids"], [9999])
        self.assertEqual(row["atlas_only_quest_ids"], [2000])
        self.assertEqual(row["candidate_pairs"][0]["candidate_atlas_quest_id"], 1631)
        self.assertEqual(row["candidate_pairs"][0]["observed_source_steps"], [1])
        self.assertEqual(row["candidate_pairs"][0]["status"], "REVIEW_NUMERIC_ID_ONLY")
        self.assertFalse(row["candidate_pairs"][0]["quest_identity_confirmed"])
        self.assertFalse(row["candidate_pairs"][0]["required_objective_confirmed"])

    def test_unmapped_source_is_not_silently_added_to_atlas(self) -> None:
        self.crosswalk["guides"] = []
        self._write()
        report = audit_ganymede_quest_candidates(self.root)
        row = report["guide_reports"][0]
        self.assertEqual(row["mapping_state"], "GUIDE_UNMAPPED")
        self.assertEqual(row["numeric_id_candidate_count"], 0)
        self.assertEqual(row["external_only_quest_ids"], [1631, 9999])

    def test_invalid_atlas_quest_id_blocks_report(self) -> None:
        self.atlas["sections"][0]["steps"][0]["entity_id"] = "1631"
        self._write()
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_atlas_guide", [i["code"] for i in report["issues"]])

    def test_false_crosswalk_certification_blocks_report(self) -> None:
        self.crosswalk["guides"][0]["quest_mapping_verified"] = True
        self._write()
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("unproved_crosswalk", [i["code"] for i in report["issues"]])

    def test_invalid_source_step_blocks_report(self) -> None:
        self.source["steps"][1]["source_step_number"] = 3
        self._write()
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_source_snapshot", [i["code"] for i in report["issues"]])

    def test_repeated_quest_in_multiple_steps_deduplicates(self) -> None:
        self.source["steps"][1]["external_dofusdb_ids"]["quest"] = [1631]
        self.atlas["sections"][0]["steps"] = [
            {"type": "quest", "entity_id": 1631},
        ]
        self._write()
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["numeric_id_candidates_per_guide"], 1)
        self.assertEqual(
            report["guide_reports"][0]["candidate_pairs"][0]["observed_source_steps"],
            [1, 2],
        )

    def test_independent_named_evidence_remains_review_only(self) -> None:
        evidence = {
            "schema_version": 1,
            "source_guide_id": 2251,
            "atlas_guide_id": "guide_complet",
            "evidence_level": "NAMED_QUEST_CANDIDATES_ONLY",
            "quest_objectives_verified": False,
            "route_verified": False,
            "sources": {
                "dpln_quest_list": "https://www.dofuspourlesnoobs.com/example.html",
                "ganymede_guide": "https://ganymede-app.com/guides/2251",
            },
            "main_quests": [{
                "quest_id": 1631,
                "name": "Exemple de quête",
                "achievement_group": "Source",
                "dofusdb_url": "https://dofusdb.fr/fr/database/quest/1631",
                "identity_status": "REVIEW_TRIANGULATED_ID_NAME",
            }],
            "access_and_prerequisites": [],
        }
        output = self.root / GUIDES_DIR / "ganymede_dpln_example_evidence.json"
        output.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])
        self.assertEqual(report["triangulated_named_quest_candidates"], 1)
        self.assertEqual(report["certified_quest_mappings"], 0)
        row = report["guide_reports"][0]["candidate_pairs"][0]
        self.assertEqual(row["status"], "REVIEW_TRIANGULATED_SOURCES")
        self.assertEqual(row["independent_quest_name"], "Exemple de quête")
        self.assertFalse(row["quest_identity_confirmed"])
        self.assertFalse(row["required_objective_confirmed"])

        evidence["route_verified"] = True
        output.write_text(json.dumps(evidence), encoding="utf-8")
        bad = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(bad["status"], "FAIL")
        self.assertIn("invalid_independent_evidence", [i["code"] for i in bad["issues"]])

    def test_named_evidence_missing_link_fails_closed(self) -> None:
        evidence = {
            "schema_version": 1,
            "source_guide_id": 2251,
            "atlas_guide_id": "guide_complet",
            "evidence_level": "NAMED_QUEST_CANDIDATES_ONLY",
            "quest_objectives_verified": False,
            "route_verified": False,
            "sources": {
                "dpln_quest_list": "https://www.dofuspourlesnoobs.com/example.html",
                "ganymede_guide": "https://ganymede-app.com/guides/2251",
            },
            "main_quests": [{
                "quest_id": 90001, "name": "Quête non correspondante",
                "achievement_group": "Example",
                "dofusdb_url": "https://dofusdb.fr/fr/database/quest/90001",
                "identity_status": "REVIEW_TRIANGULATED_ID_NAME",
            }],
            "access_and_prerequisites": [],
        }
        output = self.root / GUIDES_DIR / "ganymede_dpln_example_evidence.json"
        output.write_text(json.dumps(evidence), encoding="utf-8")
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("evidence_quest_unresolved", [i["code"] for i in report["issues"]])
        self.assertEqual(report["certified_quest_mappings"], 0)

    def test_invalid_daily_timing_is_not_exploitable(self) -> None:
        evidence = {
            "schema_version": 1,
            "source_guide_id": 2251,
            "atlas_guide_id": "guide_complet",
            "evidence_level": "NAMED_QUEST_CANDIDATES_ONLY",
            "quest_objectives_verified": False,
            "route_verified": False,
            "sources": {
                "dpln_quest_list": "https://www.dofuspourlesnoobs.com/example.html",
                "ganymede_guide": "https://ganymede-app.com/guides/2251",
            },
            "main_quests": [{
                "quest_id": 1631, "name": "Exemple",
                "achievement_group": "Example",
                "dofusdb_url": "https://dofusdb.fr/fr/database/quest/1631",
                "identity_status": "REVIEW_TRIANGULATED_ID_NAME",
            }],
            "access_and_prerequisites": [],
            "timed_progression_evidence": {
                "requires_calendar_pages": 365,
                "max_offerings_per_day": 1,
                "reward_interval": "daily",
                "schedule_policy": "NON_BLOCKING_LONG_TERM_GOAL",
            },
        }
        out = self.root / GUIDES_DIR / "ganymede_dpln_time_evidence.json"
        out.write_text(json.dumps(evidence), encoding="utf-8")
        report = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])
        self.assertEqual(
            report["guide_reports"][0]["timed_progression_review"]["max_offerings_per_day"], 1
        )

        evidence["timed_progression_evidence"]["schedule_policy"] = "FORCE_WAIT"
        out.write_text(json.dumps(evidence), encoding="utf-8")
        bad = audit_ganymede_quest_candidates(self.root)
        self.assertEqual(bad["status"], "FAIL")
        self.assertIn("invalid_independent_evidence", [i["code"] for i in bad["issues"]])

    def test_repository_snapshots_are_discovery_not_gameplay_proof(self) -> None:
        report = audit_ganymede_quest_candidates(ROOT)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])
        self.assertGreaterEqual(report["guide_snapshots_checked"], 86)
        self.assertEqual(report["triangulated_named_quest_candidates"], 12)
        dolmanax = next(r for r in report["guide_reports"] if r["source_guide_id"] == 2248)
        self.assertEqual(dolmanax["triangulated_named_quest_candidates"], 1)
        self.assertEqual(
            dolmanax["timed_progression_review"]["requires_calendar_pages"], 365
        )
        self.assertEqual(
            dolmanax["timed_progression_review"]["schedule_policy"],
            "NON_BLOCKING_LONG_TERM_GOAL",
        )
        self.assertEqual(
            dolmanax["candidate_pairs"][0]["candidate_atlas_quest_id"], 954
        )
        cawotte = next(r for r in report["guide_reports"] if r["source_guide_id"] == 2205)
        self.assertEqual(cawotte["triangulated_named_quest_candidates"], 11)
        self.assertEqual(cawotte["numeric_id_candidate_count"] >= 11, True)
        self.assertEqual(
            {p["candidate_atlas_quest_id"] for p in cawotte["candidate_pairs"]
             if p["status"] == "REVIEW_TRIANGULATED_SOURCES"},
            set(range(833, 844)),
        )
        self.assertEqual(report["certified_quest_mappings"], 0)
        self.assertEqual(report["certified_quest_objectives"], 0)


if __name__ == "__main__":
    unittest.main()
