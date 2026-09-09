from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.network.character_resolver import CharacterResolution
from app.network.diagnostics import protocol_payload_summary
from app.network.events import (
    CharacterIdentifiedEvent,
    QuestCompletedEvent,
    QuestJournalSnapshotEvent,
    QuestObjectiveCompletedEvent,
)
from app.network.instrumentation import InstrumentedNetworkProgressBridge
from app.quest_catalog import QuestCatalog, QuestObjective, QuestRecord, QuestStep


class _Resolver:
    def __init__(self, mapping: dict[str, tuple[str, int]]) -> None:
        self.mapping = dict(mapping)

    def resolve_for_session(self, character_name: str, session_id: str):
        row = self.mapping.get(character_name)
        if row is None:
            return None
        key, slot = row
        return CharacterResolution(key, character_name, slot)

    def resolve(self, character_name: str):
        return self.resolve_for_session(character_name, "")


class _QuestProgress:
    path = Path("tests-network-progress.json")

    def __init__(self) -> None:
        self.completed: dict[str, set[int]] = {}
        self.objectives: dict[str, dict[int, set[int]]] = {}
        self.write_count = 0

    def completed_quest_ids(self, character_key: str):
        return tuple(sorted(self.completed.get(character_key, set())))

    def is_quest_completed(self, character_key: str, quest_id: int) -> bool:
        return int(quest_id) in self.completed.get(character_key, set())

    def set_quest_completed(self, character_key: str, quest_id: int, completed: bool) -> bool:
        values = self.completed.setdefault(character_key, set())
        quest_id = int(quest_id)
        before = set(values)
        if completed:
            values.add(quest_id)
        else:
            values.discard(quest_id)
        changed = values != before
        if changed:
            self.write_count += 1
        return changed

    def set_quests_completed(self, character_key: str, quest_ids, completed: bool) -> bool:
        values = self.completed.setdefault(character_key, set())
        before = set(values)
        normalized = {int(value) for value in quest_ids}
        if completed:
            values.update(normalized)
        else:
            values.difference_update(normalized)
        changed = values != before
        if changed:
            self.write_count += 1
        return changed

    def is_objective_completed(self, character_key: str, quest_id: int, objective_id: int) -> bool:
        return int(objective_id) in self.objectives.get(character_key, {}).get(int(quest_id), set())

    def set_objective_completed(
        self,
        character_key: str,
        quest_id: int,
        objective_id: int,
        completed: bool,
    ) -> bool:
        quest_rows = self.objectives.setdefault(character_key, {})
        values = quest_rows.setdefault(int(quest_id), set())
        before = set(values)
        if completed:
            values.add(int(objective_id))
        else:
            values.discard(int(objective_id))
        changed = values != before
        if changed:
            self.write_count += 1
        return changed


@dataclass
class _AchievementState:
    completed_achievements: set[int] = field(default_factory=set)


class _AchievementProgress:
    def __init__(self) -> None:
        self.states: dict[str, _AchievementState] = {}
        self.objectives: dict[str, dict[int, set[int]]] = {}
        self.sync_calls: list[str] = []

    def state_for(self, character_key: str) -> _AchievementState:
        return self.states.setdefault(character_key, _AchievementState())

    def sync_from_quest_progress(
        self,
        character_key: str,
        achievement_provider,
        quest_progress_service,
        guide_provider=None,
    ) -> bool:
        self.sync_calls.append(character_key)
        return False

    def is_achievement_completed(self, character_key: str, achievement_id: int) -> bool:
        return int(achievement_id) in self.state_for(character_key).completed_achievements

    def set_achievement_completed(self, character_key: str, achievement_id: int, completed: bool) -> bool:
        values = self.state_for(character_key).completed_achievements
        before = set(values)
        if completed:
            values.add(int(achievement_id))
        else:
            values.discard(int(achievement_id))
        return values != before

    def is_objective_completed(self, character_key: str, achievement_id: int, objective_id: int) -> bool:
        return int(objective_id) in self.objectives.get(character_key, {}).get(int(achievement_id), set())

    def set_objective_completed(
        self,
        character_key: str,
        achievement_id: int,
        objective_id: int,
        completed: bool,
    ) -> bool:
        achievement_rows = self.objectives.setdefault(character_key, {})
        values = achievement_rows.setdefault(int(achievement_id), set())
        before = set(values)
        if completed:
            values.add(int(objective_id))
        else:
            values.discard(int(objective_id))
        return values != before


