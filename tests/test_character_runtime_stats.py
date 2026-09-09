from __future__ import annotations

import unittest

from app.network.character_runtime_decoder import (
    CharacterRuntimeProtocolMessageDecoder,
    _candidate_character_stats,
)
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.network.transport import CapturedProtocolMessage


def _varint(value: int) -> bytes:
    remaining = int(value)
    if remaining < 0:
        remaining += 1 << 64
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


def _entry(
    characteristic_id: int,
    *,
    container: int = 4,
    base: int = 0,
    parchments: int = 0,
    equipment: int = 0,
) -> bytes:
    prefix = b"" if characteristic_id == 0 else _scalar(1, characteristic_id)
    if container == 4:
        value = b""
        if base:
            value += _scalar(2, base)
        if parchments:
            value += _scalar(3, parchments)
        if equipment:
            value += _scalar(7, equipment)
    elif container == 5:
        value = b""
        if base:
            value += _scalar(1, base)
        if equipment:
            value += _scalar(5, equipment)
    elif container == 2:
        value = _scalar(2, base) if base else b""
    else:
        raise ValueError(container)
    return prefix + _message(container, value)


def _kub_payload(*, wrong_ap_container: bool = False) -> bytes:
    entries = (
        _entry(0, base=3200, equipment=150),
        _entry(1, container=4 if wrong_ap_container else 5, base=6, equipment=5),
        _entry(10, base=200, parchments=100, equipment=50),
        _entry(11, base=300, parchments=100, equipment=400),
        _entry(12, base=100, parchments=100, equipment=20),
        _entry(13, base=150, parchments=100, equipment=75),
        _entry(14, base=180, parchments=100, equipment=60),
        _entry(15, base=220, parchments=100, equipment=80),
        _entry(23, container=5, base=3, equipment=3),
        _entry(25, equipment=120),
        _entry(47, container=2, base=10000),
        _entry(96, container=2, base=500),
        _entry(18, base=0),
    )
    body = b"".join(_message(11, entry) for entry in entries)
    return _message(2, body)


class _Delegate:
    def decode(self, _message: CapturedProtocolMessage):
        return None


class CharacterRuntimeStatsTests(unittest.TestCase):
    def test_exact_kub_shape_decodes_displayed_character_values(self):
        stats = _candidate_character_stats(_kub_payload())
        self.assertIsNotNone(stats)
        values = dict(stats)
        self.assertEqual(values["life_points"], 3350)
        self.assertEqual(values["action_points"], 11)
        self.assertEqual(values["movement_points"], 6)
        self.assertEqual(values["strength"], 350)
        self.assertEqual(values["vitality"], 800)
        self.assertEqual(values["power"], 120)
        self.assertEqual(values["energy"], 10000)
        self.assertEqual(values["shield"], 500)
        self.assertEqual(values["critical"], 0)

    def test_kub_is_applied_only_to_verified_routed_server_session(self):
        state = CharacterRuntimeStateStore()
        decoder = CharacterRuntimeProtocolMessageDecoder(_Delegate(), state=state)
        inbound = CapturedProtocolMessage(
            session_id="s1",
            type_url="type.ankama.com/kub",
            payload=_kub_payload(),
            direction="server_to_client",
        )

        decoder.decode(inbound)
        self.assertIsNone(state.snapshot_for_session("s1"))

        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kub",
                payload=_kub_payload(),
                direction="client_to_server",
            )
        )
        self.assertEqual(state.snapshot("character:42").stats, ())

        decoder.decode(inbound)
        self.assertEqual(dict(state.snapshot("character:42").stats)["strength"], 350)

        state.identify(
            session_id="s1",
            character_key="character:84",
            character_id=84,
            name="Beta",
        )
        self.assertEqual(state.snapshot("character:84").stats, ())
        self.assertEqual(dict(state.snapshot("character:42").stats)["strength"], 350)

    def test_wrong_alias_or_wrong_known_container_cannot_publish_stats(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        decoder = CharacterRuntimeProtocolMessageDecoder(_Delegate(), state=state)

        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/not-kub",
                payload=_kub_payload(),
                direction="server_to_client",
            )
        )
        self.assertEqual(state.snapshot("character:42").stats, ())

        self.assertIsNone(_candidate_character_stats(_kub_payload(wrong_ap_container=True)))
        decoder.decode(
            CapturedProtocolMessage(
                session_id="s1",
                type_url="type.ankama.com/kub",
                payload=_kub_payload(wrong_ap_container=True),
                direction="server_to_client",
            )
        )
        self.assertEqual(state.snapshot("character:42").stats, ())

    def test_runtime_store_rejects_duplicate_or_unbounded_stat_rows(self):
        state = CharacterRuntimeStateStore()
        state.identify(
            session_id="s1",
            character_key="character:42",
            character_id=42,
            name="Alpha",
        )
        self.assertFalse(
            state.update_verified_profile(
                "s1",
                stats=(("strength", 100), ("strength", 200)),
            )
        )
        self.assertFalse(
            state.update_verified_profile(
                "s1",
                stats=(("strength", 2_147_483_648),),
            )
        )
        self.assertEqual(state.snapshot("character:42").stats, ())


if __name__ == "__main__":
    unittest.main()
