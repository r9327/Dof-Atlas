from __future__ import annotations

import unittest

from app.network.character_resolver import CharacterResolution
from app.network.current_protocol_profile import DOFUS_361010_PROFILE
from app.network.protocol_calibration import CurrentProtocolCalibration
from app.network.transport import CapturedProtocolMessage, TransportSessionClosed
from app.quest_catalog import QuestCatalog, QuestRecord, QuestStep


BUILD = "ab" * 32
SNAPSHOT_TYPE = "type.ankama.com/qzx"


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


def _kvi(character_id: int = 9001, name: str = "Atlas-Test", session_id: str = "s1") -> CapturedProtocolMessage:
    details = _b(2, name.encode("utf-8"))
    entry = _b(1, details) + _v(2, character_id)
    return CapturedProtocolMessage(session_id, "type.ankama.com/kvi", _b(1, entry))


def _kva(character_id: int = 9001, session_id: str = "s1") -> CapturedProtocolMessage:
    payload = _b(1, _b(1, _v(2, character_id)))
    return CapturedProtocolMessage(session_id, "type.ankama.com/kva", payload)


def _idz(quest_id: int, step_id: int, session_id: str = "s1") -> CapturedProtocolMessage:
    return CapturedProtocolMessage(
        session_id,
        "type.ankama.com/idz",
        _v(1, quest_id) + _v(2, step_id),
    )


def _idr(
    *,
    finished: tuple[int, ...] = (303,),
    active: tuple[int, ...] = (),
    packed_finished: tuple[int, ...] = (),
    session_id: str = "s1",
) -> CapturedProtocolMessage:
    payload = b""
    for quest_id in active:
        body = _v(2, 5001)
        payload += _b(1, _b(2, body) + _v(3, quest_id))
    for quest_id in finished:
        payload += _b(3, _v(1, 1) + _v(2, quest_id))
    payload += _b(4, b"".join(_varint(quest_id) for quest_id in packed_finished))
    return CapturedProtocolMessage(session_id, "type.ankama.com/idr", payload)


def _snapshot(
    type_url: str = SNAPSHOT_TYPE,
    *,
    character_id: int = 9001,
    quest_ids: tuple[int, ...] = (101, 202),
    session_id: str = "s1",
) -> CapturedProtocolMessage:
    payload = b"".join(
        _b(1, _v(1, quest_id) + _v(2, 1))
        for quest_id in quest_ids
    )
    payload += _v(4, character_id)
    return CapturedProtocolMessage(session_id, type_url, payload)


def _quest(quest_id: int, *step_ids: int) -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=f"Q{quest_id}",
        category="Test",
        level_min=1,
        level_max=200,
        start_criterion="",
        steps=[QuestStep(id=step_id, name=f"S{step_id}", description="") for step_id in step_ids],
    )


class _Resolver:
    def resolve(self, character_name: str):
        if character_name == "Atlas-Test":
            return CharacterResolution(character_key="slot:3", label="Atlas-Test", slot=3)
        if character_name == "Other-Test":
            return CharacterResolution(character_key="slot:4", label="Other-Test", slot=4)
        return None


class ProtocolCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.active_build = BUILD
        self.catalog = QuestCatalog(
            [
                _quest(101, 1001, 1002),
                _quest(202, 2001, 2002),
                _quest(303, 3001),
            ]
        )
        self.calibration = CurrentProtocolCalibration(
            build_sha256=BUILD,
            active_build_sha256_provider=lambda: self.active_build,
            quest_catalog=self.catalog,
            character_resolver=_Resolver(),
        )

    def identify(self, *, session_id: str = "s1") -> None:
        self.calibration.observe(_kvi(session_id=session_id))
        self.calibration.observe(_kva(session_id=session_id))

    def test_login_journal_before_identity_then_final_step_completions_calibrate(self) -> None:
        self.assertEqual(self.calibration.status().reason, "awaiting_character_identity")
        before_identity = self.calibration.observe(
            _idr(finished=(303,), active=(101,), packed_finished=(202,))
        )
        self.assertEqual(before_identity.reason, "awaiting_character_identity")

        self.identify()
        identified = self.calibration.status()
        self.assertEqual(identified.reason, "awaiting_distinct_quest_completions")
        self.assertEqual(identified.quest_journal_observation_count, 1)
        self.assertEqual(identified.quest_journal_verified_count, 2)

        first_completion = self.calibration.observe(_idz(101, 1002))
        self.assertFalse(first_completion.ready)
        self.assertEqual(first_completion.reason, "awaiting_distinct_quest_completions")
        self.assertEqual(first_completion.max_distinct_completion_count, 1)

        second_completion = self.calibration.observe(_idz(202, 2002))
        self.assertTrue(second_completion.ready)
        self.assertEqual(second_completion.reason, "profile_calibrated")
        certificate = second_completion.certificate
        self.assertIsNotNone(certificate)
        self.assertEqual(certificate.verified_quest_ids, (101, 202))
        self.assertEqual(certificate.character_name, "Atlas-Test")
        self.assertEqual(certificate.session_id, "s1")
        self.assertEqual(certificate.quest_journal_type_url, DOFUS_361010_PROFILE.quest_journal_type_url)
        self.assertEqual(certificate.journal_verified_quest_ids, (202, 303))
        self.assertEqual(certificate.journal_observation_count, 1)
        self.assertEqual(certificate.finished_quests_snapshot_type_url, "")
        self.assertEqual(certificate.snapshot_verified_quest_ids, ())
        self.assertEqual(certificate.snapshot_observation_count, 0)

    def test_non_final_idz_never_counts_as_completion(self) -> None:
        self.calibration.observe(_idr())
        self.identify()
        status = self.calibration.observe(_idz(101, 1001))
        self.assertFalse(status.ready)
        self.assertEqual(status.max_distinct_completion_count, 0)
        self.assertEqual(status.reason, "awaiting_distinct_quest_completions")

    def test_two_live_completions_without_journal_wait_for_journal(self) -> None:
        self.identify()
        self.calibration.observe(_idz(101, 1002))
        status = self.calibration.observe(_idz(202, 2002))
        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "awaiting_quest_journal")
        self.assertEqual(status.max_distinct_completion_count, 2)

        status = self.calibration.observe(_idr(finished=(101, 202)))
        self.assertTrue(status.ready)
        self.assertEqual(status.reason, "profile_calibrated")

    def test_empty_valid_journal_is_still_exact_build_evidence(self) -> None:
        self.calibration.observe(_idr(finished=(), active=(), packed_finished=()))
        self.identify()
        self.calibration.observe(_idz(101, 1002))
        status = self.calibration.observe(_idz(202, 2002))
        self.assertTrue(status.ready)
        self.assertEqual(status.quest_journal_observation_count, 1)
        self.assertEqual(status.quest_journal_verified_count, 0)
        self.assertEqual(status.certificate.journal_verified_quest_ids, ())

    def test_shape_only_legacy_snapshot_is_never_calibration_evidence(self) -> None:
        self.calibration.observe(_idr())
        self.identify()
        discovery_status = self.calibration.observe(_snapshot())
        self.assertEqual(discovery_status.reason, "awaiting_distinct_quest_completions")
        self.assertEqual(discovery_status.snapshot_candidate_count, 0)
        self.assertEqual(discovery_status.snapshot_candidate_type_url, "")

        self.calibration.observe(_idz(101, 1002))
        status = self.calibration.observe(_idz(202, 2002))
        self.assertTrue(status.ready)
        certificate = status.certificate
        self.assertIsNotNone(certificate)
        self.assertEqual(certificate.build_sha256, BUILD)
        self.assertEqual(certificate.game_version, "3.6.10.10")
        self.assertEqual(certificate.character_key, "slot:3")
        self.assertEqual(certificate.character_id, 9001)
        self.assertEqual(certificate.finished_quests_snapshot_type_url, "")
        self.assertEqual(certificate.snapshot_verified_quest_ids, ())
        self.assertEqual(certificate.snapshot_observation_count, 0)

    def test_journal_on_different_session_cannot_authorize_character(self) -> None:
        self.calibration.observe(_idr(session_id="s2"))
        self.identify(session_id="s1")
        self.calibration.observe(_idz(101, 1002))
        status = self.calibration.observe(_idz(202, 2002))
        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "awaiting_quest_journal")
        self.assertEqual(status.quest_journal_observation_count, 0)

    def test_completion_before_identity_does_not_count(self) -> None:
        self.calibration.observe(_idz(101, 1002))
        self.calibration.observe(_idr())
        self.identify()
        status = self.calibration.status()
        self.assertEqual(status.max_distinct_completion_count, 0)
        self.assertEqual(status.quest_journal_observation_count, 1)
        self.assertFalse(status.ready)

    def test_unknown_quest_id_does_not_count_as_live_completion(self) -> None:
        self.calibration.observe(_idr())
        self.identify()
        status = self.calibration.observe(_idz(999999, 999001))
        self.assertEqual(status.max_distinct_completion_count, 0)
        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "awaiting_distinct_quest_completions")

    def test_session_close_discards_journal_and_partial_calibration(self) -> None:
        self.calibration.observe(_idr())
        self.identify()
        self.calibration.observe(_idz(101, 1002))
        status = self.calibration.observe(TransportSessionClosed("s1"))
        self.assertEqual(status.reason, "awaiting_character_identity")
        self.assertEqual(status.max_distinct_completion_count, 0)
        self.assertEqual(status.quest_journal_observation_count, 0)
        self.assertEqual(status.snapshot_candidate_count, 0)

    def test_build_change_invalidates_all_evidence_until_reset(self) -> None:
        self.calibration.observe(_idr())
        self.identify()
        self.calibration.observe(_idz(101, 1002))
        self.active_build = "cd" * 32
        status = self.calibration.observe(_idz(202, 2002))
        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "build_changed")
        self.assertEqual(status.identified_session_count, 0)

        self.active_build = BUILD
        self.assertEqual(self.calibration.status().reason, "build_changed")
        self.calibration.reset()
        self.assertEqual(self.calibration.status().reason, "awaiting_character_identity")

    def test_different_sessions_cannot_combine_quest_evidence(self) -> None:
        self.calibration.observe(_idr(session_id="s1"))
        self.identify(session_id="s1")
        self.calibration.observe(_idz(101, 1002, session_id="s1"))
        self.calibration.observe(_idr(session_id="s2"))
        self.calibration.observe(_kvi(session_id="s2"))
        self.calibration.observe(_kva(session_id="s2"))
        self.calibration.observe(_idz(202, 2002, session_id="s2"))
        status = self.calibration.status()
        self.assertFalse(status.ready)
        self.assertEqual(status.max_distinct_completion_count, 1)

    def test_latest_identified_session_supplies_journal_evidence(self) -> None:
        self.calibration.observe(_idr(finished=(303,), session_id="s1"))
        self.identify(session_id="s1")
        self.calibration.observe(_idr(finished=(202,), session_id="s2"))
        self.identify(session_id="s2")

        status = self.calibration.status()

        self.assertIsNotNone(status.journal_evidence)
        self.assertEqual(status.journal_evidence.session_id, "s2")
        self.assertEqual(status.journal_evidence.journal_verified_quest_ids, (202,))

    def test_all_simultaneous_characters_supply_separate_journal_evidence(self) -> None:
        self.calibration.observe(_idr(finished=(303,), session_id="s1"))
        self.identify(session_id="s1")
        self.calibration.observe(_idr(finished=(202,), session_id="s2"))
        self.calibration.observe(_kvi(9002, "Other-Test", "s2"))
        status = self.calibration.observe(_kva(9002, "s2"))

        evidence_by_session = {
            evidence.session_id: evidence for evidence in status.journal_evidences
        }
        self.assertEqual(set(evidence_by_session), {"s1", "s2"})
        self.assertEqual(evidence_by_session["s1"].character_key, "slot:3")
        self.assertEqual(evidence_by_session["s1"].journal_verified_quest_ids, (303,))
        self.assertEqual(evidence_by_session["s2"].character_key, "slot:4")
        self.assertEqual(evidence_by_session["s2"].journal_verified_quest_ids, (202,))

    def test_reidentification_clears_old_character_evidence(self) -> None:
        self.calibration.observe(_idr())
        self.identify()
        self.calibration.observe(_idz(101, 1002))
        self.identify()
        status = self.calibration.status()
        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "awaiting_quest_journal")
        self.assertEqual(status.max_distinct_completion_count, 0)
        self.assertEqual(status.quest_journal_observation_count, 0)

    def test_unresolved_character_never_becomes_calibrated(self) -> None:
        self.calibration.observe(_idr())
        self.calibration.observe(_kvi(name="Other"))
        self.calibration.observe(_kva())
        self.calibration.observe(_idz(101, 1002))
        self.calibration.observe(_idz(202, 2002))
        status = self.calibration.status()
        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "awaiting_character_identity")


if __name__ == "__main__":
    unittest.main()