class _AchievementProvider:
    def get_by_id(self, achievement_id: int):
        return None


def _quest(quest_id: int, *, objective_id: int | None = None) -> QuestRecord:
    steps = []
    if objective_id is not None:
        steps = [
            QuestStep(
                id=quest_id * 10,
                name=f"Step {quest_id}",
                description="",
                objectives=[
                    QuestObjective(
                        id=objective_id,
                        text=f"Objective {objective_id}",
                        type_id=1,
                    )
                ],
            )
        ]
    return QuestRecord(
        id=quest_id,
        name=f"Quest {quest_id}",
        category="Test",
        level_min=1,
        level_max=200,
        start_criterion="",
        steps=steps,
    )


def _bridge(*, objective: bool = False):
    quests = [_quest(value, objective_id=101 if objective and value == 1 else None) for value in range(1, 6)]
    quest_progress = _QuestProgress()
    achievement_progress = _AchievementProgress()
    bridge = InstrumentedNetworkProgressBridge(
        quest_catalog=QuestCatalog(quests),
        quest_progress_service=quest_progress,
        achievement_progress_service=achievement_progress,
        achievement_provider=_AchievementProvider(),
        character_resolver=_Resolver({"Alice": ("slot:1", 1), "Bob": ("slot:2", 2)}),
        logger=logging.getLogger("tests.network.progress.instrumentation"),
    )
    return bridge, quest_progress, achievement_progress


def _identify(bridge, *, session: str, name: str, character_id: int):
    return bridge.handle(
        CharacterIdentifiedEvent(
            session_id=session,
            event_id=f"identity:{name}:{character_id}",
            reliable=True,
            character_name=name,
            character_id=character_id,
        )
    )


def _journal(bridge, *, session: str, event_id: str, finished: tuple[int, ...], active=()):
    return bridge.handle(
        QuestJournalSnapshotEvent(
            session_id=session,
            event_id=event_id,
            reliable=True,
            finished_quest_ids=finished,
            active_quest_ids=tuple(active),
        )
    )


def _encode_varint(value: int) -> bytes:
    value = int(value)
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            output.append(byte | 0x80)
        else:
            output.append(byte)
            return bytes(output)


def _protobuf_varint(field_number: int, value: int) -> bytes:
    return _encode_varint((int(field_number) << 3) | 0) + _encode_varint(value)


def test_history_validates_only_explicit_finished_quests(monkeypatch):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    bridge, progress, achievements = _bridge()
    assert _identify(bridge, session="s1", name="Alice", character_id=1001).accepted

    result = _journal(
        bridge,
        session="s1",
        event_id="journal:1",
        finished=(1, 2, 3),
        active=(4,),
    )

    assert result.accepted
    assert result.reason == "quest_journal_reconciled"
    assert progress.completed_quest_ids("slot:1") == (1, 2, 3)
    assert 4 not in progress.completed.get("slot:1", set())
    assert 5 not in progress.completed.get("slot:1", set())
    assert achievements.sync_calls == ["slot:1"]


def test_unknown_network_quest_never_maps_by_index_and_logs_failure(monkeypatch, caplog):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    caplog.set_level(logging.INFO, logger="tests.network.progress.instrumentation")
    bridge, progress, _ = _bridge()
    _identify(bridge, session="s1", name="Alice", character_id=1001)

    result = _journal(
        bridge,
        session="s1",
        event_id="journal:unknown",
        finished=(999999,),
    )

    assert result.accepted
    assert result.reason == "quest_journal_no_known_finished_quests"
    assert progress.completed_quest_ids("slot:1") == ()
    assert "[QUEST_MATCH][FAILED]" in caplog.text
    assert "999999" in caplog.text
    assert "network_id_absent_from_atlas_catalog" in caplog.text


def test_two_characters_never_share_network_quest_history(monkeypatch):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    bridge, progress, _ = _bridge()
    _identify(bridge, session="s1", name="Alice", character_id=1001)
    _journal(bridge, session="s1", event_id="journal:alice", finished=(1, 2, 3))

    _identify(bridge, session="s2", name="Bob", character_id=2002)
    _journal(bridge, session="s2", event_id="journal:bob", finished=(4, 5))

    assert progress.completed_quest_ids("slot:1") == (1, 2, 3)
    assert progress.completed_quest_ids("slot:2") == (4, 5)


