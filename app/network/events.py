from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkEvent:
    """Normalized local client event.

    ``reliable`` is deliberately false by default. Only a version-matched,
    validated decoder is allowed to set it to true before an event can mutate
    player progression.
    """

    session_id: str
    event_id: str = ""
    reliable: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionClosedEvent(NetworkEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterIdentifiedEvent(NetworkEvent):
    character_name: str
    character_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestStartedEvent(NetworkEvent):
    quest_id: int


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestObjectiveCompletedEvent(NetworkEvent):
    quest_id: int
    objective_id: int


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestCompletedEvent(NetworkEvent):
    quest_id: int
    # Some protocols expose a direct one-shot completion. The reviewed current
    # Dofus profile instead exposes idz: the server validates one concrete quest
    # step. When present, Atlas must prove this is the quest's final local step
    # before turning the evidence into persistent quest completion.
    validated_step_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestJournalSnapshotEvent(NetworkEvent):
    """Reviewed current quest journal scoped to an already identified session.

    ``finished_quest_ids`` is additive only: Atlas never clears local/manual
    progress because an id is absent from one journal. ``active_quest_ids`` is
    retained only as structural evidence and must never be promoted to done.
    The wire journal has no player id, so the progress bridge must require a
    verified CharacterIdentifiedEvent route for this exact transport session.
    """

    finished_quest_ids: tuple[int, ...]
    active_quest_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class FinishedQuestsSnapshotEvent(NetworkEvent):
    """Legacy historical finished-quest snapshot contract.

    This event remains for compatibility/tests but current runtime keeps its
    mutation path closed because the historical QuestsEvent alias was learned
    from payload shape rather than an independently reviewed current opcode.
    """

    quest_ids: tuple[int, ...]
    player_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AchievementObjectiveCompletedEvent(NetworkEvent):
    achievement_id: int
    objective_id: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AchievementCompletedEvent(NetworkEvent):
    achievement_id: int


BusinessNetworkEvent: TypeAlias = (
    SessionClosedEvent
    | CharacterIdentifiedEvent
    | QuestStartedEvent
    | QuestObjectiveCompletedEvent
    | QuestCompletedEvent
    | QuestJournalSnapshotEvent
    | FinishedQuestsSnapshotEvent
    | AchievementObjectiveCompletedEvent
    | AchievementCompletedEvent
)


__all__ = [
    "AchievementCompletedEvent",
    "AchievementObjectiveCompletedEvent",
    "BusinessNetworkEvent",
    "CharacterIdentifiedEvent",
    "FinishedQuestsSnapshotEvent",
    "NetworkEvent",
    "QuestCompletedEvent",
    "QuestJournalSnapshotEvent",
    "QuestObjectiveCompletedEvent",
    "QuestStartedEvent",
    "SessionClosedEvent",
]
