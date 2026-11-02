"""Adversarial tests for the standalone, read-only guide conformity comparator."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_guide_conformity import before_after, compare, main


def reference() -> dict:
    return {
        "reference_verified": True, "rights_verified": True, "complete": True,
        "guides": [
            {"guide_id": 2219, "title": "Route alpha", "evidence_ref": "approved:guide2219",
             "steps": [
                 {"source_step_id": "A", "title": "Étape A", "evidence_ref": "approved:A",
                  "actions": [
                      {"action_id": "talk", "kind": "talk", "npc": "PNJ A",
                       "dialogue_choice": "B"},
                      {"action_id": "get", "kind": "item",
                       "items": [{"name": "Ressource", "quantity": 10}]},
                  ]},
                 {"source_step_id": "B", "title": "Étape B",
                  "actions": [{"action_id": "move", "kind": "travel",
                               "coordinates": [13, 26]}]},
             ]},
            {"guide_id": 2220, "title": "Route beta",
             "steps": [{"source_step_id": "one", "title": "Départ",
                        "actions": [{"action_id": "fight", "kind": "combat",
                                     "monsters": [{"name": "Monstre", "quantity": 3}]}]}]},
        ],
    }


def imported(source: dict) -> dict:
    result = copy.deepcopy(source)
    result.pop("rights_verified")
    result.pop("reference_verified")
    result.pop("complete")
    for guide in result["guides"]:
        guide.pop("evidence_ref", None)
        for step in guide["steps"]:
            step.pop("evidence_ref", None)
    return result


class TestGuideConformity(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = reference()
        self.atlas = imported(self.reference)

    def _codes(self, actual: dict) -> list[str]:
        return [x["issue_code"] for x in compare(self.reference, actual)["issues"]]

    def test_exact_match_does_not_claim_gameplay_certificate(self) -> None:
        result = compare(self.reference, self.atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_PASS")
        self.assertEqual(result["issue_count"], 0)
        self.assertFalse(result["certified"])
        self.assertEqual(result["coverage"]["reference_guides"], 2)
        self.assertEqual(result["coverage"]["reference_steps"], 3)
        self.assertEqual(result["coverage"]["reference_actions"], 4)

    def test_missing_guide(self) -> None:
        self.atlas["guides"].pop()
        result = compare(self.reference, self.atlas)
        self.assertIn("MISSING_GUIDE", self._codes(self.atlas))
        self.assertTrue(any("guides[2220]" in issue["field_path"] for issue in result["issues"]))
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")

    def test_missing_step_and_action(self) -> None:
        self.atlas["guides"][0]["steps"].pop()
        self.atlas["guides"][0]["steps"][0]["actions"].pop(0)
        result = compare(self.reference, self.atlas)
        self.assertGreaterEqual(result["issue_count"], 2)
        self.assertIn("MISSING_STEP", self._codes(self.atlas))
        self.assertIn("MISSING_ACTION", self._codes(self.atlas))
        self.assertTrue(any("steps[B]" in x["field_path"] for x in result["issues"]))
        self.assertTrue(any("actions[talk]" in x["field_path"] for x in result["issues"]))

    def test_wrong_quantity_with_precise_expected_actual(self) -> None:
        self.atlas["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = 8
        result = compare(self.reference, self.atlas)
        wrong = [x for x in result["issues"] if x["issue_code"] == "VALUE_MISMATCH"]
        self.assertEqual(len(wrong), 1)
        self.assertEqual(wrong[0]["expected"], 10)
        self.assertEqual(wrong[0]["actual"], 8)
        self.assertEqual(wrong[0]["guide_id"], "2219")
        self.assertEqual(wrong[0]["source_step_id"], "A")
        self.assertEqual(wrong[0]["action_id"], "get")
        self.assertEqual(wrong[0]["source_evidence_ref"], "approved:A")

    def test_wrong_coordinates_and_order(self) -> None:
        steps = self.atlas["guides"][0]["steps"]
        steps[1]["actions"][0]["coordinates"] = [1, 2]
        steps.reverse()
        result = compare(self.reference, self.atlas)
        self.assertIn("ORDER_CHANGED", self._codes(self.atlas))
        self.assertTrue(any("coordinates" in x["field_path"] for x in result["issues"]))

    def test_duplicates_and_extra_actions_block(self) -> None:
        steps = self.atlas["guides"][0]["steps"]
        steps.append(copy.deepcopy(steps[1]))
        steps[0]["actions"].append({"action_id": "fake", "kind": "invented"})
        self.assertIn("DUPLICATE", self._codes(self.atlas))
        self.assertIn("EXTRA_ACTION", self._codes(self.atlas))

    def test_reference_without_provenance_never_passes(self) -> None:
        self.reference["rights_verified"] = False
        result = compare(self.reference, self.atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertIn("UNVERIFIABLE", self._codes(self.atlas))

    def test_reference_incomplete_never_passes(self) -> None:
        self.reference["complete"] = False
        self.assertIn("UNVERIFIABLE", self._codes(self.atlas))

    def test_wrong_type_never_passes(self) -> None:
        self.atlas["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = "10"
        self.assertIn("TYPE_MISMATCH", self._codes(self.atlas))

    def test_extra_guide_is_reported(self) -> None:
        self.atlas["guides"].append({"guide_id": 9999, "title": "Invented", "steps": []})
        self.assertTrue(any("guides[9999]" in x["field_path"]
                            for x in compare(self.reference, self.atlas)["issues"]))

    def test_before_after_reports_resolved_and_new(self) -> None:
        old = copy.deepcopy(self.atlas)
        old["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = 8
        new = copy.deepcopy(self.atlas)
        new["guides"][0]["steps"][1]["actions"][0]["coordinates"] = [0, 0]
        delta = before_after(self.reference, old, new)
        self.assertEqual(len(delta["resolved"]), 1)
        self.assertEqual(len(delta["introduced"]), 1)
        self.assertEqual(len(delta["persistent"]), 0)
        self.assertEqual(delta["status"], "PARITY_CHECK_BLOCKED")
        self.assertFalse(delta["certified"])

    def test_input_unchanged_and_deterministic(self) -> None:
        a = copy.deepcopy(self.reference)
        b = copy.deepcopy(self.atlas)
        self.assertEqual(compare(a, b), compare(a, b))
        compare(a, b)
        self.assertEqual(a, self.reference)
        self.assertEqual(b, self.atlas)

    def test_cli_exports_all_three_reports(self) -> None:
        before = copy.deepcopy(self.atlas)
        before["guides"][0]["steps"].pop()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (("reference", self.reference), ("before", before),
                               ("after", self.atlas)):
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            args = ["--reference", str(root / "reference.json"),
                    "--before", str(root / "before.json"),
                    "--after", str(root / "after.json"),
                    "--output-dir", str(root / "results")]
            self.assertEqual(main(args), 0)
            self.assertEqual(set(path.name for path in (root / "results").glob("*.json")),
                             {"before.json", "after.json", "before_after.json"})
            after_report = json.loads((root / "results" / "after.json").read_text())
            self.assertFalse(after_report["certified"])
            self.assertEqual(after_report["issue_count"], 0)
            delta = json.loads((root / "results" / "before_after.json").read_text())
            self.assertEqual(len(delta["resolved"]), 1)


if __name__ == "__main__":
    unittest.main()