def test_live_quest_completion_applies_immediately_and_syncs(monkeypatch):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    bridge, progress, achievements = _bridge()
    _identify(bridge, session="s1", name="Alice", character_id=1001)

    result = bridge.handle(
        QuestCompletedEvent(
            session_id="s1",
            event_id="quest-live:2",
            reliable=True,
            quest_id=2,
            validated_step_id=20,
        )
    )

    assert result.accepted and result.changed
    assert result.reason == "quest_completed"
    assert progress.completed_quest_ids("slot:1") == (2,)
    assert achievements.sync_calls == ["slot:1"]
    assert progress.write_count == 1


def test_completed_objective_does_not_complete_whole_quest(monkeypatch):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    bridge, progress, achievements = _bridge(objective=True)
    _identify(bridge, session="s1", name="Alice", character_id=1001)

    result = bridge.handle(
        QuestObjectiveCompletedEvent(
            session_id="s1",
            event_id="quest-objective:1:101",
            reliable=True,
            quest_id=1,
            objective_id=101,
        )
    )

    assert result.accepted and result.changed
    assert result.reason == "quest_objective_completed"
    assert progress.is_objective_completed("slot:1", 1, 101)
    assert not progress.is_quest_completed("slot:1", 1)
    assert achievements.sync_calls == []


def test_repeated_history_is_idempotent_even_with_new_event_id(monkeypatch):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    bridge, progress, achievements = _bridge()
    _identify(bridge, session="s1", name="Alice", character_id=1001)

    first = _journal(bridge, session="s1", event_id="journal:1", finished=(1, 2, 3))
    writes_after_first = progress.write_count
    second = _journal(bridge, session="s1", event_id="journal:2", finished=(1, 2, 3))

    assert first.accepted and first.changed
    assert second.accepted and not second.changed
    assert second.reason == "quest_journal_already_reconciled"
    assert progress.completed_quest_ids("slot:1") == (1, 2, 3)
    assert progress.write_count == writes_after_first
    assert achievements.sync_calls == ["slot:1", "slot:1"]


def test_deep_debug_exposes_achievement_numeric_candidates_without_assigning_semantics(monkeypatch, caplog):
    monkeypatch.delenv("ATLAS_NETWORK_DEBUG", raising=False)
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG_DEEP", "1")
    caplog.set_level(logging.INFO, logger="tests.network.progress.instrumentation")
    bridge, progress, _ = _bridge()
    _identify(bridge, session="s1", name="Alice", character_id=1001)

    payload = _protobuf_varint(1, 742) + _protobuf_varint(2, 18456)
    summary = protocol_payload_summary(payload)

    assert summary["payload_scalar_samples"] == {"1": (742,), "2": (18456,)}
    assert progress.completed_quest_ids("slot:1") == ()
    assert "[NETWORK][ACHIEVEMENTS][SUMMARY_UNAVAILABLE]" in caplog.text
    assert "no_verified_achievement_summary_decoder" in caplog.text


def test_deep_debug_exposes_level_numeric_candidate_without_false_application(monkeypatch, caplog):
    monkeypatch.delenv("ATLAS_NETWORK_DEBUG", raising=False)
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG_DEEP", "1")
    caplog.set_level(logging.INFO, logger="tests.network.progress.instrumentation")
    bridge, progress, _ = _bridge()
    _identify(bridge, session="s1", name="Alice", character_id=1001)

    summary = protocol_payload_summary(_protobuf_varint(3, 200))

    assert summary["payload_scalar_samples"] == {"3": (200,)}
    assert progress.completed_quest_ids("slot:1") == ()
    assert "[NETWORK][LEVEL][UNAVAILABLE]" in caplog.text
    assert "no_verified_level_decoder" in caplog.text


def test_regular_debug_does_not_dump_scalar_values(monkeypatch):
    monkeypatch.setenv("ATLAS_NETWORK_DEBUG", "1")
    monkeypatch.delenv("ATLAS_NETWORK_DEBUG_DEEP", raising=False)

    summary = protocol_payload_summary(_protobuf_varint(1, 18456))

    assert "payload_scalar_samples" not in summary
    assert "payload_hex" not in summary
