from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.discovery_evidence import DiscoveryEvidenceCandidate, ProtocolDiscoveryConsensus, ProtocolDiscoveryEvidenceError
from app.network.mapping_audit import audit_mapping_evidence, audit_payload


def mapping_payload(build: str) -> dict:
    return {
        "schema_version": 1,
        "game_version": "3.6.test",
        "build_sha256": build,
        "messages": {
            "ankama.com/c": {
                "event_type": "character_identified",
                "fields": [
                    {
                        "output_name": "character_name",
                        "path": [5, 2],
                        "kind": "string",
                        "required": True,
                    }
                ],
            },
            "ankama.com/q": {
                "event_type": "quest_completed",
                "fields": [
                    {
                        "output_name": "quest_id",
                        "path": [3],
                        "kind": "positive_int",
                        "required": True,
                    }
                ],
            },
        },
    }


def consensus(build: str, event: str, type_url: str, path: tuple[int, ...], kind: str) -> dict:
    return ProtocolDiscoveryConsensus(
        build_sha256=build,
        event_type=event,
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


class NetworkMappingAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.build = "a" * 64
        self.mapping_path = self.root / "mapping.json"
        self.mapping_path.write_text(json.dumps(mapping_payload(self.build)), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_consensus(self, name: str, payload: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_mapping_matches_two_required_consensuses(self) -> None:
        character_path = self.write_consensus(
            "character.json",
            consensus(self.build, "character_identified", "ankama.com/c", (5, 2), "string"),
        )
        quest_path = self.write_consensus(
            "quest.json",
            consensus(self.build, "quest_completed", "ankama.com/q", (3,), "positive_int"),
        )
        manifest, consensuses, validation = audit_mapping_evidence(
            self.mapping_path,
            (character_path, quest_path),
        )
        self.assertTrue(validation.valid)
        payload = audit_payload(self.mapping_path, manifest, consensuses, validation)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["reason"], "mapping_evidence_match")
        self.assertEqual(payload["consensus_events"], ["character_identified", "quest_completed"])

    def test_missing_required_consensus_is_reported_without_installing_anything(self) -> None:
        character_path = self.write_consensus(
            "character.json",
            consensus(self.build, "character_identified", "ankama.com/c", (5, 2), "string"),
        )
        _manifest, _consensuses, validation = audit_mapping_evidence(
            self.mapping_path,
            (character_path,),
        )
        self.assertFalse(validation.valid)
        self.assertEqual(validation.reason, "mapping_evidence_missing")
        self.assertEqual(validation.missing_events, ("quest_completed",))

    def test_wrong_path_is_mismatch(self) -> None:
        character_path = self.write_consensus(
            "character.json",
            consensus(self.build, "character_identified", "ankama.com/c", (5, 2), "string"),
        )
        quest_path = self.write_consensus(
            "quest.json",
            consensus(self.build, "quest_completed", "ankama.com/q", (4,), "positive_int"),
        )
        _manifest, _consensuses, validation = audit_mapping_evidence(
            self.mapping_path,
            (character_path, quest_path),
        )
        self.assertFalse(validation.valid)
        self.assertEqual(validation.reason, "mapping_evidence_mismatch")
        self.assertIn("quest_completed", validation.mismatched_events)

    def test_tampered_consensus_is_rejected_before_audit(self) -> None:
        raw = consensus(self.build, "quest_completed", "ankama.com/q", (3,), "positive_int")
        raw["authoritative_mapping"] = True
        path = self.write_consensus("tampered.json", raw)
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            audit_mapping_evidence(self.mapping_path, (path,))


if __name__ == "__main__":
    unittest.main()
