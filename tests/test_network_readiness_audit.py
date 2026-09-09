from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.deobfs_bundle import (
    DeobfuscationEvidenceBundleError,
    create_deobfuscation_evidence_bundle,
)
from app.network.discovery_evidence import (
    DiscoveryEvidenceCandidate,
    ProtocolDiscoveryConsensus,
)
from app.network.readiness_audit import audit_protocol_mapping_readiness


def report_text(rows: list[str]) -> str:
    return (
        "Message Matches Report\n"
        "======================\n\n"
        "Obf  →  Orig                  File          [conf:   0.00%]\n"
        "----------------------------------------------------------\n"
        + "\n".join(rows)
        + f"\n\nTotal matches: {len(rows)}\n"
    )


def consensus_payload(
    build_sha256: str,
    event_type: str,
    type_url: str,
    path: tuple[int, ...],
    kind: str,
) -> dict:
    return ProtocolDiscoveryConsensus(
        build_sha256=build_sha256,
        event_type=event_type,
        report_count=2,
        candidates=(
            DiscoveryEvidenceCandidate(
                type_url=type_url,
                path=path,
                kind=kind,
                supporting_report_count=2,
                total_matching_message_count=2,
            ),
        ),
        reason="single_consensus_candidate",
    ).to_dict()


class NetworkReadinessAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.build_sha256 = "a" * 64
        self.mapping_path = self.root / "candidate_mapping.json"
        self.character_consensus_path = self.root / "character_consensus.json"
        self.quest_consensus_path = self.root / "quest_consensus.json"
        self.enum_report_path = self.root / "enum_matches.txt"
        self.structure_report_path = self.root / "structure_matches.txt"
        self.bundle_path = self.root / "deobfs_bundle.json"

        self.mapping_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "game_version": "3.6.test",
                    "build_sha256": self.build_sha256,
                    "messages": {
                        "ankama.com/csel": {
                            "event_type": "character_identified",
                            "fields": [
                                {
                                    "output_name": "character_name",
                                    "path": [2, 1, 2, 1],
                                    "kind": "string",
                                    "required": True,
                                }
                            ],
                        },
                        "ankama.com/qval": {
                            "event_type": "quest_completed",
                            "fields": [
                                {
                                    "output_name": "quest_id",
                                    "path": [1],
                                    "kind": "positive_int",
                                    "required": True,
                                }
                            ],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        self.character_consensus_path.write_text(
            json.dumps(
                consensus_payload(
                    self.build_sha256,
                    "character_identified",
                    "ankama.com/csel",
                    (2, 1, 2, 1),
                    "string",
                )
            ),
            encoding="utf-8",
        )
        self.quest_consensus_path.write_text(
            json.dumps(
                consensus_payload(
                    self.build_sha256,
                    "quest_completed",
                    "ankama.com/qval",
                    (1,),
                    "positive_int",
                )
            ),
            encoding="utf-8",
        )
        self.enum_report_path.write_text(
            report_text(
                [
                    "csel  →  CharacterSelectionEvent   character_management.proto   [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.structure_report_path.write_text(
            report_text(
                [
                    "qval  →  QuestValidatedEvent       quest.proto                  [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.write_bundle()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_bundle(self, build_sha256: str | None = None) -> None:
        bundle = create_deobfuscation_evidence_bundle(
            build_sha256 or self.build_sha256,
            (self.enum_report_path, self.structure_report_path),
        )
        self.bundle_path.write_text(json.dumps(bundle.to_dict()), encoding="utf-8")

    def audit(self):
        return audit_protocol_mapping_readiness(
            self.mapping_path,
            (self.character_consensus_path, self.quest_consensus_path),
            self.bundle_path,
            (self.enum_report_path, self.structure_report_path),
        )

    def test_complete_independent_evidence_marks_candidate_ready_for_review(self) -> None:
        manifest, consensuses, validation = self.audit()
        self.assertEqual(manifest.build_sha256, self.build_sha256)
        self.assertEqual(len(consensuses), 2)
        self.assertTrue(validation.valid)
        self.assertEqual(validation.reason, "candidate_evidence_complete")
        self.assertTrue(validation.mapping_validation.valid)
        self.assertEqual(
            {row.event_type for row in validation.semantic_validations if row.valid},
            {"character_identified", "quest_completed"},
        )
        self.assertFalse(validation.to_dict()["authoritative_mapping"])

    def test_semantic_alias_mismatch_fails_closed_after_rebundling(self) -> None:
        self.structure_report_path.write_text(
            report_text(
                [
                    "qval  →  OtherEvent                other.proto                  [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.write_bundle()
        _manifest, _consensuses, validation = self.audit()
        self.assertFalse(validation.valid)
        self.assertEqual(validation.reason, "semantic_evidence_invalid")
        self.assertEqual(validation.invalid_semantic_events, ("quest_completed",))

    def test_report_modified_after_bundle_is_rejected_before_semantic_audit(self) -> None:
        self.structure_report_path.write_text(
            report_text(
                [
                    "qval  →  OtherEvent                other.proto                  [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        with self.assertRaises(DeobfuscationEvidenceBundleError):
            self.audit()

    def test_uncertain_alias_in_any_report_fails_closed_after_rebundling(self) -> None:
        self.enum_report_path.write_text(
            report_text(
                [
                    "csel  →  CharacterSelectionEvent   character_management.proto   [conf: 100.00%]",
                    "qval  →  ???                       ???                          [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.write_bundle()
        _manifest, _consensuses, validation = self.audit()
        self.assertFalse(validation.valid)
        self.assertEqual(validation.reason, "semantic_evidence_invalid")
        self.assertIn("quest_completed", validation.invalid_semantic_events)

    def test_mapping_field_path_mismatch_fails_before_semantic_readiness(self) -> None:
        mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        mapping["messages"]["ankama.com/qval"]["fields"][0]["path"] = [2]
        self.mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

        _manifest, _consensuses, validation = self.audit()
        self.assertFalse(validation.valid)
        self.assertEqual(validation.reason, "mapping_evidence_invalid")
        self.assertIn("quest_completed", validation.mapping_validation.mismatched_events)

    def test_bundle_from_different_build_is_rejected(self) -> None:
        self.write_bundle("b" * 64)
        with self.assertRaises(DeobfuscationEvidenceBundleError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
