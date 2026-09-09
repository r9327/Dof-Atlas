from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.deobfs_bundle import (
    DeobfuscationEvidenceBundleError,
    create_deobfuscation_evidence_bundle,
    parse_deobfuscation_evidence_bundle,
    verify_deobfuscation_evidence_bundle,
)


def report_text(alias: str, original: str) -> str:
    return (
        "Message Matches Report\n"
        "======================\n\n"
        "Obf  →  Orig                  File          [conf:   0.00%]\n"
        "----------------------------------------------------------\n"
        f"{alias}  →  {original}   sample.proto   [conf: 100.00%]\n\n"
        "Total matches: 1\n"
    )


class NetworkDeobfuscationBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.enum_path = self.root / "enum_matches.txt"
        self.structure_path = self.root / "structure_matches.txt"
        self.enum_path.write_text(
            report_text("csel", "CharacterSelectionEvent"),
            encoding="utf-8",
        )
        self.structure_path.write_text(
            report_text("qval", "QuestValidatedEvent"),
            encoding="utf-8",
        )
        self.build = "a" * 64

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bundle_round_trip_and_verification(self) -> None:
        bundle = create_deobfuscation_evidence_bundle(
            self.build,
            (self.enum_path, self.structure_path),
        )
        parsed = parse_deobfuscation_evidence_bundle(bundle.to_dict())
        verified = verify_deobfuscation_evidence_bundle(
            parsed,
            (self.structure_path, self.enum_path),
            expected_build_sha256=self.build,
        )
        self.assertEqual({path.name for path in verified}, {"enum_matches.txt", "structure_matches.txt"})
        self.assertFalse(bundle.to_dict()["authoritative_mapping"])
        self.assertNotIn(str(self.root), json.dumps(bundle.to_dict()))

    def test_wrong_build_is_rejected(self) -> None:
        bundle = create_deobfuscation_evidence_bundle(
            self.build,
            (self.enum_path, self.structure_path),
        )
        with self.assertRaises(DeobfuscationEvidenceBundleError):
            verify_deobfuscation_evidence_bundle(
                bundle,
                (self.enum_path, self.structure_path),
                expected_build_sha256="b" * 64,
            )

    def test_report_changed_after_bundle_is_rejected(self) -> None:
        bundle = create_deobfuscation_evidence_bundle(
            self.build,
            (self.enum_path, self.structure_path),
        )
        self.structure_path.write_text(
            report_text("qval", "OtherEvent"),
            encoding="utf-8",
        )
        with self.assertRaises(DeobfuscationEvidenceBundleError):
            verify_deobfuscation_evidence_bundle(
                bundle,
                (self.enum_path, self.structure_path),
                expected_build_sha256=self.build,
            )

    def test_duplicate_report_content_is_rejected(self) -> None:
        duplicate = self.root / "copy.txt"
        duplicate.write_bytes(self.enum_path.read_bytes())
        with self.assertRaises(DeobfuscationEvidenceBundleError):
            create_deobfuscation_evidence_bundle(
                self.build,
                (self.enum_path, duplicate),
            )

    def test_bundle_rejects_absolute_or_nested_report_names(self) -> None:
        bundle = create_deobfuscation_evidence_bundle(self.build, (self.enum_path,))
        raw = bundle.to_dict()
        raw["reports"][0]["name"] = "folder/enum_matches.txt"
        with self.assertRaises(DeobfuscationEvidenceBundleError):
            parse_deobfuscation_evidence_bundle(raw)


if __name__ == "__main__":
    unittest.main()
