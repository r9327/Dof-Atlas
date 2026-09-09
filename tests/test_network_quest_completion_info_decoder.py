from __future__ import annotations

import unittest

from app.network.normalizer import DecodedClientMessage
from app.network.quest_completion_info_decoder import (
    QuestCompletionInfoDecoder,
    QuestCompletionInfoRule,
)
from app.network.transport import CapturedProtocolMessage


FINGERPRINT = "ab" * 32
TYPE_URL = "type.ankama.com/lqn"


def _varint(value: int) -> bytes:
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


def _field_varint(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 0) + _varint(value)


def _field_bytes(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def _completion_payload(quest_id: str = "1234", *, message_id: int = 56, message_type: int | None = None) -> bytes:
    rows = []
    if message_type is not None:
        rows.append(_field_varint(1, message_type))
    rows.append(_field_varint(2, message_id))
    rows.append(_field_bytes(4, quest_id.encode("utf-8")))
    return b"".join(rows)


class _Delegate:
    def __init__(self) -> None:
        self.messages: list[CapturedProtocolMessage] = []
        self.closed: list[str] = []
        self.reset_count = 0

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        self.messages.append(message)
        return None

    def session_closed(self, session_id: str) -> None:
        self.closed.append(session_id)

    def reset(self) -> None:
        self.reset_count += 1


class QuestCompletionInfoDecoderTests(unittest.TestCase):
    def _decoder(self, delegate: _Delegate | None = None, *, fingerprint: str = FINGERPRINT):
        return QuestCompletionInfoDecoder(
            delegate or _Delegate(),
            QuestCompletionInfoRule(
                type_url=TYPE_URL,
                message_type_field=1,
                completion_message_type=0,
                message_id_field=2,
                completion_message_id=56,
                parameters_field=4,
                quest_id_parameter_index=0,
            ),
            mapping_version="3.6.10.10",
            mapping_fingerprint=FINGERPRINT,
            active_fingerprint_provider=lambda: fingerprint,
        )

    def test_decodes_current_quest_completed_message_when_zero_type_is_omitted(self) -> None:
        decoded = self._decoder().decode(
            CapturedProtocolMessage("s1", TYPE_URL, _completion_payload("1234"))
        )
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.verified)
        self.assertEqual(decoded.event_type, "quest_completed")
        self.assertEqual(decoded.fields, {"quest_id": 1234})
        self.assertTrue(decoded.event_id.startswith("proto:"))

    def test_accepts_explicit_zero_type_but_rejects_nonzero_type(self) -> None:
        explicit_zero = self._decoder().decode(
            CapturedProtocolMessage("s1", TYPE_URL, _completion_payload("1234", message_type=0))
        )
        self.assertIsNotNone(explicit_zero)

        warning = self._decoder().decode(
            CapturedProtocolMessage("s1", TYPE_URL, _completion_payload("1234", message_type=1))
        )
        self.assertIsNone(warning)

    def test_quest_start_and_update_message_ids_never_complete_a_quest(self) -> None:
        for message_id in (54, 55):
            with self.subTest(message_id=message_id):
                self.assertIsNone(
                    self._decoder().decode(
                        CapturedProtocolMessage(
                            "s1",
                            TYPE_URL,
                            _completion_payload("1234", message_id=message_id),
                        )
                    )
                )

    def test_rejects_missing_or_repeated_message_id(self) -> None:
        missing = _field_bytes(4, b"1234")
        self.assertIsNone(self._decoder().decode(CapturedProtocolMessage("s1", TYPE_URL, missing)))

        repeated = _field_varint(2, 56) + _field_varint(2, 56) + _field_bytes(4, b"1234")
        self.assertIsNone(self._decoder().decode(CapturedProtocolMessage("s1", TYPE_URL, repeated)))

    def test_rejects_missing_nonnumeric_zero_or_unicode_quest_id(self) -> None:
        missing = _field_varint(2, 56)
        self.assertIsNone(self._decoder().decode(CapturedProtocolMessage("s1", TYPE_URL, missing)))

        for value in ("", "0", "-1", "12.5", "quest-12", "１２３４"):
            with self.subTest(value=value):
                self.assertIsNone(
                    self._decoder().decode(
                        CapturedProtocolMessage("s1", TYPE_URL, _completion_payload(value))
                    )
                )

    def test_uses_configured_parameter_index_without_guessing(self) -> None:
        rule = QuestCompletionInfoRule(
            type_url=TYPE_URL,
            message_type_field=1,
            completion_message_type=0,
            message_id_field=2,
            completion_message_id=56,
            parameters_field=4,
            quest_id_parameter_index=1,
        )
        decoder = QuestCompletionInfoDecoder(
            _Delegate(),
            rule,
            mapping_version="3.6.10.10",
            mapping_fingerprint=FINGERPRINT,
            active_fingerprint_provider=lambda: FINGERPRINT,
        )
        payload = _field_varint(2, 56) + _field_bytes(4, b"ignored") + _field_bytes(4, b"4321")
        decoded = decoder.decode(CapturedProtocolMessage("s1", TYPE_URL, payload))
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.fields["quest_id"], 4321)

    def test_rejects_wrong_build_and_client_direction(self) -> None:
        payload = _completion_payload("1234")
        self.assertIsNone(
            self._decoder(fingerprint="cd" * 32).decode(
                CapturedProtocolMessage("s1", TYPE_URL, payload)
            )
        )
        self.assertIsNone(
            self._decoder().decode(
                CapturedProtocolMessage(
                    "s1",
                    TYPE_URL,
                    payload,
                    direction="client_to_server",
                )
            )
        )

    def test_delegates_other_opcodes_and_forwards_lifecycle(self) -> None:
        delegate = _Delegate()
        decoder = self._decoder(delegate)
        message = CapturedProtocolMessage("s1", "type.ankama.com/other", b"")
        self.assertIsNone(decoder.decode(message))
        self.assertEqual(delegate.messages, [message])

        decoder.session_closed("s1")
        decoder.reset()
        self.assertEqual(delegate.closed, ["s1"])
        self.assertEqual(delegate.reset_count, 1)

    def test_rule_rejects_overlapping_semantic_fields(self) -> None:
        with self.assertRaises(ValueError):
            QuestCompletionInfoRule(
                type_url=TYPE_URL,
                message_type_field=1,
                completion_message_type=0,
                message_id_field=2,
                completion_message_id=56,
                parameters_field=2,
            )


if __name__ == "__main__":
    unittest.main()
