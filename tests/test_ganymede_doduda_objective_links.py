from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.audit_ganymede_doduda_objective_links import (
    audit_ganymede_doduda_objective_links,
)


def candidate_summary(*, valid: bool = True) -> dict:
    return {
        "status": "REVIEW_REQUIRED" if valid else "FAIL",
        "guide_reports": [{
            "source_guide_id": 2205,
            "candidate_pairs": [{
                "status": "REVIEW_TRIANGULATED_SOURCES",
                "external_dofusdb_quest_id": 101,
                "observed_source_steps": [1, 5],
            }, {
                "status": "REVIEW_NUMERIC_ID_ONLY",
                "external_dofusdb_quest_id": 102,
                "observed_source_steps": [6],
            }],
        }],
    }


class GanymedeDodudaObjectiveLinkAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw_dir = self.root / "doduda"
        self.raw_dir.mkdir()
        self.quests = {
            "101": {"data": {
                "id": 101,
                "stepIds": {"Array": [401, 402]},
                "startCriterion": "Qf=99&PL>49",
            }},
        }
        self.steps = {
            "401": {"data": {"id": 401}},
            "402": {"data": {"id": 402}},
        }
        self.objectives = {
            "501": {"data": {
                "id": 501, "stepId": 401, "typeId": 6,
                "parameters": {"parameter0": 10},
            }},
            "502": {"data": {
                "id": 502, "stepId": 402, "typeId": 7,
            }},
        }
        self._write()

    def _write(self) -> None:
        for name, data in (
            ("quests.json", self.quests),
            ("quest_steps.json", self.steps),
            ("quest_objectives.json", self.objectives),
        ):
            (self.raw_dir / name).write_text(
                json.dumps({"RefIds": data}), encoding="utf-8"
            )

    def _audit(self, *, valid: bool = True) -> dict:
        with patch(
            "tools.audit_ganymede_doduda_objective_links.audit_ganymede_quest_candidates",
            return_value=candidate_summary(valid=valid),
        ):
            return audit_ganymede_doduda_objective_links(
                self.root, raw_dir=self.raw_dir
            )

    def test_raw_ids_are_only_structure_not_gameplay_proof(self) -> None:
        report = self._audit()
        self.assertEqual(report["status"], "PASS_RAW_STRUCTURE_ONLY", report["issues"])
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["reviewed_candidates"], 1)
        self.assertEqual(report["incomplete_structure_candidates"], 0)
        quest = report["structure_reviews"][0]
        self.assertEqual(quest["canonical_start_criterion_uninterpreted"], "Qf=99&PL>49")
        self.assertEqual(quest["canonical_quest_step_ids"], [401, 402])
        self.assertEqual(
            [step["raw_objective_ids"] for step in quest["step_reviews"]],
            [[501], [502]],
        )
        self.assertEqual(
            [step["raw_combat_type_ids"] for step in quest["step_reviews"]],
            [[6], [7]],
        )
        self.assertFalse(quest["mandatory_order_confirmed"])
        self.assertFalse(quest["quest_actions_confirmed"])
        self.assertFalse(quest["item_quantities_confirmed"])
        self.assertEqual(report["certified_quest_objectives"], 0)
        self.assertEqual(report["certified_prerequisites"], 0)
        self.assertEqual(report["certified_routes"], 0)

    def test_missing_canonical_installation_is_blocked_not_accepted(self) -> None:
        (self.raw_dir / "quest_steps.json").unlink()
        report = self._audit()
        self.assertEqual(report["status"], "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE")
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(len(report["missing_files"]), 1)
        self.assertEqual(report["certified_quest_objectives"], 0)

    def test_missing_objective_id_is_review_not_success(self) -> None:
        self.objectives.pop("502")
        self._write()
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_RAW_STRUCTURE_GAPS", report["issues"])
        self.assertEqual(report["incomplete_structure_candidates"], 1)
        self.assertEqual(report["structure_reviews"][0]["step_reviews"][1]["raw_objective_count"], 0)
        self.assertEqual(report["certified_quest_objectives"], 0)

    def test_missing_step_record_is_review_not_success(self) -> None:
        self.steps.pop("402")
        self._write()
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_RAW_STRUCTURE_GAPS", report["issues"])
        self.assertFalse(
            report["structure_reviews"][0]["step_reviews"][1]["raw_step_record_present"]
        )

    def test_invalid_step_reference_is_not_accepted(self) -> None:
        self.quests["101"]["data"]["stepIds"]["Array"] = [401, True]
        self._write()
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_RAW_STRUCTURE_GAPS", report["issues"])
        self.assertEqual(report["structure_reviews"][0]["canonical_quest_step_ids"], [401, None])

    def test_invalid_canonical_objective_row_is_review(self) -> None:
        self.objectives["501"]["data"]["typeId"] = None
        self._write()
        report = self._audit()
        self.assertEqual(report["status"], "REVIEW_RAW_STRUCTURE_GAPS", report["issues"])
        self.assertEqual(
            report["structure_reviews"][0]["step_reviews"][0]["unresolved_objective_rows"],
            1,
        )

    def test_source_candidates_must_be_validated_first(self) -> None:
        report = self._audit(valid=False)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["issues"][0]["code"], "unvalidated_source_candidates")
        self.assertEqual(report["certified_routes"], 0)

    def test_malformed_canonical_json_does_not_claim_success(self) -> None:
        (self.raw_dir / "quest_steps.json").write_text(
            '{"RefIds":{"401":{"data":', encoding="utf-8"
        )
        report = self._audit()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["issues"][0]["code"], "canonical_data_unreadable")

    def test_unsupported_extra_numeric_link_does_not_become_mandatory(self) -> None:
        report = self._audit()
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["structure_reviews"][0]["quest_id"], 101)


if __name__ == "__main__":
    unittest.main()
