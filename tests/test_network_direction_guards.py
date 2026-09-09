from __future__ import annotations

import unittest

from app.network.character_resolver import CharacterResolution
from app.network.protocol_calibration import CurrentProtocolCalibration
from app.network.transport import CapturedProtocolMessage
from app.quest_catalog import QuestCatalog, QuestRecord, QuestStep


BUILD = "ab" * 32


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


def _message(type_url: str, payload: bytes, *, direction: str = "server_to_client"):
    return CapturedProtocolMessage("s1", type_url, payload, direction=direction)


def _kvi(*, direction: str = "server_to_client"):
    details = _b(2, b"Atlas-Test")
    entry = _b(1, details) + _v(2, 9001)
    return _message("type.ankama.com/kvi", _b(1, entry), direction=direction)


def _kva(*, direction: str = "server_to_client"):
    return _message(
        "type.ankama.com/kva",
        _b(1, _b(1, _v(2, 9001))),
        direction=direction,
    )


def _idr(*, direction: str = "server_to_client"):
    payload = _b(3, _v(1, 1) + _v(2, 101))
    return _message("type.ankama.com/idr", payload, direction=direction)


def _idz(quest_id: int, step_id: int, *, direction: str = "server_to_client"):
    return _message(
        "type.ankama.com/idz",
        _v(1, quest_id) + _v(2, step_id),
        direction=direction,
    )


def _quest(quest_id: int, first_step: int, final_step: int) -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=f"Q{quest_id}",
        category="Test",
        level_min=1,
        level_max=200,
        start_criterion="",
        steps=[
            QuestStep(id=first_step, name="First", description=""),
            QuestStep(id=final_step, name="Final", description=""),
        ],
    )


class _Resolver:
    def resolve(self, character_name: str):
        if character_name == "Atlas-Test":
            return CharacterResolution(character_key="slot:3", label="Atlas-Test", slot=3)
        return None


class NetworkDirectionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = QuestCatalog(
            [
                _quest(101, 1001, 1002),
                _quest(202, 2001, 2002),
            ]
        )
        self.calibration = CurrentProtocolCalibration(
            build_sha256=BUILD,
            active_build_sha256_provider=lambda: BUILD,
            quest_catalog=self.catalog,
            character_resolver=_Resolver(),
        )

    def test_client_to_server_identity_journal_and_idz_never_calibrate(self) -> None:
        self.calibration.observe(_kvi(direction="client_to_server"))
        self.calibration.observe(_kva(direction="client_to_server"))
        outbound_identity = self.calibration.status()
        self.assertEqual(outbound_identity.reason, "awaiting_character_identity")
        self.assertEqual(outbound_identity.identified_session_count, 0)

        self.calibration.observe(_kvi())
        self.calibration.observe(_kva())
        self.calibration.observe(_idr(direction="client_to_server"))
        self.calibration.observe(_idz(101, 1002, direction="client_to_server"))
        outbound = self.calibration.observe(
            _idz(202, 2002, direction="client_to_server")
        )

        self.assertFalse(outbound.ready)
        self.assertEqual(outbound.reason, "awaiting_quest_journal")
        self.assertEqual(outbound.quest_journal_observation_count, 0)
        self.assertEqual(outbound.quest_journal_verified_count, 0)
        self.assertEqual(outbound.max_distinct_completion_count, 0)
        self.assertIsNone(outbound.certificate)

    def test_valid_server_to_client_idz_path_still_calibrates_after_outbound_noise(self) -> None:
        self.calibration.observe(_kvi(direction="client_to_server"))
        self.calibration.observe(_idz(101, 1002, direction="client_to_server"))

        self.calibration.observe(_kvi())
        self.calibration.observe(_kva())
        self.calibration.observe(_idr())
        self.calibration.observe(_idz(101, 1002))
        status = self.calibration.observe(_idz(202, 2002))

        self.assertTrue(status.ready)
        self.assertEqual(status.reason, "profile_calibrated")
        self.assertIsNotNone(status.certificate)
        self.assertEqual(status.certificate.verified_quest_ids, (101, 202))


if __name__ == "__main__":
    unittest.main()
