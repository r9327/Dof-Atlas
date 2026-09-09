from __future__ import annotations

import unittest

from app.network.discovery_evidence import (
    DiscoveryEvidenceCandidate,
    ProtocolDiscoveryConsensus,
)
from app.network.mapped_decoder import ProtocolFieldRule, ProtocolMessageRule
from app.network.mapping_evidence import validate_mapping_against_consensus
from app.network.mapping_manifest import ProtocolMappingManifest


def consensus(build: str, event: str, type_url: str, path: tuple[int, ...], kind: str):
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
    )


def manifest(build: str = "a" * 64) -> ProtocolMappingManifest:
    return ProtocolMappingManifest(
        game_version="3.6.test",
        build_sha256=build,
        rules={
            "ankama.com/c": ProtocolMessageRule(
                event_type="character_identified",
                fields=(
                    ProtocolFieldRule(
                        output_name="character_name",
                        path=(5, 2),
                        kind="string",
                        required=True,
                    ),
                ),
            ),
            "ankama.com/q": ProtocolMessageRule(
                event_type="quest_completed",
                fields=(
                    ProtocolFieldRule(
                        output_name="quest_id",
                        path=(3,),
                        kind="positive_int",
                        required=True,
                    ),
                ),
            ),
        },
    )


class NetworkMappingEvidenceTests(unittest.TestCase):
    def test_required_consensus_matches_manifest(self) -> None:
        build = "a" * 64
        result = validate_mapping_against_consensus(
            manifest(build),
            (
                consensus(build, "character_identified", "ankama.com/c", (5, 2), "string"),
                consensus(build, "quest_completed", "ankama.com/q", (3,), "positive_int"),
            ),
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "mapping_evidence_match")
        self.assertEqual(result.missing_events, ())
        self.assertEqual(result.mismatched_events, ())

    def test_missing_required_consensus_fails_closed(self) -> None:
        build = "a" * 64
        result = validate_mapping_against_consensus(
            manifest(build),
            (consensus(build, "character_identified", "ankama.com/c", (5, 2), "string"),),
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "mapping_evidence_missing")
        self.assertEqual(result.missing_events, ("quest_completed",))

    def test_wrong_build_or_path_is_mismatch(self) -> None:
        build = "a" * 64
        result = validate_mapping_against_consensus(
            manifest(build),
            (
                consensus(build, "character_identified", "ankama.com/c", (5, 2), "string"),
                consensus("b" * 64, "quest_completed", "ankama.com/q", (3,), "positive_int"),
            ),
        )
        self.assertFalse(result.valid)
        self.assertIn("quest_completed", result.mismatched_events)

        wrong_path = validate_mapping_against_consensus(
            manifest(build),
            (
                consensus(build, "character_identified", "ankama.com/c", (5, 2), "string"),
                consensus(build, "quest_completed", "ankama.com/q", (4,), "positive_int"),
            ),
        )
        self.assertFalse(wrong_path.valid)
        self.assertIn("quest_completed", wrong_path.mismatched_events)

    def test_ambiguous_consensus_is_not_accepted(self) -> None:
        build = "a" * 64
        ambiguous = ProtocolDiscoveryConsensus(
            build_sha256=build,
            event_type="quest_completed",
            report_count=2,
            candidates=(
                DiscoveryEvidenceCandidate("ankama.com/q", (3,), "positive_int", 2, 2),
                DiscoveryEvidenceCandidate("ankama.com/x", (1,), "positive_int", 2, 2),
            ),
            reason="ambiguous_consensus_candidates",
        )
        result = validate_mapping_against_consensus(
            manifest(build),
            (
                consensus(build, "character_identified", "ankama.com/c", (5, 2), "string"),
                ambiguous,
            ),
        )
        self.assertFalse(result.valid)
        self.assertIn("quest_completed", result.mismatched_events)


if __name__ == "__main__":
    unittest.main()
