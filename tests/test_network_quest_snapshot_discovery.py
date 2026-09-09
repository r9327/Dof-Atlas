from __future__ import annotations

import unittest

from app.network.quest_snapshot_discovery import discover_current_quest_snapshot
from app.network.transport import CapturedProtocolMessage


TYPE_URL = "type.ankama.com/qzx"


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


def _finished(quest_id: int, count: int = 1) -> bytes:
    return _v(1, quest_id) + _v(2, count)


def _active(quest_id: int) -> bytes:
    return _v(1, quest_id) + _b(2, _v(1, 77))


def _snapshot(
    *,
    player_id: int = 9001,
    finished: tuple[int, ...] = (101, 202),
    active: tuple[int, ...] = (303,),
    reinitialized: tuple[int, ...] = (),
    type_url: str = TYPE_URL,
    direction: str = "server_to_client",
    extra_root: bytes = b"",
) -> CapturedProtocolMessage:
    payload = b"".join(_b(1, _finished(quest_id)) for quest_id in finished)
    payload += b"".join(_b(2, _active(quest_id)) for quest_id in active)
    if reinitialized:
        payload += _b(3, b"".join(_varint(quest_id) for quest_id in reinitialized))
    payload += _v(4, player_id)
    payload += extra_root
    return CapturedProtocolMessage("s1", type_url, payload, direction=direction)


class QuestSnapshotDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.known = frozenset({101, 202, 303, 404})

    def discover(self, message: CapturedProtocolMessage):
        return discover_current_quest_snapshot(
            message,
            selected_character_id=9001,
            known_quest_ids=self.known,
        )

    def test_accepts_exact_historical_quests_event_shape_for_diagnostics_only(self) -> None:
        candidate = self.discover(_snapshot(reinitialized=(404,)))
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.type_url, TYPE_URL)
        self.assertEqual(candidate.player_id, 9001)
        self.assertEqual(candidate.finished_quest_ids, (101, 202))
        self.assertEqual(candidate.active_quest_ids, (303,))
        self.assertEqual(candidate.reinitialized_quest_ids, (404,))

    def test_rejects_wrong_player_unknown_ids_and_client_direction(self) -> None:
        self.assertIsNone(self.discover(_snapshot(player_id=9002)))
        self.assertIsNone(self.discover(_snapshot(finished=(101, 999999))))
        self.assertIsNone(self.discover(_snapshot(direction="client_to_server")))

    def test_rejects_too_few_finished_quests_or_finished_active_overlap(self) -> None:
        self.assertIsNone(self.discover(_snapshot(finished=(101,))))
        self.assertIsNone(self.discover(_snapshot(finished=(101, 202), active=(202,))))

    def test_rejects_extra_root_fields_and_non_current_aliases(self) -> None:
        self.assertIsNone(self.discover(_snapshot(extra_root=_v(5, 1))))
        self.assertIsNone(self.discover(_snapshot(type_url="ankama.com/qzx")))
        self.assertIsNone(self.discover(_snapshot(type_url="type.ankama.com/TOO-LONG")))

    def test_never_mistakes_known_non_snapshot_aliases_for_snapshot(self) -> None:
        for type_url in (
            "type.ankama.com/kvi",
            "type.ankama.com/kva",
            "type.ankama.com/lqn",
            "type.ankama.com/idr",
            "type.ankama.com/isf",
            "type.ankama.com/izu",
            "type.ankama.com/lry",
        ):
            with self.subTest(type_url=type_url):
                self.assertIsNone(self.discover(_snapshot(type_url=type_url)))

    def test_rejects_malformed_finished_entry(self) -> None:
        payload = _b(1, _v(1, 101) + _v(3, 7))
        payload += _b(1, _finished(202))
        payload += _v(4, 9001)
        self.assertIsNone(
            self.discover(CapturedProtocolMessage("s1", TYPE_URL, payload))
        )

    def test_rejects_finished_entry_without_positive_finished_count(self) -> None:
        missing_count = _b(1, _v(1, 101)) + _b(1, _finished(202)) + _v(4, 9001)
        self.assertIsNone(
            self.discover(CapturedProtocolMessage("s1", TYPE_URL, missing_count))
        )

        zero_count = _b(1, _finished(101, 0)) + _b(1, _finished(202)) + _v(4, 9001)
        self.assertIsNone(
            self.discover(CapturedProtocolMessage("s1", TYPE_URL, zero_count))
        )

        repeated_count = (
            _b(1, _v(1, 101) + _v(2, 1) + _v(2, 2))
            + _b(1, _finished(202))
            + _v(4, 9001)
        )
        self.assertIsNone(
            self.discover(CapturedProtocolMessage("s1", TYPE_URL, repeated_count))
        )


if __name__ == "__main__":
    unittest.main()
