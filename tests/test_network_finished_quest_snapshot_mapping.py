from __future__ import annotations

import unittest

from app.network.mapping_manifest import ProtocolMappingError, parse_protocol_mapping
from app.network.normalizer import ProtocolEventNormalizer
from app.network.transport import CapturedProtocolMessage


BUILD = "12" * 32


def _varint(value: int) -> bytes:
    out = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field_varint(field_number: int, value: int) -> bytes:
    return _varint(field_number << 3) + _varint(value)


def _field_bytes(field_number: int, payload: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(payload)) + payload


def _base_mapping() -> dict:
    return {
        "schema_version": 1,
        "game_version": "3.6.10.10",
        "build_sha256": BUILD,
        "messages": {},
        "character_identity": {
            "roster_type_url": "type.ankama.com/kvi",
            "selected_type_url": "type.ankama.com/kva",
            "roster_entry_field": 1,
            "roster_character_id_path": [2],
            "roster_character_name_path": [1, 2],
            "selected_character_id_path": [1, 1, 2],
        },
        "finished_quests_snapshot": {
            "type_url": "type.ankama.com/qst",
            "finished_entry_field": 1,
            "quest_id_path_from_entry": [1],
            "player_id_field": 4,
        },
    }


class FinishedQuestSnapshotMappingTests(unittest.TestCase):
    def test_manifest_exposes_snapshot_as_runtime_event_and_builds_decoder(self) -> None:
        manifest = parse_protocol_mapping(_base_mapping())
        self.assertIn("character_identified", manifest.provided_event_types)
        self.assertIn("finished_quests_snapshot", manifest.provided_event_types)
        self.assertNotIn("quest_completed", manifest.provided_event_types)

        decoder = manifest.build_decoder(active_build_sha256_provider=lambda: BUILD)
        finished = _field_varint(1, 123) + _field_varint(2, 1)
        payload = _field_bytes(1, finished) + _field_varint(4, 55)
        decoded = decoder.decode(
            CapturedProtocolMessage("s1", "type.ankama.com/qst", payload)
        )
        self.assertIsNotNone(decoded)
        event = ProtocolEventNormalizer().normalize(decoded)
        self.assertIsNotNone(event)
        self.assertEqual(event.quest_ids, (123,))
        self.assertEqual(event.player_id, 55)

    def test_snapshot_url_cannot_overlap_identity_or_scalar_rules(self) -> None:
        identity_overlap = _base_mapping()
        identity_overlap["finished_quests_snapshot"]["type_url"] = "type.ankama.com/kva"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(identity_overlap)

        message_overlap = _base_mapping()
        message_overlap["messages"] = {
            "type.ankama.com/qst": {
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
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(message_overlap)

    def test_snapshot_mapping_rejects_legacy_prefix_and_invalid_fields(self) -> None:
        legacy = _base_mapping()
        legacy["finished_quests_snapshot"]["type_url"] = "ankama.com/qst"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(legacy)

        invalid = _base_mapping()
        invalid["finished_quests_snapshot"]["finished_entry_field"] = 0
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(invalid)

        invalid_path = _base_mapping()
        invalid_path["finished_quests_snapshot"]["quest_id_path_from_entry"] = []
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(invalid_path)


if __name__ == "__main__":
    unittest.main()
