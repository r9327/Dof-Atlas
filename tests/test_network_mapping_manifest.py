from __future__ import annotations

import copy
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
    return encode_varint((int(field_number) << 3) | 0) + encode_varint(value)


class NetworkMappingManifestTests(unittest.TestCase):
    def base_mapping(self) -> dict:
        return {
            "schema_version": 1,
            "game_version": "3.6.test",
            "build_sha256": "a" * 64,
            "messages": {
                "ankama.com/quest_alias": {
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

    def test_valid_manifest_builds_decoder_from_exact_build_hash_alone(self) -> None:
        manifest = parse_protocol_mapping(self.base_mapping())
        decoder = manifest.build_decoder(
            active_build_sha256_provider=lambda: "a" * 64,
        )
        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/quest_alias",
                payload=varint_field(1, 1234),
            )
        )
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(decoded.fields["quest_id"], 1234)

    def test_optional_version_check_must_also_match_when_configured(self) -> None:
        manifest = parse_protocol_mapping(self.base_mapping())
        decoder = manifest.build_decoder(
            active_build_sha256_provider=lambda: "a" * 64,
            active_version_provider=lambda: "3.6.other",
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="session-1",
                    type_url="ankama.com/quest_alias",
                    payload=varint_field(1, 1234),
                )
            )
        )

    def test_build_fingerprint_mismatch_disables_decode(self) -> None:
        manifest = parse_protocol_mapping(self.base_mapping())
        decoder = manifest.build_decoder(
            active_build_sha256_provider=lambda: "b" * 64,
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="session-1",
                    type_url="ankama.com/quest_alias",
                    payload=varint_field(1, 1234),
                )
            )
        )

    def test_manifest_rejects_missing_or_invalid_fingerprint(self) -> None:
        for fingerprint in (None, "", "not-a-sha256", "f" * 63):
            raw = self.base_mapping()
            raw["build_sha256"] = fingerprint
            with self.subTest(fingerprint=fingerprint):
                with self.assertRaises(ProtocolMappingError):
                    parse_protocol_mapping(raw)

    def test_manifest_rejects_unknown_event_or_semantic_output(self) -> None:
        unknown_event = self.base_mapping()
        unknown_event["messages"]["ankama.com/quest_alias"]["event_type"] = "guessed_event"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(unknown_event)

        wrong_output = self.base_mapping()
        wrong_output["messages"]["ankama.com/quest_alias"]["fields"][0]["output_name"] = "character_id"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(wrong_output)

    def test_manifest_rejects_missing_or_optional_required_semantic_field(self) -> None:
        raw = self.base_mapping()
        raw["messages"] = {
            "ankama.com/quest_objective_alias": {
                "event_type": "quest_objective_completed",
                "fields": [
                    {
                        "output_name": "quest_id",
                        "path": [1],
                        "kind": "positive_int",
                    }
                ],
            }
        }
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(raw)

        optional = self.base_mapping()
        optional["messages"]["ankama.com/quest_alias"]["fields"][0]["required"] = False
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(optional)

    def test_manifest_rejects_wrong_kind_and_duplicate_output(self) -> None:
        wrong_kind = self.base_mapping()
        wrong_kind["messages"]["ankama.com/quest_alias"]["fields"][0]["kind"] = "string"
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(wrong_kind)

        duplicate = self.base_mapping()
        duplicate["messages"]["ankama.com/quest_alias"]["fields"].append(
            copy.deepcopy(duplicate["messages"]["ankama.com/quest_alias"]["fields"][0])
        )
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(duplicate)

    def test_manifest_rejects_non_ankama_type_url_and_non_integer_path(self) -> None:
        raw = self.base_mapping()
        rule = raw["messages"].pop("ankama.com/quest_alias")
        raw["messages"]["example.com/quest_alias"] = rule
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(raw)

        float_path = self.base_mapping()
        float_path["messages"]["ankama.com/quest_alias"]["fields"][0]["path"] = [1.0]
        with self.assertRaises(ProtocolMappingError):
            parse_protocol_mapping(float_path)


if __name__ == "__main__":
    unittest.main()
