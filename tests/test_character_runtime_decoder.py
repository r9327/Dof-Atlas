from __future__ import annotations

import unittest

from app.network.character_runtime_decoder import (
    CharacterRuntimeProtocolMessageDecoder,
    _candidate_achievement_snapshot,
    _candidate_level,
)
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


def _level_payload(level: int) -> bytes:
    return _message(
        1,
        _message(4, _scalar(2, level) + _scalar(4, level)),
    )


def _achievements_payload(ids: tuple[int, ...]) -> bytes:
    return b"".join(
        _message(
            1,
            _scalar(1, achievement_id)
            + _scalar(2, 1_700_000_000 + achievement_id)
            + _scalar(3, 200),
        )
        for achievement_id in ids
    )


class _Delegate:
    def __init__(self, decoded: DecodedClientMessage | None) -> None:
        self.decoded = decoded
        self.closed: list[str] = []
        self.reset_count = 0

    def decode(self, _message: CapturedProtocolMessage):
        return self.decoded

    def session_closed(self, session_id: str) -> None:
        self.closed.append(session_id)

    def reset(self) -> None:
        self.reset_count += 1


class CharacterRuntimeProtocolMessageDecoderTests(unittest.TestCase):
    def test_only_verified_identity_from_same_transport_session_is_projected(self):
        state = CharacterRuntimeStateStore()
        raw = CapturedProtocolMessage(
            session_id="s1",
            type_url="type.ankama.com/kva",
            payload=b"",
        )
        verified = DecodedClientMessage(
            session_id="s1",
            event_type="character_identified",
            fields={"character_name": "Alpha", "character_id": 42},
            verified=True,
        )
        decoder = CharacterRuntimeProtocolMessageDecoder(
            _Delegate(verified),
            state=state,
        )
        self.assertIs(decoder.decode(raw), verified)
        snapshot = state.snapshot("character:42")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.name, "Alpha")
        self.assertTrue(snapshot.connected)
        self.assertIsNone(snapshot.level)
        self.assertIsNone(snapshot.achievement_points)

        unverified_state = CharacterRuntimeStateStore()
        unverified = DecodedClientMessage(
            session_id="s1",
            event_type="character_identified",
            fields={"character_name": "Alpha", "character_id": 42},
            verified=False,
        )
        CharacterRuntimeProtocolMessageDecoder(
            _Delegate(unverified),
            state=unverified_state,
        ).decode(raw)
        self.assertIsNone(unverified_state.snapshot("character:42"))

        mismatched_state = CharacterRuntimeStateStore()
        wrong_session = DecodedClientMessage(
            session_id="other-session",
            event_type="character_identified",
            fields={"character_name": "Alpha", "character_id": 42},
            verified=True,
        )
        CharacterRuntimeProtocolMessageDecoder(
            _Delegate(wrong_session),
            state=mismatched_state,
        ).decode(raw)
        self.assertIsNone(mismatched_state.snapshot("character:42"))

    def test_level_candidate_requires_duplicate_consistent_level_fields(self):
        self.assertEqual(_candidate_level(_level_payload(199)), (199, (199, 199)))

        inconsistent = _message(
            1,
            _message(4, _scalar(2, 199) + _scalar(4, 198)),
        )
        self.assertEqual(_candidate_level(inconsistent), (None, (199, 198)))

    def test_achievement_snapshot_candidate_uses_only_known_ids_and_local_points(self):
        points = {10: 5, 20: 10, 30: 15}
        payload = _achievements_payload((10, 20, 30))
        self.assertEqual(
            _candidate_achievement_snapshot(payload, points),
            ((10, 20, 30), 30),
        )

        unknown = payload + _message(1, _scalar(1, 999))
        self.assertIsNone(_candidate_achievement_snapshot(unknown, points))

        too_small = _achievements_payload((10, 20))
        self.assertIsNone(_candidate_achievement_snapshot(too_small, points))

    def test_family_aliases_do_not_prove_current_level_or_real_success_points(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        decoder = CharacterRuntimeProtocolMessageDecoder(
            _Delegate(None),
            state=state,
            achievement_points_by_id={10: 5, 20: 10, 30: 15},
        )

        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kri",
                payload=_level_payload(199),
                direction="server_to_client",
            )
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/gus",
                payload=_achievements_payload((10, 20, 30)),
                direction="server_to_client",
            )
        )

        snapshot = state.snapshot("character:42")
        self.assertIsNone(snapshot.level)
        self.assertIsNone(snapshot.achievement_points)

    def test_repeated_rotated_level_shape_remains_non_authoritative(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        decoder = CharacterRuntimeProtocolMessageDecoder(_Delegate(None), state=state)
        message = CapturedProtocolMessage(
            session_id="s1",
            type_url="type.ankama.com/rotated-level",
            payload=_level_payload(199),
            direction="server_to_client",
        )
        decoder.decode(message)
        self.assertIsNone(state.snapshot("character:42").level)
        decoder.decode(message)
        self.assertIsNone(state.snapshot("character:42").level)

    def test_strong_catalog_shape_does_not_prove_achievement_semantics(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        points = {10: 5, 20: 10, 30: 15, 40: 20, 50: 25}
        decoder = CharacterRuntimeProtocolMessageDecoder(
            _Delegate(None),
            state=state,
            achievement_points_by_id=points,
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/rotated-achievements",
                payload=_achievements_payload((10, 20, 30, 40, 50)),
                direction="server_to_client",
            )
        )
        self.assertIsNone(state.snapshot("character:42").achievement_points)

    def test_profile_facts_before_identity_or_from_outbound_packets_are_ignored(self):
        state = CharacterRuntimeStateStore()
        decoder = CharacterRuntimeProtocolMessageDecoder(
            _Delegate(None),
            state=state,
            achievement_points_by_id={10: 5, 20: 10, 30: 15},
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kri",
                payload=_level_payload(199),
                direction="server_to_client",
            )
        )
        self.assertIsNone(state.snapshot("character:42"))

        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kri",
                payload=_level_payload(199),
                direction="client_to_server",
            )
        )
        self.assertIsNone(state.snapshot("character:42").level)

    def test_identity_switch_cannot_reuse_rotated_alias_evidence(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        decoder = CharacterRuntimeProtocolMessageDecoder(_Delegate(None), state=state)
        rotated = CapturedProtocolMessage(
            session_id="s1",
            type_url="type.ankama.com/rotated-level",
            payload=_level_payload(199),
            direction="server_to_client",
        )
        decoder.decode(rotated)
        self.assertIsNone(state.snapshot("character:42").level)

        decoder.delegate.decoded = DecodedClientMessage(
            session_id="s1",
            event_type="character_identified",
            fields={"character_name": "Beta", "character_id": 84},
            verified=True,
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kva",
                payload=b"",
                direction="server_to_client",
            )
        )
        decoder.delegate.decoded = None
        decoder.decode(rotated)
        self.assertIsNone(state.snapshot("character:84").level)
        decoder.decode(rotated)
        self.assertIsNone(state.snapshot("character:84").level)
        self.assertIsNone(state.snapshot("character:42").level)

    def test_session_lifecycle_is_forwarded_and_detaches_runtime_identity(self):
        state = CharacterRuntimeStateStore()
        delegate = _Delegate(
            DecodedClientMessage(
                session_id="s1",
                event_type="character_identified",
                fields={"character_name": "Alpha", "character_id": 42},
                verified=True,
            )
        )
        decoder = CharacterRuntimeProtocolMessageDecoder(delegate, state=state)
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kva",
                payload=b"",
            )
        )
        decoder.session_closed("s1")
        self.assertEqual(delegate.closed, ["s1"])
        self.assertFalse(state.snapshot("character:42").connected)

        decoder.reset()
        self.assertEqual(delegate.reset_count, 1)


if __name__ == "__main__":
    unittest.main()
