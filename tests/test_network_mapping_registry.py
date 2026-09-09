from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.mapping_registry import ProtocolMappingRegistry


def mapping_payload(build_sha256: str, *, alias: str = "quest_alias") -> dict:
    return {
        "schema_version": 1,
        "game_version": "3.6.test",
        "build_sha256": build_sha256,
        "messages": {
            f"ankama.com/{alias}": {
                "event_type": "quest_completed",
                "fields": [
                    {
                        "output_name": "quest_id",
                        "path": [1],
                        "kind": "positive_int",
                        "required": True,
                    }
                ],
            }
        },
    }


class NetworkMappingRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_mapping(self, name: str, build_sha256: str, *, alias: str = "quest_alias") -> Path:
        path = self.root / name
        path.write_text(
            json.dumps(mapping_payload(build_sha256, alias=alias)),
            encoding="utf-8",
        )
        return path

    def test_selects_only_exact_build_hash(self) -> None:
        exact = self.write_mapping("exact.json", "a" * 64)
        self.write_mapping("other.json", "b" * 64)

        selection = ProtocolMappingRegistry((self.root,)).select("a" * 64)

        self.assertTrue(selection.usable)
        self.assertEqual(selection.reason, "exact_match")
        self.assertEqual(selection.matched_paths, (exact,))
        self.assertEqual(selection.manifest.build_sha256, "a" * 64)

    def test_missing_build_never_falls_back_to_other_version(self) -> None:
        self.write_mapping("stale.json", "b" * 64)
        selection = ProtocolMappingRegistry((self.root,)).select("a" * 64)
        self.assertFalse(selection.usable)
        self.assertEqual(selection.reason, "no_exact_match")
        self.assertIsNone(selection.manifest)

    def test_duplicate_exact_build_is_ambiguous(self) -> None:
        first = self.write_mapping("first.json", "a" * 64, alias="one")
        second = self.write_mapping("second.json", "a" * 64, alias="two")

        selection = ProtocolMappingRegistry((self.root,)).select("a" * 64)

        self.assertFalse(selection.usable)
        self.assertEqual(selection.reason, "ambiguous_exact_match")
        self.assertEqual(set(selection.matched_paths), {first, second})
        self.assertIsNone(selection.manifest)

    def test_invalid_files_are_reported_and_never_loaded(self) -> None:
        exact = self.write_mapping("exact.json", "a" * 64)
        invalid = self.root / "broken.json"
        invalid.write_text("{not-json", encoding="utf-8")

        selection = ProtocolMappingRegistry((self.root,)).select("a" * 64)

        self.assertTrue(selection.usable)
        self.assertEqual(selection.matched_paths, (exact,))
        self.assertEqual(selection.invalid_paths, (invalid,))

    def test_invalid_requested_fingerprint_fails_closed_without_scan_result(self) -> None:
        self.write_mapping("exact.json", "a" * 64)
        selection = ProtocolMappingRegistry((self.root,)).select("not-a-hash")
        self.assertFalse(selection.usable)
        self.assertEqual(selection.reason, "invalid_build_fingerprint")
        self.assertEqual(selection.matched_paths, ())
        self.assertEqual(selection.invalid_paths, ())


if __name__ == "__main__":
    unittest.main()
