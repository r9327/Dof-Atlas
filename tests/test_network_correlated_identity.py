from __future__ import annotations

import unittest

from app.network.correlated_identity_decoder import (
    CorrelatedCharacterIdentityDecoder,
    CorrelatedCharacterIdentityRule,
)
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


def string_field(field_number: int, value: str) -> bytes:
    return bytes_field(field_number, value.encode("utf-8"))


def roster_entry(character_id: int, name: str, level: int = 200) -> bytes:
    basic = string_field(2, name) + varint_field(3, level)
    return bytes_field(1, basic) + varint_field(2, character_id)


def roster_payload(*entries: bytes) -> bytes:
    return b"".join(bytes_field(1, entry) for entry in entries)


def selected_payload(character_id: int) -> bytes:
    character = varint_field(2, character_id)
    success = bytes_field(1, character)
    return bytes_field(1, success)


def selected_payload_with_name(character_id: int, name: str) -> bytes:
    basic = string_field(2, name)
    character = bytes_field(1, basic) + varint_field(2, character_id)
    success = bytes_field(1, character)
    return bytes_field(1, success)


class _NullDecoder:
    def __init__(self) -> None:
        self.closed: list[str] = []
        self.reset_count = 0

    def decode(self, _message):
        return None

    def session_closed(self, session_id: str) -> None:
        self.closed.append(session_id)

    def reset(self) -> None:
        self.reset_count += 1


class CorrelatedCharacterIdentityDecoderTests(unittest.TestCase):
    def build_decoder(
        self,
        *,
        active_build: str | None = None,
        direct_selected_name: bool = False,
    ):
        delegate = _NullDecoder()
        fingerprint = "a" * 64
        decoder = CorrelatedCharacterIdentityDecoder(
            delegate,
            CorrelatedCharacterIdentityRule(
                roster_type_url="type.ankama.com/kvi",
                selected_type_url="type.ankama.com/kva",
                roster_entry_field=1,
                roster_character_id_path=(2,),
                roster_character_name_path=(1, 2),
                selected_character_id_path=(1, 1, 2),
                selected_character_name_path=(1, 1, 1, 2) if direct_selected_name else (),
            ),
            mapping_version="3.6.10.10",
            mapping_fingerprint=fingerprint,
            active_fingerprint_provider=lambda: active_build or fingerprint,
        )
        return decoder, delegate

    def test_current_kvi_then_kva_emits_verified_character_identity(self) -> None:
        decoder, _delegate = self.build_decoder()
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="s1",
                    type_url="type.ankama.com/kvi",
                    payload=roster_payload(
                        roster_entry(101, "Alpha", 199),
                        roster_entry(202, "Bravo", 200),
                    ),
                )
            )
        )
        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kva",
                payload=selected_payload(202),
            )
        )
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(decoded.event_type, "character_identified")
        self.assertEqual(decoded.fields, {"character_name": "Bravo", "character_id": 202})

    def test_current_kva_can_identify_directly_when_it_contains_name_and_id(self) -> None:
        decoder, _delegate = self.build_decoder(direct_selected_name=True)

        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kva",
                payload=selected_payload_with_name(202, "Alice"),
            )
        )

        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(
            decoded.fields,
            {"character_name": "Alice", "character_id": 202},
        )

    def test_direct_selected_name_must_not_conflict_with_same_session_roster(self) -> None:
        decoder, _delegate = self.build_decoder(direct_selected_name=True)
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kvi",
                payload=roster_payload(roster_entry(202, "Other")),
            )
        )

        decoded = decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kva",
                payload=selected_payload_with_name(202, "Alice"),
            )
        )

        self.assertIsNone(decoded)

    def test_rosters_are_strictly_scoped_to_transport_session(self) -> None:
        decoder, _delegate = self.build_decoder()
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kvi",
                payload=roster_payload(roster_entry(101, "Alpha")),
            )
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="s2",
                    type_url="type.ankama.com/kva",
                    payload=selected_payload(101),
                )
            )
        )

    def test_malformed_replacement_roster_clears_previous_identity(self) -> None:
        decoder, _delegate = self.build_decoder()
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kvi",
                payload=roster_payload(roster_entry(101, "Alpha")),
            )
        )
        # A new malformed roster must invalidate the old id->name association.
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kvi",
                payload=bytes_field(1, b"\x08"),
            )
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="s1",
                    type_url="type.ankama.com/kva",
                    payload=selected_payload(101),
                )
            )
        )

    def test_unknown_selected_id_never_fabricates_identity(self) -> None:
        decoder, _delegate = self.build_decoder()
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kvi",
                payload=roster_payload(roster_entry(101, "Alpha")),
            )
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="s1",
                    type_url="type.ankama.com/kva",
                    payload=selected_payload(999),
                )
            )
        )

    def test_build_mismatch_disables_observation_and_selection(self) -> None:
        decoder, _delegate = self.build_decoder(active_build="b" * 64)
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kvi",
                payload=roster_payload(roster_entry(101, "Alpha")),
            )
        )
        self.assertIsNone(
            decoder.decode(
                CapturedProtocolMessage(
                    session_id="s1",
                    type_url="type.ankama.com/kva",
                    payload=selected_payload(101),
                )
            )
        )

    def test_session_close_and_reset_purge_roster_and_forward_lifecycle(self) -> None:
        decoder, delegate = self.build_decoder()
        roster = CapturedProtocolMessage(
            session_id="s1",
            type_url="type.ankama.com/kvi",
            payload=roster_payload(roster_entry(101, "Alpha")),
        )
        selected = CapturedProtocolMessage(
            session_id="s1",
            type_url="type.ankama.com/kva",
            payload=selected_payload(101),
        )
        decoder.decode(roster)
        decoder.session_closed("s1")
        self.assertEqual(delegate.closed, ["s1"])
        self.assertIsNone(decoder.decode(selected))

        decoder.decode(roster)
        decoder.reset()
        self.assertEqual(delegate.reset_count, 1)
        self.assertIsNone(decoder.decode(selected))


if __name__ == "__main__":
    unittest.main()
