from __future__ import annotations

import unittest

from app.network.character_runtime_decoder import CharacterRuntimeProtocolMessageDecoder
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.network.normalizer import DecodedClientMessage
from app.network.transport import CapturedProtocolMessage


def _varint(value: int) -> bytes:
    remaining = int(value)
    encoded = bytearray()
    while True:
        current = remaining & 0x7F
        remaining >>= 7
        if remaining:
            encoded.append(current | 0x80)
        else:
            encoded.append(current)
            return bytes(encoded)


def _scalar(field_number: int, value: int) -> bytes:
    return _varint((int(field_number) << 3) | 0) + _varint(int(value))


def _message(field_number: int, payload: bytes) -> bytes:
    body = bytes(payload)
    return _varint((int(field_number) << 3) | 2) + _varint(len(body)) + body


def _selected_payload(level: int) -> bytes:
    # 3.6.10.10 kva: f1.f1.f1 = character details, f3 = level.
    details = _scalar(3, level)
    character = _message(1, details) + _scalar(2, 42)
    return _message(1, _message(1, character))


class _Delegate:
    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified

    def decode(self, message: CapturedProtocolMessage):
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="character_identified",
            fields={"character_name": "Alpha", "character_id": 42},
            verified=self.verified,
        )


class VerifiedSelectionLevelTests(unittest.TestCase):
    def _decode(
        self,
        *,
        type_url: str = "type.ankama.com/kva",
        direction: str = "server_to_client",
        level: int = 199,
        verified: bool = True,
    ) -> CharacterRuntimeStateStore:
        state = CharacterRuntimeStateStore()
        decoder = CharacterRuntimeProtocolMessageDecoder(
            _Delegate(verified=verified),
            state=state,
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url=type_url,
                payload=_selected_payload(level),
                direction=direction,
            )
        )
        return state

    def test_verified_kva_projects_level_from_reviewed_selection_path(self):
        state = self._decode(level=199)
        snapshot = state.snapshot("character:42")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.level, 199)

    def test_level_is_not_projected_from_wrong_alias_or_outbound_packet(self):
        wrong_alias = self._decode(type_url="type.ankama.com/not-kva")
        self.assertIsNone(wrong_alias.snapshot("character:42").level)

        outbound = self._decode(direction="client_to_server")
        self.assertIsNone(outbound.snapshot("character:42").level)

    def test_unverified_identity_or_invalid_level_cannot_project_level(self):
        unverified = self._decode(verified=False)
        self.assertIsNone(unverified.snapshot("character:42"))

        invalid = self._decode(level=201)
        self.assertIsNone(invalid.snapshot("character:42").level)


if __name__ == "__main__":
    unittest.main()
