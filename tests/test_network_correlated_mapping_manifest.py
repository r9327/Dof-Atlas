from __future__ import annotations

import unittest

from app.network.mapping_manifest import ProtocolMappingError, parse_protocol_mapping
from app.network.transport import CapturedProtocolMessage


def encode_varint(value: int) -> bytes:
    output = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


def varint_field(field_number: int, value: int) -> bytes:
    return encode_varint((field_number << 3) | 0) + encode_varint(value)


def bytes_field(field_number: int, value: bytes) -> bytes:
    return encode_varint((field_number << 3) | 2) + encode_varint(len(value)) + value


def current_identity_mapping() -> dict:
    return {
        "schema_version": 1,
        "game_version": "3.6.10.10",
        "build_sha256": "a" * 64,
        "messages": {
            "type.ankama.com/quest": {
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
        "character_identity": {
            "roster_type_url": "type.ankama.com/kvi",
            "selected_type_url": "type.ankama.com/kva",
            "roster_entry_field": 1,
            "roster_character_id_path": [2],
            "roster_character_name_path": [1, 2],
            "selected_character_id_path": [1, 1, 2],
        },
    }


class CorrelatedMappingManifestTests(unittest.TestCase):
    def test_manifest_reports_correlated_identity_and_quest_completion_capabilities(self) -> None:
        manifest = parse_protocol_mapping(current_identity_mapping())
        self.assertEqual(
            manifest.provided_event_types,
            frozenset({"character_identified", "quest_completed", "quest_completion"}),
        )
        self.assertIsNotNone(manifest.character_identity)

    def test_manifest_builds_correlated_decoder_for_current_type_urls(self) -> None:
        manifest = parse_protocol_mapping(current_identity_mapping())
        decoder = manifest.build_decoder(active_build_sha256_provider=lambda: "a" * 64)

        basic = bytes_field(2, b"AtlasHero") + varint_field(3, 200)
        roster_entry = bytes_field(1, basic) + varint_field(2, 321)
        decoder.decode(
            CapturedProtocolMessage(
                "session-1",
                "type.ankama.com/kvi",
                bytes_field(1, roster_entry),
            )
        )
        selected = bytes_field(1, bytes_field(1, varint_field(2, 321)))
        decoded = decoder.decode(
            CapturedProtocolMessage("session-1", "type.ankama.com/kva", selected)
        )
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(decoded.fields["character_name"], "AtlasHero")
        self.assertEqual(decoded.fields["character_id"], 321)

    def test_manifest_accepts_optional_direct_selected_character_name_path(self) -> None:
        raw = current_identity_mapping()
        raw["character_identity"]["selected_character_name_path"] = [1, 1, 1, 2]
        manifest = parse_protocol_mapping(raw)

        self.assertEqual(
            manifest.character_identity.selected_character_name_path,
            (1, 1, 1, 2),
        )

    def test_character_identity_requires_current_full_type_url(self) -> None:
        raw = current_identity_mapping()
        raw["character_identity"]["roster_type_url"] = "ankama.com/kvi"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(raw)

    def test_identity_urls_cannot_overlap_direct_message_rules(self) -> None:
        raw = current_identity_mapping()
        raw["messages"]["type.ankama.com/kvi"] = raw["messages"].pop(
            "type.ankama.com/quest"
        )
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(raw)

    def test_direct_and_correlated_character_identity_are_mutually_exclusive(self) -> None:
        raw = current_identity_mapping()
        raw["messages"]["type.ankama.com/direct_identity"] = {
            "event_type": "character_identified",
            "fields": [
                {
                    "output_name": "character_name",
                    "path": [1],
                    "kind": "string",
                    "required": True,
                }
            ],
        }
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(raw)


if __name__ == "__main__":
    unittest.main()
