from __future__ import annotations

import unittest

from app.network.normalizer import DecodedClientMessage
from app.network.quest_snapshot_decoder import (
    FinishedQuestsSnapshotDecoder,
    FinishedQuestsSnapshotRule,
)
from app.network.transport import CapturedProtocolMessage


FINGERPRINT = "ab" * 32


def _varint(value: int) -> bytes:
    rows = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            rows.append(byte | 0x80)
        else:
            rows.append(byte)
            return bytes(rows)


def _field_varint(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 0) + _varint(value)


def _field_bytes(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


class _Delegate:
    def __init__(self) -> None:
        self.messages: list[CapturedProtocolMessage] = []
        self.reset_count = 0
        self.closed: list[str] = []

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        self.messages.append(message)
        return None

    def reset(self) -> None:
        self.reset_count += 1

    def session_closed(self, session_id: str) -> None:
        self.closed.append(session_id)


class FinishedQuestsSnapshotDecoderTests(unittest.TestCase):
    def _decoder(self, delegate: _Delegate | None = None, fingerprint: str = FINGERPRINT):
        return FinishedQuestsSnapshotDecoder(
            delegate or _Delegate(),
            FinishedQuestsSnapshotRule(
                type_url="type.ankama.com/qst",
                finished_entry_field=1,
                quest_id_path_from_entry=(1,),
                player_id_field=4,
            ),
            mapping_version="3.6.10.10",
            mapping_fingerprint=FINGERPRINT,
            active_fingerprint_provider=lambda: fingerprint,
        )

    def test_decodes_repeated_finished_quests_and_required_player_id(self) -> None:
        payload = b"".join(
            [
                _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1)),
                _field_bytes(1, _field_varint(1, 202) + _field_varint(2, 3)),
                _field_varint(4, 9001),
            ]
        )
        decoded = self._decoder().decode(
            CapturedProtocolMessage("s1", "type.ankama.com/qst", payload)
        )
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(decoded.event_type, "finished_quests_snapshot")
        self.assertEqual(decoded.fields["quest_ids"], (101, 202))
        self.assertEqual(decoded.fields["player_id"], 9001)

    def test_accepts_reviewed_active_and_reinitialized_sections(self) -> None:
        active = _field_varint(1, 303) + _field_bytes(2, _field_varint(1, 7))
        payload = b"".join(
            [
                _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1)),
                _field_bytes(2, active),
                _field_varint(3, 404),
                _field_bytes(3, _varint(505) + _varint(606)),
                _field_varint(4, 9001),
            ]
        )
        decoded = self._decoder().decode(
            CapturedProtocolMessage("s1", "type.ankama.com/qst", payload)
        )
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.fields["quest_ids"], (101,))
        self.assertEqual(decoded.fields["player_id"], 9001)

    def test_empty_finished_list_is_valid_when_player_is_attributed(self) -> None:
        decoded = self._decoder().decode(
            CapturedProtocolMessage(
                "s1",
                "type.ankama.com/qst",
                _field_varint(4, 9001),
            )
        )
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.fields["quest_ids"], ())
        self.assertEqual(decoded.fields["player_id"], 9001)

    def test_rejects_missing_or_repeated_player_id(self) -> None:
        missing = _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", missing)
            )
        )

        repeated = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
            + _field_varint(4, 9001)
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", repeated)
            )
        )

    def test_rejects_malformed_finished_entry(self) -> None:
        payload = _field_bytes(1, _field_varint(2, 1)) + _field_varint(4, 9001)
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", payload)
            )
        )

        missing_finished_count = _field_bytes(1, _field_varint(1, 101)) + _field_varint(4, 9001)
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", missing_finished_count)
            )
        )

        zero_finished_count = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 0))
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", zero_finished_count)
            )
        )

        unexpected_nested_field = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1) + _field_varint(3, 7))
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", unexpected_nested_field)
            )
        )

        repeated_finished_count = (
            _field_bytes(
                1,
                _field_varint(1, 101)
                + _field_varint(2, 1)
                + _field_varint(2, 2),
            )
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", repeated_finished_count)
            )
        )

    def test_rejects_unexpected_root_or_invalid_auxiliary_shape(self) -> None:
        unexpected_root = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
            + _field_varint(4, 9001)
            + _field_varint(5, 1)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", unexpected_root)
            )
        )

        malformed_active = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
            + _field_bytes(2, _field_varint(1, 202) + _field_varint(2, 7))
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", malformed_active)
            )
        )

        invalid_reinitialized = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
            + _field_varint(3, 0)
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", invalid_reinitialized)
            )
        )

    def test_rejects_finished_active_overlap(self) -> None:
        payload = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
            + _field_bytes(2, _field_varint(1, 101))
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", payload)
            )
        )

    def test_rejects_wrong_build_and_client_direction(self) -> None:
        payload = (
            _field_bytes(1, _field_varint(1, 101) + _field_varint(2, 1))
            + _field_varint(4, 9001)
        )
        self.assertIsNone(
            self._decoder(fingerprint="cd" * 32).decode(
                CapturedProtocolMessage("s1", "type.ankama.com/qst", payload)
            )
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage(
                    "s1",
                    "type.ankama.com/qst",
                    payload,
                    direction="client_to_server",
                )
            )
        )

    def test_delegates_other_messages_and_forwards_lifecycle_hooks(self) -> None:
        delegate = _Delegate()
        decoder = self._decoder(delegate)
        message = CapturedProtocolMessage("s1", "type.ankama.com/other", b"")
        self.assertIsNone(decoder.decode(message))
        self.assertEqual(delegate.messages, [message])
        decoder.session_closed("s1")
        decoder.reset()
        self.assertEqual(delegate.closed, ["s1"])
        self.assertEqual(delegate.reset_count, 1)


if __name__ == "__main__":
    unittest.main()
