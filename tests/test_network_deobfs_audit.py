from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.network.deobfs_audit import (
    validate_consensus_deobfuscation,
    validate_consensus_deobfuscation_reports,
)
from app.network.discovery_evidence import DiscoveryEvidenceCandidate, ProtocolDiscoveryConsensus


def consensus(type_url: str, *, reason: str = "single_consensus_candidate") -> ProtocolDiscoveryConsensus:
    candidates = (
        DiscoveryEvidenceCandidate(
            type_url=type_url,
            path=(1,),
            kind="positive_int",
            supporting_report_count=2,
            total_matching_message_count=2,
        ),
    )
    if reason != "single_consensus_candidate":
        candidates = ()
    return ProtocolDiscoveryConsensus(
        build_sha256="a" * 64,
        event_type="quest_completed",
        report_count=2,
        candidates=candidates,
        reason=reason,
    )


def report_text(rows: list[str]) -> str:
    return (
        "Message Matches Report\n"
        "======================\n\n"
        "Obf  →  Orig                  File          [conf:   0.00%]\n"
        "----------------------------------------------------------\n"
        + "\n".join(rows)
        + f"\n\nTotal matches: {len(rows)}\n"
    )


class NetworkDeobfuscationAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.report_path = root / "structure_matches.txt"
        self.report_path.write_text(
            report_text(
                [
                    "irj  →  QuestValidatedEvent   quest.proto   [conf: 100.00%]",
                    "abc  →  ???                   ???           [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.enum_report_path = root / "enum_matches.txt"
        self.enum_report_path.write_text(report_text([]), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_matching_definitive_alias_is_valid_evidence(self) -> None:
        result = validate_consensus_deobfuscation(
            consensus("ankama.com/irj"),
            self.report_path,
            expected_message="QuestValidatedEvent",
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "deobfuscated_message_match")
        self.assertEqual(result.alias, "irj")
        self.assertEqual(result.confidence, 100.0)

    def test_multiple_reports_may_supply_one_definitive_match(self) -> None:
        result = validate_consensus_deobfuscation_reports(
            consensus("ankama.com/irj"),
            (self.enum_report_path, self.report_path),
            expected_message="QuestValidatedEvent",
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.original_message, "QuestValidatedEvent")

    def test_wrong_expected_message_fails_closed(self) -> None:
        result = validate_consensus_deobfuscation(
            consensus("ankama.com/irj"),
            self.report_path,
            expected_message="OtherEvent",
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "deobfuscated_message_mismatch")
        self.assertEqual(result.original_message, "QuestValidatedEvent")

    def test_uncertain_or_missing_alias_is_not_evidence(self) -> None:
        uncertain = validate_consensus_deobfuscation(
            consensus("ankama.com/abc"),
            self.report_path,
            expected_message="Foo",
        )
        self.assertFalse(uncertain.valid)
        self.assertEqual(uncertain.reason, "uncertain_deobfuscation_alias")

        missing = validate_consensus_deobfuscation(
            consensus("ankama.com/missing"),
            self.report_path,
            expected_message="QuestValidatedEvent",
        )
        self.assertFalse(missing.valid)
        self.assertEqual(missing.reason, "no_definitive_deobfuscation_match")

    def test_uncertainty_in_any_report_overrides_other_definitive_match(self) -> None:
        uncertain_path = Path(self.tmp.name) / "uncertain.txt"
        uncertain_path.write_text(
            report_text(["irj  →  ???                   ???           [conf: 100.00%]"]),
            encoding="utf-8",
        )
        result = validate_consensus_deobfuscation_reports(
            consensus("ankama.com/irj"),
            (self.report_path, uncertain_path),
            expected_message="QuestValidatedEvent",
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "uncertain_deobfuscation_alias")

    def test_conflicting_definitive_reports_fail_closed(self) -> None:
        conflicting_path = Path(self.tmp.name) / "conflicting.txt"
        conflicting_path.write_text(
            report_text(["irj  →  OtherEvent             other.proto   [conf: 100.00%]"]),
            encoding="utf-8",
        )
        result = validate_consensus_deobfuscation_reports(
            consensus("ankama.com/irj"),
            (self.report_path, conflicting_path),
            expected_message="QuestValidatedEvent",
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "conflicting_deobfuscation_matches")

    def test_ambiguous_consensus_or_nested_type_url_is_rejected(self) -> None:
        ambiguous = validate_consensus_deobfuscation(
            consensus("ankama.com/irj", reason="no_consensus_candidate"),
            self.report_path,
            expected_message="QuestValidatedEvent",
        )
        self.assertFalse(ambiguous.valid)
        self.assertEqual(ambiguous.reason, "consensus_not_unambiguous")

        nested = validate_consensus_deobfuscation(
            consensus("ankama.com/game/irj"),
            self.report_path,
            expected_message="QuestValidatedEvent",
        )
        self.assertFalse(nested.valid)
        self.assertEqual(nested.reason, "unsupported_type_url_alias")


if __name__ == "__main__":
    unittest.main()
