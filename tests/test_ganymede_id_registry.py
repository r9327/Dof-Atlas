from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.build_ganymede_id_registry import build_ganymede_id_registry
from tools.audit_ganymede_quest_candidates import CROSSWALK, GUIDES_DIR, INDEX


class GanymedeIdRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = {
            "guides": [{"ganymede_guide_id": 2251, "listed_step_count": 2}],
        }
        self.crosswalk = {"guides": [{
            "ganymede_guide_id": 2251,
            "atlas_guide_ids": ["local_guide"],
            "status": "metadata_only",
            "quest_mapping_verified": False,
            "route_parity_verified": False,
        }]}
        self.catalog = {"guides": [{
            "id": "local_guide", "file": "local_guide.json",
            "category": "dofus", "enabled": True,
        }]}
        self.guide = {
            "id": "local_guide", "completeness_status": "partial",
            "graph_semantics": {"Qf": "prerequisite_completed",
                                "Qa": "ordering_context_only",
                                "OR": "optional_alternatives"},
            "sections": [{"id": "chapter", "steps": [
                {"id": "q100", "type": "quest", "entity_id": 100,
                 "optional": True, "relation": "alternative",
                 "alternative_groups": ["quest:101:or:1"],
                 "prerequisites": [{"type": "quest", "entity_id": 101},
                                   {"type": "achievement", "entity_id": 300}]},
                {"id": "q101", "type": "quest", "entity_id": 101,
                 "optional": False, "prerequisites": []},
            ]}],
        }
        self.snapshot = {
            "schema_version": 1,
            "source": {
                "guide_id": 2251,
                "source_url": "https://ganymede-app.com/guides/2251",
                "page_count": 1, "steps_per_page": 50,
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
                    "quest": 2, "dungeon": 1, "object": 1, "monster": 1,
                },
                "coordinate_mentions": 0,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [
                {"source_step_number": 1, "source_page": 1,
                 "linked_guide_ids": [],
                 "external_dofusdb_ids": {
                     "quest": [100], "dungeon": [100],
                     "object": [100], "monster": [100],
                 }, "coordinate_mentions": []},
                {"source_step_number": 2, "source_page": 1,
                 "linked_guide_ids": [],
                 "external_dofusdb_ids": {
                     "quest": [101], "dungeon": [],
                     "object": [], "monster": [],
                 }, "coordinate_mentions": []},
            ],
        }
        self.evidence = {
            "schema_version": 1,
            "source_guide_id": 2251, "atlas_guide_id": "local_guide",
            "evidence_level": "NAMED_QUEST_CANDIDATES_ONLY",
            "quest_objectives_verified": False, "route_verified": False,
            "sources": {
                "dpln_quest_list": "https://www.dofuspourlesnoobs.com/example.html",
                "ganymede_guide": "https://ganymede-app.com/guides/2251",
            },
            "main_quests": [{
                "quest_id": 100, "name": "Quête principale",
                "achievement_group": "Succès",
                "dofusdb_url": "https://dofusdb.fr/fr/database/quest/100",
                "identity_status": "REVIEW_TRIANGULATED_ID_NAME",
            }],
            "access_and_prerequisites": [],
            "non_main_references": [],
            "preparation_evidence": {"resources": [{"name": "Une pierre", "quantity": 8}]},
        }
        self.write()

    def write(self) -> None:
        for p, value in [
            (INDEX, self.index), (CROSSWALK, self.crosswalk),
            (GUIDES_DIR / "catalog.json", self.catalog),
            (GUIDES_DIR / "local_guide.json", self.guide),
            (GUIDES_DIR / "ganymede_source_observed_links.json", self.snapshot),
            (GUIDES_DIR / "ganymede_dpln_test_evidence.json", self.evidence),
        ]:
            dest = self.root / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_typed_namespaces_prevent_id_collision(self) -> None:
        report = build_ganymede_id_registry(self.root)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])
        self.assertIn("100", report["quest_by_id"])
        for kind in ("object", "dungeon", "monster"):
            self.assertIn("100", report[f"{kind}_by_id"])
            self.assertEqual(report[f"{kind}_by_id"]["100"]["atlas_occurrences"], [])
        self.assertEqual(report["summary"]["distinct_quest_ids"], 2)

    def test_local_metadata_and_optional_or_are_preserved_not_required(self) -> None:
        report = build_ganymede_id_registry(self.root)
        row = report["quest_by_id"]["100"]
        occ = row["atlas_occurrences"][0]
        self.assertEqual(occ["atlas_guide_id"], "local_guide")
        self.assertTrue(occ["local_optional"])
        self.assertEqual(occ["local_relation"], "alternative")
        self.assertEqual(occ["local_alternative_groups"], ["quest:101:or:1"])
        self.assertEqual(
            occ["local_declared_prerequisites"],
            [{"type": "quest", "entity_id": 101},
             {"type": "achievement", "entity_id": 300}],
        )
        self.assertEqual(occ["source_confidence"], "ATLAS_GUIDE_UNVERIFIED_DECLARATION")
        self.assertEqual(report["atlas_guide_metadata"][0]["completeness_status"], "partial")
        self.assertEqual(report["certified_prerequisites"], 0)

    def test_source_occurrences_and_dpln_provenance_preserved(self) -> None:
        report = build_ganymede_id_registry(self.root)
        row = report["quest_by_id"]["100"]
        self.assertEqual(row["ganymede_occurrences"][0]["source_step"], 1)
        self.assertEqual(row["ganymede_occurrences"][0]["mapped_atlas_guide_hints"], ["local_guide"])
        self.assertEqual(row["dpln_evidence"][0]["source_role"], "DPLN_MAIN_REVIEW")
        self.assertFalse(row["dpln_evidence"][0]["local_quest_identity_certified"])
        self.assertEqual(report["summary"]["dpln_main_quest_ids_for_review"], 1)

    def test_source_global_preparation_not_assigned_to_individual_quests(self) -> None:
        report = build_ganymede_id_registry(self.root)
        preparation = report["guide_level_preparation_sources"][0]
        self.assertEqual(preparation["source_global_preparation"]["resources"][0]["quantity"], 8)
        self.assertFalse(preparation["ready_for_shopping_list"])
        self.assertFalse(preparation["per_character_quantities_verified"])
        self.assertNotIn("resources", report["quest_by_id"]["100"])

    def test_duplicate_atlas_quest_ids_in_two_steps_keep_both_occurrences(self) -> None:
        self.guide["sections"][0]["steps"].append({
            "id": "q100_second", "type": "quest", "entity_id": 100,
            "optional": False, "prerequisites": [],
        })
        self.write()
        report = build_ganymede_id_registry(self.root)
        self.assertEqual(len(report["quest_by_id"]["100"]["atlas_occurrences"]), 2)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])

    def test_invalid_local_prerequisite_fails_closed(self) -> None:
        self.guide["sections"][0]["steps"][0]["prerequisites"][0]["entity_id"] = "101"
        self.write()
        report = build_ganymede_id_registry(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("invalid_atlas_guide", [p["code"] for p in report["issues"]])
        self.assertEqual(report["certified_routes"], 0)

    def test_broken_source_is_not_rebranded_as_complete_registry(self) -> None:
        self.snapshot["steps"].pop()
        self.write()
        report = build_ganymede_id_registry(self.root)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["issues"][0]["code"], "upstream_invalid")

    def test_real_repository_indexes_both_95_and_local_26_guides(self) -> None:
        from tools.audit_ganymede_master_refs import ROOT
        report = build_ganymede_id_registry(ROOT)
        self.assertEqual(report["status"], "REVIEW_REQUIRED", report["issues"])
        self.assertEqual(report["summary"]["ganymede_guides"], 95)
        self.assertEqual(report["summary"]["atlas_guides"], 26)
        self.assertEqual(report["certified_routes"], 0)


if __name__ == "__main__":
    unittest.main()
