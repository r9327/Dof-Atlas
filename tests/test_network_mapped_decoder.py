from __future__ import annotations

import unittest

from app.network.events import QuestCompletedEvent
from app.network.mapped_decoder import ProtocolFieldRule, ProtocolMessageRule, StrictMappedProtocolDecoder
from app.network.normalizer import ProtocolEventNormalizer
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


class NetworkMappedDecoderTests(unittest.TestCase):
    def build_decoder(self, active_version: str = "3.6.test") -> StrictMappedProtocolDecoder:
        return StrictMappedProtocolDecoder(
            mapping_version="3.6.test",
            active_version_provider=lambda: active_version,
            rules={
                "ankama.com/obfuscated_quest_done": ProtocolMessageRule(
                    event_type="quest_completed",
                    fields=(
                        ProtocolFieldRule(
                            output_name="quest_id",
                            path=(1,),
                            kind="positive_int",
                        ),
                    ),
                )
            },
        )

    def test_exact_version_and_exact_type_produce_verified_event(self) -> None:
        decoder = self.build_decoder()
        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/obfuscated_quest_done",
                payload=varint_field(1, 1234),
            )
        )
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(decoded.event_type, "quest_completed")
        self.assertEqual(decoded.fields["quest_id"], 1234)
        normalized = ProtocolEventNormalizer().normalize(decoded)
        self.assertIsInstance(normalized, QuestCompletedEvent)
        self.assertEqual(normalized.quest_id, 1234)

    def test_version_mismatch_disables_decoding(self) -> None:
        decoder = self.build_decoder(active_version="3.6.newer")
        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/obfuscated_quest_done",
                payload=varint_field(1, 1234),
            )
        )
        self.assertIsNone(decoded)

    def test_client_to_server_message_is_never_authoritative(self) -> None:
        decoder = self.build_decoder()
        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/obfuscated_quest_done",
                payload=varint_field(1, 1234),
                direction="client_to_server",
            )
        )
        self.assertIsNone(decoded)

    def test_unknown_type_and_missing_field_fail_closed(self) -> None:
        decoder = self.build_decoder()
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="session-1",
                    type_url="ankama.com/unknown",
                    payload=varint_field(1, 1234),
                )
            )
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="session-1",
                    type_url="ankama.com/obfuscated_quest_done",
                    payload=varint_field(2, 1234),
                )
            )
        )

    def test_repeated_semantic_field_is_ambiguous_and_rejected(self) -> None:
        decoder = self.build_decoder()
        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="session-1",
                type_url="ankama.com/obfuscated_quest_done",
                payload=varint_field(1, 1234) + varint_field(1, 5678),
            )
        )
        self.assertIsNone(decoded)

    def test_truncated_payload_fails_closed(self) -> None:
        decoder = self.build_decoder()
        truncated = encode_varint((1 << 3) | 2) + encode_varint(20) + b"short"
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="session-1",
                    type_url="ankama.com/obfuscated_quest_done",
                    payload=truncated,
                )
            )
        )

    def test_event_id_is_stable_for_transport_retransmission(self) -> None:
        decoder = self.build_decoder()
        message = CapturedProtocolMessage(
            session_id="session-1",
            type_url="ankama.com/obfuscated_quest_done",
            payload=varint_field(1, 1234),
        )
        first = decoder.decode(message)
        second = decoder.decode(message)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.event_id, second.event_id)

    def test_fingerprint_configuration_must_be_complete(self) -> None:
        rule = ProtocolMessageRule(
            event_type="quest_completed",
            fields=(ProtocolFieldRule("quest_id", (1,), "positive_int"),),
        )
        with self.assertRaises(ValueError):
            StrictMappedProtocolDecoder(
                mapping_version="3.6.test",
                active_version_provider=lambda: "3.6.test",
                rules={"ankama.com/quest": rule},
                mapping_fingerprint="a" * 64,
            )
        with self.assertRaises(ValueError):
            StrictMappedProtocolDecoder(
                mapping_version="3.6.test",
                active_version_provider=lambda: "3.6.test",
                rules={"ankama.com/quest": rule},
                active_fingerprint_provider=lambda: "a" * 64,
            )


if __name__ == "__main__":
    unittest.main()
