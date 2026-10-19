"""The canonical label overlay must not certify gameplay or corrupt source links."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.resolve_ganymede_action_labels import PATTERN, _french_name, render_labels, resolve_all


def candidate():
    return {
        "atlas_guide_id": "dofus_test", "source_guide_id": 9001,
        "source_step_count": 2,
        "steps": [
            {"source_step_number": 1, "stable_step_id": "ganymede_9001_step_0001",
             "review_status": "AUTO_EXTRACTED_NEEDS_REVIEW",
             "actions": [
                 {"kind": "prepare_object", "label": "Prévoir objet nº 17983 ×3",
                  "object_id": 17983, "quantity": 3},
                 {"kind": "quest_start", "label": "Démarrer quête nº 1732",
                  "quest_id": 1732},
                 {"kind": "guide_dependency", "label": "Guide nº 2204",
                  "guide_id": 2204},
                 {"kind": "talk", "label": "Parler à Sered"},
             ]},
            {"source_step_number": 2, "stable_step_id": "ganymede_9001_step_0002",
             "review_status": "AUTO_EXTRACTED_NEEDS_REVIEW",
             "actions": [
                 {"kind": "prepare_object", "label": "Prévoir objet nº 3 ×5",
                  "object_id": 3},
                 {"kind": "quest_finish", "label": "Terminer quête nº 1732",
                  "quest_id": 1732},
             ]},
        ],
    }


class GanymedeActionNameResolutionTests(unittest.TestCase):
    def test_untranslated_raw_name_is_not_misreported_as_french(self):
        self.assertEqual(_french_name({"name": "English fallback", "nameId": 12}, {}),
                         "")
        self.assertEqual(
            _french_name({"name": {"fr": "Nom français", "en": "English"}}, {}),
            "Nom français",
        )
        self.assertEqual(
            _french_name({"name": "English fallback", "nameId": 12},
                         {"12": "Nom français"}),
            "Nom français",
        )

    def test_numeric_pattern_only_matches_explicit_source_ids(self):
        self.assertIsNotNone(PATTERN.search("Prévoir objet nº 17983 ×3"))
        self.assertIsNotNone(PATTERN.search("Guide n° 2204"))
        self.assertIsNone(PATTERN.search("Rejoindre [14,22]"))
        self.assertIsNone(PATTERN.search("Récolter 5 plantes"))

    def test_pinned_names_yield_non_destructive_source_positioned_overrides(self):
        source = candidate()
        result = render_labels(source, {
            ("object", 17983): "Ressource confirmée",
            ("quest", 1732): "Une quête nommée",
            ("guide", 2204): "Chemin des Dofus",
        })
        self.assertEqual(result["generic_label_actions"], 5)
        self.assertEqual(result["resolved_action_labels"], 4)
        self.assertEqual(len(result["unresolved_references"]), 1)
        self.assertEqual(result["unresolved_references"][0]["external_id"], 3)
        overrides = result["label_overrides"]
        self.assertEqual([x["action_index"] for x in overrides], [0, 1, 2, 1])
        self.assertEqual(overrides[0]["display_label"], "Prévoir objet «Ressource confirmée» ×3")
        self.assertEqual(overrides[1]["display_label"], "Démarrer quête «Une quête nommée»")
        self.assertEqual(overrides[2]["display_label"], "Guide «Chemin des Dofus»")
        self.assertEqual(overrides[3]["display_label"], "Terminer quête «Une quête nommée»")
        self.assertTrue(all(x["canonical_objective_verified"] is False for x in overrides))
        self.assertEqual(source["steps"][0]["actions"][0]["label"],
                         "Prévoir objet nº 17983 ×3")

    def test_id_collision_does_not_guess_a_name(self):
        source = candidate()
        source["steps"][0]["actions"][0]["quest_id"] = 17983
        result = render_labels(source, {
            ("object", 17983): "Objet A",
            ("quest", 17983): "Quête B",
        })
        self.assertEqual(result["resolved_action_labels"], 0)
        self.assertEqual(result["unresolved_references"][0]["cause"],
                         "unlinked_or_ambiguous_id")

    def test_missing_entity_reference_is_not_resolved_from_unrelated_name(self):
        source = candidate()
        source["steps"][0]["actions"][0].pop("object_id")
        result = render_labels(source, {("object", 17983): "Objet A"})
        self.assertEqual(result["resolved_action_labels"], 0)
        self.assertEqual(result["unresolved_references"][0]["cause"],
                         "unlinked_or_ambiguous_id")

    def test_full_overlay_uses_localized_pinned_raw_and_rejects_stale_digest(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            raw = root / "raw"
            raw.mkdir()
            catalog = root / "data/encyclopedia/guides"
            catalog.mkdir(parents=True)
            for source_id in range(9001, 9021):
                data = {
                    "atlas_guide_id": f"dofus_{source_id}",
                    "source_guide_id": source_id, "source_step_count": 1,
                    "steps": [{
                        "source_step_number": 1,
                        "stable_step_id": f"ganymede_{source_id}_step_0001",
                        "review_status": "AUTO_EXTRACTED_NEEDS_REVIEW",
                        "actions": [{
                            "kind": "prepare_object",
                            "label": "Prévoir objet nº 17983 ×1",
                            "object_id": 17983, "quantity": 1,
                        }],
                    }],
                }
                (catalog / f"ganymede_{source_id}_action_candidates.json").write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
            items = raw / "items.json"
            lang = raw / "languages/fr.json"
            lang.parent.mkdir(parents=True)
            items.write_text(json.dumps({
                "RefIds": [{"data": {"id": 17983, "nameId": 500}}]
            }), encoding="utf-8")
            lang.write_text(json.dumps({
                "entries": {"500": "Ressource française"}
            }), encoding="utf-8")
            pinned = {}
            for key, path in (("items.json", items), ("languages/fr.json", lang)):
                data = path.read_bytes()
                pinned[key] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            fake_lock = {"tag": "test-pinned", "assets": pinned}
            valid = {"status": "AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW", "issues": []}
            with patch("tools.resolve_ganymede_action_labels.read_lock", return_value=fake_lock), \
                 patch("tools.resolve_ganymede_action_labels.audit_action_candidates",
                       return_value=valid):
                report = resolve_all(root, raw_dir=raw)
                self.assertEqual(report["status"], "REVIEW_NAMES_RESOLVED", report)
                self.assertEqual(report["resolved_action_labels"], 20)
                self.assertEqual(report["unresolved_reference_count"], 0)
                self.assertFalse(report["ready_to_replace"])
                self.assertEqual(
                    report["guides"][0]["label_overrides"][0]["display_label"],
                    "Prévoir objet «Ressource française» ×1",
                )
                items.write_text(items.read_text(encoding="utf-8") + " ",
                                 encoding="utf-8")
                blocked = resolve_all(root, raw_dir=raw)
                self.assertEqual(blocked["status"],
                                 "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE")
                self.assertIn("items.json", blocked["missing_or_stale_pinned_assets"])

    def test_identical_ids_in_two_stages_keep_both_occurrences(self):
        source = candidate()
        source["steps"][1]["actions"][0] = {
            "kind": "prepare_object", "label": "Prévoir objet nº 17983",
            "object_id": 17983,
        }
        result = render_labels(source, {("object", 17983): "Objet A"})
        self.assertEqual(result["resolved_action_labels"], 2)
        self.assertEqual([v["source_step_number"] for v in result["label_overrides"]],
                         [1, 2])


if __name__ == "__main__":
    unittest.main()
