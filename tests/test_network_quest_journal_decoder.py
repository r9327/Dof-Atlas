from __future__ import annotations

import unittest

from app.network.mapped_decoder import StrictMappedProtocolDecoder
from app.network.quest_journal_decoder import QuestJournalDecoder, QuestJournalRule
from app.network.transport import CapturedProtocolMessage


BUILD = "ab" * 32
TYPE_URL = "type.ankama.com/idr"


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


def _v(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 0) + _varint(value)


def _b(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def _active(quest_id: int) -> bytes:
    body = _v(2, 5001)
    return _b(1, _b(2, body) + _v(3, quest_id))


def _finished(quest_id: int) -> bytes:
    return _b(3, _v(1, 1) + _v(2, quest_id))


def _packed(*quest_ids: int) -> bytes:
    return _b(4, b"".join(_varint(quest_id) for quest_id in quest_ids))


class QuestJournalDecoderTests(unittest.TestCase):
    def setUp(self) -> None:
        delegate = StrictMappedProtocolDecoder(
            mapping_version="3.6.10.10",
            active_version_provider=None,
            rules={},
            mapping_fingerprint=BUILD,
            active_fingerprint_provider=lambda: BUILD,
        )
        self.decoder = QuestJournalDecoder(
            delegate,
            QuestJournalRule(type_url=TYPE_URL),
            mapping_version="3.6.10.10",
            mapping_fingerprint=BUILD,
            active_fingerprint_provider=lambda: BUILD,
        )

    def decode(self, payload: bytes, **changes):
        values = {
            "session_id": "s1",
            "type_url": TYPE_URL,
            "payload": payload,
            "direction": "server_to_client",
        }
        values.update(changes)
        return self.decoder.decode(CapturedProtocolMessage(**values))

    def test_decodes_finished_entries_and_packed_additional_finished_ids(self) -> None:
        event = self.decode(_active(101) + _finished(202) + _finished(303) + _packed(404, 505))
        self.assertIsNotNone(event)
        self.assertTrue(event.verified)
        self.assertEqual(event.event_type, "quest_journal_snapshot")
        self.assertEqual(event.fields["active_quest_ids"], (101,))
        self.assertEqual(event.fields["finished_quest_ids"], (202, 303, 404, 505))

    def test_active_quests_are_never_promoted_to_finished(self) -> None:
        event = self.decode(_active(101) + _packed())
        self.assertIsNotNone(event)
        self.assertEqual(event.fields["active_quest_ids"], (101,))
        self.assertEqual(event.fields["finished_quest_ids"], ())

    def test_deduplicates_finished_ids_across_finished_lists(self) -> None:
        event = self.decode(_finished(202) + _packed(202, 303, 303))
        self.assertIsNotNone(event)
        self.assertEqual(event.fields["finished_quest_ids"], (202, 303))

    def test_rejects_malformed_finished_entry_and_unknown_root_fields(self) -> None:
        self.assertIsNone(self.decode(_b(3, _v(2, 202))))
        self.assertIsNone(self.decode(_finished(202) + _v(9, 1)))

    def test_rejects_non_positive_or_truncated_packed_finished_ids(self) -> None:
        self.assertIsNone(self.decode(_packed(0)))
        self.assertIsNone(self.decode(_b(4, b"\x80")))

    def test_rejects_wrong_direction_type_or_build(self) -> None:
        payload = _finished(202)
        self.assertIsNone(self.decode(payload, direction="client_to_server"))
        self.assertIsNone(self.decode(payload, type_url="type.ankama.com/idz"))

        delegate = StrictMappedProtocolDecoder(
            mapping_version="3.6.10.10",
            active_version_provider=None,
            rules={},
            mapping_fingerprint=BUILD,
            active_fingerprint_provider=lambda: "cd" * 32,
        )
        decoder = QuestJournalDecoder(
            delegate,
            QuestJournalRule(type_url=TYPE_URL),
            mapping_version="3.6.10.10",
            mapping_fingerprint=BUILD,
            active_fingerprint_provider=lambda: "cd" * 32,
        )
        self.assertIsNone(decoder.decode(CapturedProtocolMessage("s1", TYPE_URL, payload)))


if __name__ == "__main__":
    unittest.main()
