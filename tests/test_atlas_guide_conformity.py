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
                       "text": "Parler au PNJ A", "dialogue_choice": "B"},
                      {"action_id": "get", "kind": "item", "text": "Prendre la ressource",
                       "items": [{"name": "Ressource", "quantity": 10}]},
                  ]},
                 {"source_step_id": "B", "title": "Étape B",
                  "actions": [{"action_id": "move", "kind": "travel",
                               "text": "Se déplacer", "coordinates": [13, 26]}]},
             ]},
            {"guide_id": 2220, "title": "Route beta",
             "steps": [{"source_step_id": "one", "title": "Départ",
                        "actions": [{"action_id": "fight", "kind": "combat",
                                     "text": "Combattre le monstre",
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

    def test_missing_whole_guide_enumerates_its_steps_and_actions(self) -> None:
        self.atlas["guides"].pop()
        report = compare(self.reference, self.atlas)
        paths = {(entry["issue_code"], entry["field_path"]) for entry in report["issues"]}
        self.assertIn(("MISSING_GUIDE", ".guides[2220]"), paths)
        self.assertIn(("MISSING_STEP", ".guides[2220].steps[one]"), paths)
        self.assertIn(("MISSING_ACTION", ".guides[2220].steps[one].actions[fight]"), paths)
        action = next(entry for entry in report["issues"]
                      if entry["issue_code"] == "MISSING_ACTION")
        self.assertEqual(action["guide_id"], "2220")
        self.assertEqual(action["source_step_id"], "one")
        self.assertEqual(action["action_id"], "fight")
        self.assertEqual(action["expected"]["monsters"][0]["quantity"], 3)
        self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")

    def test_missing_whole_step_enumerates_its_actions(self) -> None:
        self.atlas["guides"][0]["steps"].pop()
        report = compare(self.reference, self.atlas)
        codes = [entry["issue_code"] for entry in report["issues"]]
        self.assertIn("MISSING_STEP", codes)
        self.assertIn("MISSING_ACTION", codes)
        self.assertTrue(any(
            entry["source_step_id"] == "B" and entry["action_id"] == "move"
            for entry in report["issues"] if entry["issue_code"] == "MISSING_ACTION"
        ))

    def test_extra_whole_step_enumerates_its_actions(self) -> None:
        self.atlas["guides"][0]["steps"].append({
            "source_step_id": "invented", "title": "Fictitious step",
            "actions": [{"action_id": "invented_action", "kind": "talk", "npc": "Fiction"}],
        })
        report = compare(self.reference, self.atlas)
        paths = {(entry["issue_code"], entry["field_path"]) for entry in report["issues"]}
        self.assertIn(("EXTRA_STEP", ".guides[2219].steps[invented]"), paths)
        self.assertIn(("EXTRA_ACTION",
                       ".guides[2219].steps[invented].actions[invented_action]"), paths)
        self.assertFalse(report["certified"])

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

    def test_matching_empty_steps_and_actions_can_never_pass(self) -> None:
        for field in ("steps", "actions"):
            with self.subTest(missing_collection=field):
                source = reference()
                atlas = imported(source)
                if field == "steps":
                    source["guides"][0]["steps"] = []
                    atlas["guides"][0]["steps"] = []
                else:
                    source["guides"][0]["steps"][0]["actions"] = []
                    atlas["guides"][0]["steps"][0]["actions"] = []
                report = compare(source, atlas)
                self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")
                self.assertIn("UNVERIFIABLE", report["issue_codes"])

    def test_inventory_counts_missing_guide_contents(self) -> None:
        self.atlas["guides"].pop()
        report = compare(self.reference, self.atlas)
        self.assertEqual(report["coverage"]["reference_full_guides"], 2)
        self.assertEqual(report["coverage"]["atlas_full_guides"], 1)
        self.assertEqual(report["coverage"]["reference_full_steps"], 3)
        self.assertEqual(report["coverage"]["atlas_full_steps"], 2)
        self.assertEqual(report["coverage"]["reference_full_actions"], 4)
        self.assertEqual(report["coverage"]["atlas_full_actions"], 3)
        self.assertIn("MISSING_GUIDE", report["issue_codes"])

    def test_matching_invalid_action_kind_is_not_validated(self) -> None:
        source = reference()
        atlas = imported(source)
        source["guides"][0]["steps"][0]["actions"][0].pop("kind")
        atlas["guides"][0]["steps"][0]["actions"][0].pop("kind")
        report = compare(source, atlas)
        self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")
        self.assertIn("UNVERIFIABLE", report["issue_codes"])

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
        self.assertEqual(
            sorted(issue["field_path"] for issue in delta["introduced"]),
            [
                ".guides[2219].steps[B].actions[move].coordinates[0]",
                ".guides[2219].steps[B].actions[move].coordinates[1]",
            ],
        )
        self.assertEqual(len(delta["persistent"]), 0)
        self.assertEqual(delta["status"], "PARITY_CHECK_BLOCKED")
        self.assertFalse(delta["certified"])

    def test_persistent_mismatch_preserves_both_old_and_new_values(self) -> None:
        old = copy.deepcopy(self.atlas)
        new = copy.deepcopy(self.atlas)
        old["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = 8
        new["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = 9
        delta = before_after(self.reference, old, new)
        self.assertEqual(len(delta["persistent"]), 1)
        entry = delta["persistent"][0]
        self.assertTrue(entry["changed"])
        self.assertEqual(entry["before"]["expected"], 10)
        self.assertEqual(entry["before"]["actual"], 8)
        self.assertEqual(entry["after"]["actual"], 9)
        self.assertEqual(len(delta["introduced"]), 0)
        self.assertEqual(len(delta["resolved"]), 0)

    def test_long_values_are_not_truncated_in_machine_evidence(self) -> None:
        old = copy.deepcopy(self.atlas)
        original = "x" * 1000
        self.reference["guides"][0]["steps"][0]["title"] = original
        old["guides"][0]["steps"][0]["title"] = "wrong"
        result = compare(self.reference, old)
        issue = next(x for x in result["issues"] if x["field_path"].endswith(".title"))
        self.assertEqual(issue["expected"], original)
        self.assertEqual(issue["actual"], "wrong")

    def test_source_url_and_action_links_never_silently_disappear(self) -> None:
        self.reference["guides"][0]["steps"][0]["actions"][0]["source_url"] = (
            "https://example.invalid/verified/action"
        )
        result = compare(self.reference, self.atlas)
        self.assertIn("MISSING_FIELD", result["issue_codes"])
        self.assertTrue(any(
            x["field_path"].endswith(".source_url")
            and x["source_step_id"] == "A" and x["action_id"] == "talk"
            for x in result["issues"]
        ))

    def test_identical_invalid_declared_schema_version_never_passes(self) -> None:
        for bad in (True, None, "1", 2):
            with self.subTest(schema_version=bad):
                ref = copy.deepcopy(self.reference)
                atlas = copy.deepcopy(self.atlas)
                ref["schema_version"] = bad
                atlas["schema_version"] = bad
                result = compare(ref, atlas)
                self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
                self.assertIn("UNVERIFIABLE", result["issue_codes"])
                self.assertTrue(any(
                    issue["field_path"].endswith(".schema_version")
                    for issue in result["issues"]
                ))

    def test_root_metadata_and_schema_version_not_silently_ignored(self) -> None:
        self.reference["schema_version"] = 1
        self.atlas["schema_version"] = 2
        result = compare(self.reference, self.atlas)
        self.assertTrue(any(
            x["issue_code"] == "VALUE_MISMATCH"
            and x["field_path"].endswith("schema_version")
            for x in result["issues"]
        ))
        self.atlas["unexpected_root_field"] = "unverified"
        result = compare(self.reference, self.atlas)
        self.assertTrue(any(
            x["issue_code"] == "EXTRA_FIELD"
            and x["field_path"].endswith("unexpected_root_field")
            for x in result["issues"]
        ))

    def test_same_textual_id_with_wrong_type_never_passes(self) -> None:
        self.atlas["guides"][0]["steps"][0]["source_step_id"] = 123
        self.reference["guides"][0]["steps"][0]["source_step_id"] = "123"
        result = compare(self.reference, self.atlas)
        self.assertIn("TYPE_MISMATCH", result["issue_codes"])
        self.assertTrue(any(
            x["field_path"].endswith(".source_step_id")
            for x in result["issues"]
        ))

    def test_missing_entire_guides_key_expands_every_nested_loss(self) -> None:
        self.atlas.pop("guides")
        report = compare(self.reference, self.atlas)
        paths = {(issue["issue_code"], issue["field_path"])
                 for issue in report["issues"]}
        self.assertIn(("MISSING_FIELD", ".guides"), paths)
        self.assertIn(("MISSING_GUIDE", ".guides[2219]"), paths)
        self.assertIn(("MISSING_GUIDE", ".guides[2220]"), paths)
        self.assertIn(("MISSING_STEP", ".guides[2219].steps[A]"), paths)
        self.assertIn(("MISSING_ACTION",
                       ".guides[2219].steps[A].actions[talk]"), paths)
        self.assertEqual(report["coverage"]["reference_full_actions"], 4)
        self.assertEqual(report["coverage"]["atlas_full_actions"], 0)
        self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")

    def test_missing_entire_steps_key_expands_all_actions(self) -> None:
        self.atlas["guides"][0].pop("steps")
        report = compare(self.reference, self.atlas)
        codes = [issue["issue_code"] for issue in report["issues"]]
        self.assertIn("MISSING_FIELD", codes)
        self.assertIn("MISSING_STEP", codes)
        self.assertIn("MISSING_ACTION", codes)
        self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")

    def test_missing_entire_actions_key_expands_each_action(self) -> None:
        self.atlas["guides"][0]["steps"][0].pop("actions")
        report = compare(self.reference, self.atlas)
        action_ids = {issue["action_id"] for issue in report["issues"]
                      if issue["issue_code"] == "MISSING_ACTION"}
        self.assertEqual(action_ids, {"talk", "get"})
        self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")

    def test_extra_entire_actions_key_expands_each_action(self) -> None:
        self.reference["guides"][0]["steps"][0].pop("actions")
        report = compare(self.reference, self.atlas)
        self.assertEqual(
            {issue["action_id"] for issue in report["issues"]
             if issue["issue_code"] == "EXTRA_ACTION"},
            {"talk", "get"},
        )
        self.assertEqual(report["status"], "PARITY_CHECK_BLOCKED")

    def test_empty_optional_lists_match_adapter_contract(self) -> None:
        original = reference()
        atlas = imported(original)
        for source in (original, atlas):
            action = source["guides"][0]["steps"][0]["actions"][0]
            action["items"] = []
            action["monsters"] = []
        result = compare(original, atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_PASS")
        self.assertEqual(result["issue_count"], 0)
        self.assertFalse(result["certified"])

    def test_empty_required_items_remain_unverifiable(self) -> None:
        original = reference()
        atlas = imported(original)
        for source in (original, atlas):
            source["guides"][0]["steps"][0]["actions"][1]["items"] = []
        result = compare(original, atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertIn("UNVERIFIABLE", result["issue_codes"])

    def test_identical_missing_action_text_cannot_pass(self) -> None:
        for bad in (None, "", "   ", True):
            with self.subTest(value=bad):
                original = reference()
                atlas = imported(original)
                for data in (original, atlas):
                    action = data["guides"][0]["steps"][0]["actions"][0]
                    if bad is None:
                        action.pop("text")
                    else:
                        action["text"] = bad
                result = compare(original, atlas)
                self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
                self.assertTrue(any(
                    issue["issue_code"] == "UNVERIFIABLE"
                    and issue["field_path"].endswith(".text")
                    for issue in result["issues"]
                ))

    def test_identical_invalid_npc_name_cannot_pass(self) -> None:
        original = reference()
        atlas = imported(original)
        for data in (original, atlas):
            data["guides"][0]["steps"][0]["actions"][0]["npc"] = " "
        result = compare(original, atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertTrue(any(
            issue["issue_code"] == "UNVERIFIABLE"
            and issue["field_path"].endswith(".npc")
            for issue in result["issues"]
        ))

    def test_identical_unsupported_action_kind_is_not_parity(self) -> None:
        original = reference()
        atlas = imported(original)
        original["guides"][0]["steps"][0]["actions"][0]["kind"] = "invented"
        atlas["guides"][0]["steps"][0]["actions"][0]["kind"] = "invented"
        result = compare(original, atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertTrue(any(
            issue["field_path"].endswith(".kind")
            and issue["issue_code"] == "UNVERIFIABLE"
            for issue in result["issues"]
        ))

    def test_identical_invalid_coordinates_are_not_parity(self) -> None:
        for value in ([True, 2], [1.5, 2], [1], [10001, 0]):
            with self.subTest(value=value):
                original = reference()
                atlas = imported(original)
                original["guides"][0]["steps"][1]["actions"][0]["coordinates"] = value
                atlas["guides"][0]["steps"][1]["actions"][0]["coordinates"] = value
                result = compare(original, atlas)
                self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
                self.assertIn("UNVERIFIABLE", result["issue_codes"])

    def test_identical_missing_travel_position_is_not_parity(self) -> None:
        original = reference()
        atlas = imported(original)
        original["guides"][0]["steps"][1]["actions"][0].pop("coordinates")
        atlas["guides"][0]["steps"][1]["actions"][0].pop("coordinates")
        result = compare(original, atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertIn("UNVERIFIABLE", result["issue_codes"])

    def test_identical_wrong_item_quantity_is_not_parity(self) -> None:
        for invalid in (0, -1, True, "2"):
            with self.subTest(quantity=invalid):
                original = reference()
                atlas = imported(original)
                original["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = invalid
                atlas["guides"][0]["steps"][0]["actions"][1]["items"][0]["quantity"] = invalid
                result = compare(original, atlas)
                self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
                self.assertTrue(any(
                    issue["field_path"].endswith(".quantity")
                    and issue["issue_code"] == "UNVERIFIABLE"
                    for issue in result["issues"]
                ))

    def test_identical_combat_without_monsters_is_not_parity(self) -> None:
        original = reference()
        atlas = imported(original)
        original["guides"][1]["steps"][0]["actions"][0].pop("monsters")
        atlas["guides"][1]["steps"][0]["actions"][0].pop("monsters")
        result = compare(original, atlas)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertIn("UNVERIFIABLE", result["issue_codes"])

    def test_input_unchanged_and_deterministic(self) -> None:
        a = copy.deepcopy(self.reference)
        b = copy.deepcopy(self.atlas)
        self.assertEqual(compare(a, b), compare(a, b))
        compare(a, b)
        self.assertEqual(a, self.reference)
        self.assertEqual(b, self.atlas)

    def test_cli_never_overwrites_existing_audit_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (
                ("reference", self.reference),
                ("before", self.atlas),
                ("after", self.atlas),
            ):
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            output = root / "reports"
            output.mkdir()
            retained = output / "before.json"
            retained.write_text("PREVIOUS AUDIT", encoding="utf-8")
            argv = [
                "--reference", str(root / "reference.json"),
                "--before", str(root / "before.json"),
                "--after", str(root / "after.json"),
                "--output-dir", str(output),
            ]
            with self.assertRaises(SystemExit) as exc:
                main(argv)
            self.assertEqual(exc.exception.code, 2)
            self.assertEqual(retained.read_text(encoding="utf-8"), "PREVIOUS AUDIT")
            self.assertFalse((output / "after.json").exists())

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
            self.assertEqual(len(delta["resolved"]), 2)
            self.assertEqual(
                {entry["issue_code"] for entry in delta["resolved"]},
                {"MISSING_STEP", "MISSING_ACTION"},
            )

    def test_cli_rejects_case_variant_protected_report_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (("reference", self.reference),
                               ("before", self.atlas), ("after", self.atlas)):
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            output = root / "DATA" / "reports"
            args = ["--reference", str(root / "reference.json"),
                    "--before", str(root / "before.json"),
                    "--after", str(root / "after.json"),
                    "--output-dir", str(output)]
            with self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.parent.exists())

    def test_matching_whitespace_padded_identifiers_are_unverifiable(self) -> None:
        # Both copies used to compare as equal after an implicit .strip().
        for level in ("guide", "step", "action"):
            with self.subTest(level=level):
                original = reference()
                atlas = imported(original)
                if level == "guide":
                    original["guides"][0]["guide_id"] = " 2219 "
                    atlas["guides"][0]["guide_id"] = " 2219 "
                elif level == "step":
                    original["guides"][0]["steps"][0]["source_step_id"] = " A "
                    atlas["guides"][0]["steps"][0]["source_step_id"] = " A "
                else:
                    original["guides"][0]["steps"][0]["actions"][0]["action_id"] = " talk "
                    atlas["guides"][0]["steps"][0]["actions"][0]["action_id"] = " talk "
                result = compare(original, atlas)
                self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
                self.assertIn("UNVERIFIABLE", result["issue_codes"])
                self.assertFalse(result["certified"])

    def test_one_sided_source_id_whitespace_never_matches(self) -> None:
        changed = copy.deepcopy(self.atlas)
        changed["guides"][0]["steps"][0]["source_step_id"] = " A "
        result = compare(self.reference, changed)
        self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
        self.assertIn("UNVERIFIABLE", result["issue_codes"])
        self.assertIn("MISSING_STEP", result["issue_codes"])

    def test_invalid_id_grammar_blocks_identical_source_and_atlas(self) -> None:
        # Parity cannot pass a pair of unusable IDs just because both match.
        invalid_ids = ("bad id", "bad/id", "bad\\\\id", "é", "a" * 121, -1, True)
        for level in ("guide", "step", "action"):
            for invalid in invalid_ids:
                with self.subTest(level=level, invalid=invalid):
                    original = reference()
                    atlas = imported(original)
                    if level == "guide":
                        original["guides"][0]["guide_id"] = invalid
                        atlas["guides"][0]["guide_id"] = invalid
                    elif level == "step":
                        original["guides"][0]["steps"][0]["source_step_id"] = invalid
                        atlas["guides"][0]["steps"][0]["source_step_id"] = invalid
                    else:
                        original["guides"][0]["steps"][0]["actions"][0]["action_id"] = invalid
                        atlas["guides"][0]["steps"][0]["actions"][0]["action_id"] = invalid
                    result = compare(original, atlas)
                    self.assertEqual(result["status"], "PARITY_CHECK_BLOCKED")
                    self.assertIn("UNVERIFIABLE", result["issue_codes"])


if __name__ == "__main__":
    unittest.main()
