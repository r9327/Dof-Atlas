from __future__ import annotations

import unittest

from app.network.application_coordinator import NetworkApplicationCoordinator
from app.network.calibration_controller import ProtocolCalibrationControllerStatus
from app.network.character_resolver import CharacterResolution
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    dofus_361010_profile_digest,
)
from app.network.events import CharacterIdentifiedEvent, QuestJournalSnapshotEvent
from app.network.progress_bridge import EventApplicationResult
from app.network.protocol_calibration import (
    CurrentProtocolCalibration,
    QuestJournalCalibrationEvidence,
)
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


def _kvi(character_id: int = 9001, name: str = "Atlas-Test") -> CapturedProtocolMessage:
    details = _b(2, name.encode("utf-8"))
    entry = _b(1, details) + _v(2, character_id)
    return CapturedProtocolMessage("s1", "type.ankama.com/kvi", _b(1, entry))


def _kva(character_id: int = 9001) -> CapturedProtocolMessage:
    return CapturedProtocolMessage(
        "s1",
        "type.ankama.com/kva",
        _b(1, _b(1, _v(2, character_id))),
    )


def _idr(*quest_ids: int) -> CapturedProtocolMessage:
    payload = b"".join(_b(3, _v(1, 1) + _v(2, quest_id)) for quest_id in quest_ids)
    return CapturedProtocolMessage("s1", "type.ankama.com/idr", payload)


def _quest(quest_id: int) -> QuestRecord:
    return QuestRecord(
        id=quest_id,
        name=f"Q{quest_id}",
        category="Test",
        level_min=1,
        level_max=200,
        start_criterion="",
        steps=[QuestStep(id=quest_id * 10, name="Final", description="")],
    )


class _Resolver:
    def resolve(self, character_name: str):
        if character_name == "Atlas-Test":
            return CharacterResolution("slot:3", "Atlas-Test", 3)
        return None


class _CalibrationFake:
    def drain_identity_results(self):
        return []

    def __init__(self, evidence) -> None:
        self.is_running = True
        self.verified_journal_evidence = evidence
        self.verified_journal_evidences = (evidence,) if evidence is not None else ()
        self.verified_certificate = None
        self.poll_count = 0
        self.poll_status = ProtocolCalibrationControllerStatus(
            running=True,
            reason="awaiting_distinct_quest_completions",
            build_sha256=BUILD,
            quest_journal_observation_count=1,
            quest_journal_verified_count=2,
        )

    def poll(self) -> ProtocolCalibrationControllerStatus:
        self.poll_count += 1
        return self.poll_status


class NetworkCalibrationCatchupTests(unittest.TestCase):
    def test_reviewed_idr_remains_diagnostic_evidence_before_live_idz_is_calibrated(self) -> None:
        catalog = QuestCatalog([_quest(101), _quest(202)])
        calibration = CurrentProtocolCalibration(
            build_sha256=BUILD,
            active_build_sha256_provider=lambda: BUILD,
            quest_catalog=catalog,
            character_resolver=_Resolver(),
        )

        calibration.observe(_idr(101, 202))
        calibration.observe(_kvi())
        status = calibration.observe(_kva())

        self.assertFalse(status.ready)
        self.assertEqual(status.reason, "awaiting_distinct_quest_completions")
        self.assertIsNotNone(status.journal_evidence)
        self.assertEqual(status.journal_evidence.character_key, "slot:3")
        self.assertEqual(status.journal_evidence.character_id, 9001)
        self.assertEqual(status.journal_evidence.session_id, "s1")
        self.assertEqual(status.journal_evidence.journal_verified_quest_ids, (101, 202))
        self.assertEqual(status.journal_evidence.journal_observation_count, 1)
        self.assertIsNone(status.certificate)

    def test_coordinator_applies_verified_journal_once_while_live_calibration_continues(self) -> None:
        evidence = QuestJournalCalibrationEvidence(
            game_version=DOFUS_361010_PROFILE.game_version,
            build_sha256=BUILD,
            evidence_revision=DOFUS_361010_PROFILE.evidence_revision,
            source_commit=DOFUS_361010_PROFILE.source_commit,
            profile_digest=dofus_361010_profile_digest(),
            session_id="s1",
            character_key="slot:3",
            character_name="Atlas-Test",
            character_id=9001,
            quest_journal_type_url=DOFUS_361010_PROFILE.quest_journal_type_url,
            journal_verified_quest_ids=(101, 202),
            journal_observation_count=1,
        )
        calibration = _CalibrationFake(evidence)
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = calibration
        coordinator._context = (object(), object(), None)
        coordinator._context_ready = True
        coordinator._calibration_pending = True
        handled: list[object] = []

        class _Bridge:
            def handle(self, event):
                handled.append(event)
                return EventApplicationResult(
                    True,
                    isinstance(event, QuestJournalSnapshotEvent),
                    "applied",
                    "slot:3",
                )

        coordinator._bridge_for_calibration = _Bridge

        coordinator._apply_calibration_journal_evidence()
        coordinator._poll_calibration()
        coordinator._poll_calibration()

        self.assertTrue(coordinator._calibration_pending)
        self.assertEqual(calibration.poll_count, 2)
        self.assertEqual(len(handled), 2)
        self.assertIsInstance(handled[0], CharacterIdentifiedEvent)
        self.assertIsInstance(handled[1], QuestJournalSnapshotEvent)
        self.assertEqual(handled[1].finished_quest_ids, (101, 202))
        self.assertEqual(len(coordinator.drain_results()), 1)
        self.assertIs(coordinator.calibration.verified_journal_evidence, evidence)
        self.assertIsNone(coordinator.calibration.verified_certificate)

    def test_coordinator_applies_each_multi_account_journal_once(self) -> None:
        def evidence(session_id: str, key: str, name: str, character_id: int, quest_id: int):
            return QuestJournalCalibrationEvidence(
                game_version=DOFUS_361010_PROFILE.game_version,
                build_sha256=BUILD,
                evidence_revision=DOFUS_361010_PROFILE.evidence_revision,
                source_commit=DOFUS_361010_PROFILE.source_commit,
                profile_digest=dofus_361010_profile_digest(),
                session_id=session_id,
                character_key=key,
                character_name=name,
                character_id=character_id,
                quest_journal_type_url=DOFUS_361010_PROFILE.quest_journal_type_url,
                journal_verified_quest_ids=(quest_id,),
                journal_observation_count=1,
            )

        rows = (
            evidence("s1", "slot:3", "Atlas-Test", 9001, 101),
            evidence("s2", "slot:4", "Other-Test", 9002, 202),
        )
        calibration = _CalibrationFake(rows[0])
        calibration.verified_journal_evidences = rows
        coordinator = NetworkApplicationCoordinator(lambda: ())
        coordinator.calibration = calibration
        coordinator._context = (object(), object(), None)
        coordinator._context_ready = True
        handled: list[object] = []

        class _Bridge:
            def handle(self, event):
                handled.append(event)
                key = "slot:3" if event.session_id == "s1" else "slot:4"
                return EventApplicationResult(True, True, "applied", key)

        coordinator._bridge_for_calibration = _Bridge
        coordinator._apply_calibration_journal_evidence()
        coordinator._apply_calibration_journal_evidence()

        self.assertEqual(len(handled), 4)
        self.assertEqual(
            [event.finished_quest_ids for event in handled if isinstance(event, QuestJournalSnapshotEvent)],
            [(101,), (202,)],
        )
        self.assertEqual(
            [result.character_key for result in coordinator.drain_results()],
            ["slot:3", "slot:4"],
        )


if __name__ == "__main__":
    unittest.main()
