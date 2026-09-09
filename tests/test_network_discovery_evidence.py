from __future__ import annotations

import itertools
import unittest

from app.network.discovery_evidence import (
    ProtocolDiscoveryEvidenceError,
    build_discovery_consensus,
    parse_discovery_consensus,
)


_REPORT_IDS = itertools.count(1)
_PRIVACY = "no_payload_no_scalar_value_no_session_no_address_storage"


def report(
    build: str,
    event: str,
    candidates: list[dict],
    *,
    capture_id: str | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "purpose": "protocol_mapping_discovery_evidence_only",
        "authoritative_mapping": False,
        "privacy": _PRIVACY,
        "direction": "server_to_client",
        "capture_id": capture_id or f"{next(_REPORT_IDS):032x}",
        "build_sha256": build,
        "event_type": event,
        "observed_message_count": max(1, len(candidates)),
        "malformed_message_count": 0,
        "dropped_candidate_count": 0,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def candidate(type_url: str, path: list[int], kind: str, count: int = 1) -> dict:
    return {
        "type_url": type_url,
        "path": path,
        "kind": kind,
        "matching_message_count": count,
    }


class NetworkDiscoveryEvidenceTests(unittest.TestCase):
    def test_two_reports_keep_only_common_candidate(self) -> None:
        build = "a" * 64
        common = candidate("ankama.com/q", [3], "positive_int", 2)
        first = report(build, "quest_completed", [common, candidate("ankama.com/noise-a", [1], "positive_int")])
        second = report(build, "quest_completed", [candidate("ankama.com/q", [3], "positive_int", 4), candidate("ankama.com/noise-b", [9], "positive_int")])

        consensus = build_discovery_consensus((first, second))
        self.assertTrue(consensus.unambiguous)
        row = consensus.candidates[0]
        self.assertEqual((row.type_url, row.path, row.supporting_report_count, row.total_matching_message_count), ("ankama.com/q", (3,), 2, 6))

    def test_multiple_or_no_common_candidates_remain_non_authoritative(self) -> None:
        build = "a" * 64
        rows = [candidate("ankama.com/a", [1], "positive_int"), candidate("ankama.com/b", [2], "positive_int")]
        ambiguous = build_discovery_consensus((report(build, "quest_completed", rows), report(build, "quest_completed", rows)))
        self.assertEqual(ambiguous.reason, "ambiguous_consensus_candidates")
        self.assertFalse(ambiguous.unambiguous)

        none = build_discovery_consensus((
            report(build, "quest_completed", [candidate("ankama.com/a", [1], "positive_int")]),
            report(build, "quest_completed", [candidate("ankama.com/b", [1], "positive_int")]),
        ))
        self.assertEqual(none.reason, "no_consensus_candidate")
        self.assertEqual(none.candidates, ())

    def test_different_builds_events_or_duplicate_capture_are_rejected(self) -> None:
        row = candidate("ankama.com/a", [1], "positive_int")
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((report("a" * 64, "quest_completed", [row]), report("b" * 64, "quest_completed", [row])))
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((report("a" * 64, "quest_completed", [row]), report("a" * 64, "achievement_completed", [row])))

        capture_id = "1" * 32
        first = report("a" * 64, "quest_completed", [row], capture_id=capture_id)
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((first, dict(first)))

    def test_one_report_or_invalid_capture_id_is_rejected(self) -> None:
        row = candidate("ankama.com/a", [1], "positive_int")
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((report("a" * 64, "quest_completed", [row]),))
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((
                report("a" * 64, "quest_completed", [row], capture_id="bad"),
                report("a" * 64, "quest_completed", [row]),
            ))

    def test_report_contract_and_completeness_are_required(self) -> None:
        row = candidate("ankama.com/a", [1], "positive_int")
        base = report("a" * 64, "quest_completed", [row])
        other = report("a" * 64, "quest_completed", [row])
        for field, value in (
            ("purpose", "other"),
            ("privacy", "other"),
            ("direction", "client_to_server"),
            ("authoritative_mapping", True),
            ("candidate_count", 99),
            ("dropped_candidate_count", 1),
        ):
            bad = dict(base)
            bad[field] = value
            with self.subTest(field=field):
                with self.assertRaises(ProtocolDiscoveryEvidenceError):
                    build_discovery_consensus((bad, other))

    def test_event_kind_mismatch_and_duplicate_candidate_are_rejected(self) -> None:
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((
                report("a" * 64, "character_identified", [candidate("ankama.com/c", [1], "positive_int")]),
                report("a" * 64, "character_identified", [candidate("ankama.com/c", [1], "string")]),
            ))
        duplicate = candidate("ankama.com/q", [1], "positive_int")
        with self.assertRaises(ProtocolDiscoveryEvidenceError):
            build_discovery_consensus((
                report("a" * 64, "quest_completed", [duplicate, dict(duplicate)]),
                report("a" * 64, "quest_completed", [duplicate]),
            ))

    def test_consensus_round_trip_is_strict_and_contains_no_capture_or_scalar_target(self) -> None:
        build = "a" * 64
        first = report(build, "character_identified", [candidate("ankama.com/c", [5, 2], "string", 2)])
        second = report(build, "character_identified", [candidate("ankama.com/c", [5, 2], "string", 2)])
        consensus = build_discovery_consensus((first, second))
        serialized = consensus.to_dict()
        parsed = parse_discovery_consensus(serialized)
        self.assertEqual(parsed, consensus)
        text = repr(serialized)
        self.assertNotIn(first["capture_id"], text)
        self.assertNotIn(second["capture_id"], text)
        self.assertNotIn("character_name", text)
        self.assertNotIn("expected_id", text)
        self.assertFalse(serialized["authoritative_mapping"])

    def test_tampered_consensus_is_rejected(self) -> None:
        reports = (
            report("a" * 64, "quest_completed", [candidate("ankama.com/q", [3], "positive_int")]),
            report("a" * 64, "quest_completed", [candidate("ankama.com/q", [3], "positive_int")]),
        )
        raw = build_discovery_consensus(reports).to_dict()
        for field, value in (
            ("candidate_count", 2),
            ("reason", "ambiguous_consensus_candidates"),
            ("unambiguous", False),
            ("authoritative_mapping", True),
        ):
            bad = dict(raw)
            bad[field] = value
            with self.subTest(field=field):
                with self.assertRaises(ProtocolDiscoveryEvidenceError):
                    parse_discovery_consensus(bad)


if __name__ == "__main__":
    unittest.main()
