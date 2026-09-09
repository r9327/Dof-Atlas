from __future__ import annotations

import unittest

from app.network.normalizer import DecodedClientMessage
from app.network.quest_final_step_filter import FinalQuestStepEvidenceDecoder
from app.network.transport import CapturedProtocolMessage
from app.quest_catalog import QuestCatalog, QuestRecord, QuestStep


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


class _Delegate:
    def __init__(self, decoded: DecodedClientMessage | None) -> None:
        self.decoded = decoded
        self.closed: list[str] = []
        self.reset_count = 0

    def decode(self, _message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        return self.decoded

    def session_closed(self, session_id: str) -> None:
        self.closed.append(session_id)

    def reset(self) -> None:
        self.reset_count += 1


class FinalQuestStepEvidenceDecoderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = QuestCatalog([_quest(101, 1001, 1002), _quest(202, 2001)])
        self.raw = CapturedProtocolMessage("s1", "type.ankama.com/idz", b"")

    @staticmethod
    def completion(quest_id: int, step_id: int | None = None) -> DecodedClientMessage:
        fields = {"quest_id": quest_id}
        if step_id is not None:
            fields["validated_step_id"] = step_id
        return DecodedClientMessage(
            session_id="s1",
            event_type="quest_completed",
            fields=fields,
            event_id="evt",
            verified=True,
        )

    def test_final_step_evidence_is_passed_through(self) -> None:
        decoded = self.completion(101, 1002)
        result = FinalQuestStepEvidenceDecoder(_Delegate(decoded), self.catalog).decode(self.raw)
        self.assertIs(result, decoded)

    def test_non_final_step_evidence_is_rejected(self) -> None:
        decoded = self.completion(101, 1001)
        result = FinalQuestStepEvidenceDecoder(_Delegate(decoded), self.catalog).decode(self.raw)
        self.assertIsNone(result)

    def test_unknown_quest_or_step_is_rejected(self) -> None:
        for decoded in (
            self.completion(999999, 1002),
            self.completion(101, 999999),
        ):
            with self.subTest(fields=decoded.fields):
                self.assertIsNone(
                    FinalQuestStepEvidenceDecoder(_Delegate(decoded), self.catalog).decode(self.raw)
                )

    def test_direct_completion_without_step_evidence_remains_protocol_agnostic(self) -> None:
        decoded = self.completion(101)
        result = FinalQuestStepEvidenceDecoder(_Delegate(decoded), self.catalog).decode(self.raw)
        self.assertIs(result, decoded)

    def test_unrelated_event_is_not_modified(self) -> None:
        decoded = DecodedClientMessage(
            session_id="s1",
            event_type="quest_journal_snapshot",
            fields={"finished_quest_ids": (101,), "active_quest_ids": ()},
            event_id="journal",
            verified=True,
        )
        result = FinalQuestStepEvidenceDecoder(_Delegate(decoded), self.catalog).decode(self.raw)
        self.assertIs(result, decoded)

    def test_lifecycle_is_forwarded_to_inner_decoder(self) -> None:
        delegate = _Delegate(None)
        decoder = FinalQuestStepEvidenceDecoder(delegate, self.catalog)
        decoder.session_closed("s1")
        decoder.reset()
        self.assertEqual(delegate.closed, ["s1"])
        self.assertEqual(delegate.reset_count, 1)


if __name__ == "__main__":
    unittest.main()
