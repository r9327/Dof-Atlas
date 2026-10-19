from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.audit_ganymede_master_refs import INDEX
from tools.audit_ganymede_prerequisites import (
    audit_ganymede_prerequisites, parse_start_criterion,
)


def mock_registry(*, valid: bool = True) -> dict:
    return {
        "status": "REVIEW_REQUIRED" if valid else "FAIL",
        "quest_by_id": {
            "100": {
                "atlas_occurrences": [{
                    "atlas_guide_id": "dofus_test",
                    "atlas_step_id": "q100",
                    "local_optional": True,
                    "local_relation": "alternative",
                    "local_alternative_groups": ["quest:100:or:1"],
                    "local_declared_prerequisites": [
                        {"type": "quest", "entity_id": 101},
                        {"type": "achievement", "entity_id": 300},
                    ],
                }],
            },
            "101": {"atlas_occurrences": []},
        },
    }


class ParseStartCriterionTests(unittest.TestCase):
    def test_and_or_parentheses_preserve_alternative_branches(self) -> None:
        parsed = parse_start_criterion("Qf=10&(Qa=20|Qf=30)")
        self.assertEqual(parsed["status"], "REVIEW_BRANCHES_PRESERVED")
        self.assertTrue(parsed["has_or"])
        branches = parsed["alternative_branches"]
        self.assertEqual(len(branches), 2)
        self.assertEqual([[atom["raw"] for atom in branch] for branch in branches],
                         [["Qf=10", "Qa=20"], ["Qf=10", "Qf=30"]])
        self.assertEqual(branches[0][0]["semantic"], "QUEST_COMPLETION_CONDITION_REVIEW")
        self.assertEqual(branches[0][1]["semantic"], "QUEST_ORDERING_CONTEXT_REVIEW")
        self.assertEqual(parsed["mandatory_quest_ids_inferred"], [])

    def test_or_before_and_is_not_flattened(self) -> None:
        parsed = parse_start_criterion("Qf=1|Qf=2&PL>49")
        self.assertEqual(
            [[atom["raw"] for atom in branch]
             for branch in parsed["alternative_branches"]],
            [["Qf=1"], ["Qf=2", "PL>49"]],
        )

    def test_unknown_conditions_preserved_not_dropped(self) -> None:
        parsed = parse_start_criterion("Qf=101&custom:flag")
        self.assertEqual(parsed["unknown_atoms"], ["custom:flag"])
        self.assertEqual(parsed["alternative_branches"][0][1]["semantic"],
                         "OPAQUE_UNINTERPRETED")

    def test_unbalanced_and_empty_branches_fail_closed(self) -> None:
        for value in ("(Qf=1|Qf=2", "Qf=1||Qf=2", "&Qf=1", "Qf=1&"):
            with self.subTest(criterion=value):
                report = parse_start_criterion(value)
                self.assertEqual(report["status"], "REVIEW_UNPARSED")

    def test_branch_expansion_is_capped(self) -> None:
        expression = "&".join("(Qf=1|Qf=2)" for _ in range(7))
        parsed = parse_start_criterion(expression)
        self.assertEqual(parsed["status"], "REVIEW_UNPARSED")
        self.assertIn("cap", parsed["reason"])

    def test_neutral_criterion_is_not_false_requirement(self) -> None:
        for value in ("", "BT=1"):
            with self.subTest(value=value):
                report = parse_start_criterion(value)
                self.assertEqual(report["status"], "REVIEW_NO_RESTRICTIVE_CRITERION")
                self.assertEqual(report["alternative_branches"], [[]])


class GanymedePrerequisiteAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw_path = self.root / "installed" / "quests.json"
        idx = self.root / INDEX
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps({
            "guides": [{
                "ganymede_guide_id": 2205,
                "public_tree_prerequisite_guide_ids": [2204],
            }],
        }), encoding="utf-8")

    def write_raw(self, criterion: str) -> None:
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text(json.dumps({
            "RefIds": [
                {"data": {"id": 100, "startCriterion": criterion}},
                {"data": {"id": 101, "startCriterion": "BT=1"}},
            ],
        }), encoding="utf-8")

    def audit(self, *, valid: bool = True) -> dict:
        with patch(
            "tools.audit_ganymede_prerequisites.build_ganymede_id_registry",
            return_value=mock_registry(valid=valid),
        ):
            return audit_ganymede_prerequisites(
                self.root, raw_quests_path=self.raw_path
            )

    def test_atlas_alternative_is_preserved_without_canonical_input(self) -> None:
        report = self.audit()
        self.assertEqual(report["status"], "REVIEW_ATLAS_ONLY_CANONICAL_UNAVAILABLE")
        entry = report["quest_by_id"]["100"]
        self.assertTrue(entry["atlas_declarations"][0]["local_optional"])
        self.assertFalse(entry["atlas_declarations"][0]["all_or_branches_mandatory"])
        self.assertEqual(entry["atlas_declarations"][0]["local_alternative_groups"],
                         ["quest:100:or:1"])
        self.assertEqual(entry["verified_required_quests"], [])
        self.assertIsNone(entry["satisfied_for_any_character"])
        self.assertEqual(report["certified_prerequisites"], 0)

    def test_raw_criteria_branches_are_distinct_from_atlas_declarations(self) -> None:
        self.write_raw("Qf=101&(Qa=55|PL>50)")
        report = self.audit()
        self.assertEqual(report["status"], "REVIEW_RAW_AND_ATLAS_PREREQUISITES")
        entry = report["quest_by_id"]["100"]
        self.assertEqual(len(entry["raw_criterion_review"]["alternative_branches"]), 2)
        self.assertEqual(entry["raw_start_criterion"], "Qf=101&(Qa=55|PL>50)")
        self.assertEqual(report["raw_criteria_with_or"], 1)
        self.assertEqual(entry["verified_required_achievements"], [])
        self.assertFalse(entry["prerequisites_certified"])
        self.assertEqual(report["certified_routes"], 0)

    def test_guide_level_dependency_not_assigned_to_every_quest(self) -> None:
        report = self.audit()
        meta = report["ganymede_guide_prerequisites"][0]
        self.assertEqual(meta["source_prerequisite_guide_ids"], [2204])
        self.assertTrue(meta["not_assigned_to_every_quest"])
        self.assertNotIn("source_prerequisite_guide_ids",
                         report["quest_by_id"]["100"])

    def test_missing_local_dependency_is_reported_without_inventing_quest(self) -> None:
        mock = mock_registry()
        del mock["quest_by_id"]["101"]
        with patch("tools.audit_ganymede_prerequisites.build_ganymede_id_registry",
                   return_value=mock):
            report = audit_ganymede_prerequisites(
                self.root, raw_quests_path=self.raw_path
            )
        self.assertEqual(report["unresolved_local_quest_references"][0]["unresolved_ref_id"],
                         101)
        self.assertEqual(report["certified_prerequisites"], 0)

    def test_bad_registry_blocks_all_proofs(self) -> None:
        report = self.audit(valid=False)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["issues"][0]["code"], "invalid_id_registry")
        self.assertEqual(report["certified_prerequisites"], 0)

    def test_canonical_unavailable_must_not_be_treated_as_satisfied(self) -> None:
        report = self.audit()
        self.assertFalse(report["raw_doduda_available"])
        self.assertEqual(report["quests_with_raw_criteria"], 0)
        self.assertEqual(report["quest_by_id"]["100"]["verified_required_quests"], [])

    def test_malformed_runtime_json_fails(self) -> None:
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text('{"RefIds":{"100":{"data":', encoding="utf-8")
        report = self.audit()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["issues"][0]["code"], "unreadable_canonical_quests")


if __name__ == "__main__":
    unittest.main()
