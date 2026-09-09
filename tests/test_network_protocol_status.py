from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.protocol_status import inspect_local_protocol_status


def mapping_payload(build_sha256: str, *, include_character: bool = True) -> dict:
    messages = {
        "ankama.com/q": {
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
    }
    if include_character:
        messages["ankama.com/c"] = {
            "event_type": "character_identified",
            "fields": [
                {
                    "output_name": "character_name",
                    "path": [2, 1, 2, 1],
                    "kind": "string",
                    "required": True,
                }
            ],
        }
    return {
        "schema_version": 1,
        "game_version": "3.6.test",
        "build_sha256": build_sha256,
        "messages": messages,
    }


class NetworkProtocolStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.build = "a" * 64

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_mapping(self, name: str = "mapping.json", *, include_character: bool = True) -> Path:
        path = self.root / name
        path.write_text(
            json.dumps(mapping_payload(self.build, include_character=include_character)),
            encoding="utf-8",
        )
        return path

    def status(self):
        return inspect_local_protocol_status(
            lambda: (123,),
            mapping_roots=(self.root,),
            build_sha256_provider=lambda: self.build,
        )

    def test_no_handles_does_not_attempt_mapping(self) -> None:
        status = inspect_local_protocol_status(
            lambda: (),
            mapping_roots=(self.root,),
            build_sha256_provider=lambda: self.build,
        )
        self.assertFalse(status.ready_for_composition)
        self.assertEqual(status.reason, "no_window_handles")
        self.assertFalse(status.to_dict()["capture_started"])

    def test_no_exact_mapping_reports_build_without_starting_capture(self) -> None:
        status = self.status()
        self.assertFalse(status.ready_for_composition)
        self.assertEqual(status.reason, "mapping_no_exact_match")
        self.assertEqual(status.build_sha256, self.build)
        self.assertFalse(status.to_dict()["capture_started"])

    def test_exact_mapping_with_minimum_events_is_ready_for_composition_only(self) -> None:
        mapping = self.write_mapping()
        status = self.status()
        self.assertTrue(status.ready_for_composition)
        self.assertEqual(status.reason, "mapping_ready_not_started")
        self.assertEqual(status.mapping_name, mapping.name)
        self.assertEqual(status.matched_mapping_count, 1)
        self.assertFalse(status.to_dict()["capture_started"])

    def test_partial_mapping_reports_missing_required_event(self) -> None:
        self.write_mapping(include_character=False)
        status = self.status()
        self.assertFalse(status.ready_for_composition)
        self.assertEqual(status.reason, "mapping_missing_required_events")
        self.assertEqual(status.missing_required_events, ("character_identified",))

    def test_two_exact_mappings_are_ambiguous(self) -> None:
        self.write_mapping("one.json")
        self.write_mapping("two.json")
        status = self.status()
        self.assertFalse(status.ready_for_composition)
        self.assertEqual(status.reason, "mapping_ambiguous_exact_match")
        self.assertEqual(status.matched_mapping_count, 2)


if __name__ == "__main__":
    unittest.main()
