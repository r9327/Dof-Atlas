from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.deobfs_bundle import create_deobfuscation_evidence_bundle
from app.network.discovery_evidence import DiscoveryEvidenceCandidate, ProtocolDiscoveryConsensus
from app.network.mapping_install import install_verified_protocol_mapping
from app.network.mapping_registry import ProtocolMappingRegistry


def report_text(rows: list[str]) -> str:
    return (
        "Message Matches Report\n"
        "======================\n\n"
        "Obf  →  Orig                  File          [conf:   0.00%]\n"
        "----------------------------------------------------------\n"
        + "\n".join(rows)
        + f"\n\nTotal matches: {len(rows)}\n"
    )


def consensus_payload(build: str, event: str, type_url: str, path: tuple[int, ...], kind: str) -> dict:
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


def candidate_payload(build: str, *, character_alias: str = "csel", quest_alias: str = "qval") -> dict:
    return {
        "schema_version": 1,
        "game_version": "3.6.test",
        "build_sha256": build,
        "messages": {
            f"ankama.com/{character_alias}": {
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
            f"ankama.com/{quest_alias}": {
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


class NetworkMappingInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.destination_root = self.root / "runtime_mappings"
        self.build = "a" * 64
        self.candidate = self.root / "candidate.json"
        self.character_consensus = self.root / "character_consensus.json"
        self.quest_consensus = self.root / "quest_consensus.json"
        self.enum_report = self.root / "enum_matches.txt"
        self.structure_report = self.root / "structure_matches.txt"
        self.bundle = self.root / "deobfs_bundle.json"

        self.candidate.write_text(json.dumps(candidate_payload(self.build)), encoding="utf-8")
        self.character_consensus.write_text(
            json.dumps(
                consensus_payload(
                    self.build,
                    "character_identified",
                    "ankama.com/csel",
                    (2, 1, 2, 1),
                    "string",
                )
            ),
            encoding="utf-8",
        )
        self.quest_consensus.write_text(
            json.dumps(
                consensus_payload(
                    self.build,
                    "quest_completed",
                    "ankama.com/qval",
                    (1,),
                    "positive_int",
                )
            ),
            encoding="utf-8",
        )
        self.enum_report.write_text(
            report_text(
                [
                    "csel  →  CharacterSelectionEvent   character_management.proto   [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.structure_report.write_text(
            report_text(
                [
                    "qval  →  QuestValidatedEvent       quest.proto                  [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.rebundle()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def rebundle(self) -> None:
        bundle = create_deobfuscation_evidence_bundle(
            self.build,
            (self.enum_report, self.structure_report),
        )
        self.bundle.write_text(json.dumps(bundle.to_dict()), encoding="utf-8")

    def install(self):
        return install_verified_protocol_mapping(
            self.candidate,
            (self.character_consensus, self.quest_consensus),
            self.bundle,
            (self.enum_report, self.structure_report),
            destination_root=self.destination_root,
        )

    def test_valid_candidate_is_installed_but_not_started(self) -> None:
        result = self.install()
        self.assertTrue(result.success)
        self.assertTrue(result.installed)
        self.assertEqual(result.reason, "mapping_installed_not_started")
        self.assertIsNotNone(result.destination)
        self.assertTrue(result.destination.is_file())
        self.assertFalse(result.to_dict()["capture_started"])

        selection = ProtocolMappingRegistry((self.destination_root,)).select(self.build)
        self.assertTrue(selection.usable)
        self.assertEqual(selection.matched_paths, (result.destination,))

    def test_identical_mapping_is_not_duplicated(self) -> None:
        first = self.install()
        second = self.install()
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertFalse(second.installed)
        self.assertEqual(second.reason, "mapping_already_installed")
        self.assertEqual(second.destination, first.destination)
        self.assertEqual(len(tuple(self.destination_root.glob("*.json"))), 1)

    def test_invalid_semantic_evidence_is_not_installed(self) -> None:
        self.structure_report.write_text(
            report_text(
                [
                    "qval  →  OtherEvent                other.proto                  [conf: 100.00%]",
                ]
            ),
            encoding="utf-8",
        )
        self.rebundle()
        result = self.install()
        self.assertFalse(result.success)
        self.assertFalse(result.installed)
        self.assertEqual(result.reason, "candidate_evidence_invalid")
        self.assertFalse(self.destination_root.exists() and any(self.destination_root.glob("*.json")))

    def test_different_mapping_for_same_build_blocks_install(self) -> None:
        self.destination_root.mkdir(parents=True)
        existing = self.destination_root / "existing.json"
        existing.write_text(
            json.dumps(candidate_payload(self.build, character_alias="otherc", quest_alias="otherq")),
            encoding="utf-8",
        )
        result = self.install()
        self.assertFalse(result.success)
        self.assertFalse(result.installed)
        self.assertEqual(result.reason, "different_mapping_already_installed")
        self.assertEqual(result.destination, existing)

    def test_ambiguous_existing_mappings_block_install(self) -> None:
        self.destination_root.mkdir(parents=True)
        for name, char_alias, quest_alias in (
            ("one.json", "c1", "q1"),
            ("two.json", "c2", "q2"),
        ):
            (self.destination_root / name).write_text(
                json.dumps(candidate_payload(self.build, character_alias=char_alias, quest_alias=quest_alias)),
                encoding="utf-8",
            )
        result = self.install()
        self.assertFalse(result.success)
        self.assertFalse(result.installed)
        self.assertEqual(result.reason, "existing_mapping_ambiguous")


if __name__ == "__main__":
    unittest.main()
