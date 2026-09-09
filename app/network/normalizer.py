from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.network.events import (
    AchievementCompletedEvent,
    AchievementObjectiveCompletedEvent,
    BusinessNetworkEvent,
    CharacterIdentifiedEvent,
    FinishedQuestsSnapshotEvent,
    QuestCompletedEvent,
    QuestJournalSnapshotEvent,
    QuestObjectiveCompletedEvent,
    QuestStartedEvent,
    SessionClosedEvent,
)


@dataclass(frozen=True, slots=True)
class DecodedClientMessage:
    """Small semantic envelope emitted by a version-specific protocol adapter.

    Raw packets and unrelated client data must not be retained here. ``verified``
    means the adapter has positively identified the message using its supported
    protocol version; it is not inferred from field shape.
    """

    session_id: str
    event_type: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = ""
    verified: bool = False


class ProtocolEventNormalizer:
    """Convert verified semantic messages into Atlas business events."""

    def normalize(self, message: DecodedClientMessage) -> BusinessNetworkEvent | None:
        if not isinstance(message, DecodedClientMessage) or not message.verified:
            return None
        session_id = str(message.session_id or "").strip()
        event_type = str(message.event_type or "").strip().casefold()
        if not session_id or not event_type or not isinstance(message.fields, Mapping):
            return None
        event_id = str(message.event_id or "").strip()
        fields = message.fields

        if event_type == "session_closed":
            return SessionClosedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
            )
        if event_type == "character_identified":
            name = str(fields.get("character_name") or "").strip()
            if not name:
                return None
            return CharacterIdentifiedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                character_name=name,
                character_id=self._optional_positive_int(fields.get("character_id")),
            )
        if event_type == "quest_started":
            quest_id = self._positive_int(fields.get("quest_id"))
            if quest_id is None:
                return None
            return QuestStartedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                quest_id=quest_id,
            )
        if event_type == "quest_objective_completed":
            quest_id = self._positive_int(fields.get("quest_id"))
            objective_id = self._positive_int(fields.get("objective_id"))
            if quest_id is None or objective_id is None:
                return None
            return QuestObjectiveCompletedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                quest_id=quest_id,
                objective_id=objective_id,
            )
        if event_type == "quest_completed":
            quest_id = self._positive_int(fields.get("quest_id"))
            if quest_id is None:
                return None
            validated_step_id = None
            if "validated_step_id" in fields:
                validated_step_id = self._positive_int(fields.get("validated_step_id"))
                if validated_step_id is None:
                    return None
            return QuestCompletedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                quest_id=quest_id,
                validated_step_id=validated_step_id,
            )
        if event_type == "quest_journal_snapshot":
            finished = self._positive_int_tuple(fields.get("finished_quest_ids"))
            active = self._positive_int_tuple(fields.get("active_quest_ids", ()))
            if finished is None or active is None:
                return None
            return QuestJournalSnapshotEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                finished_quest_ids=finished,
                active_quest_ids=active,
            )
        if event_type == "finished_quests_snapshot":
            quest_ids = self._positive_int_tuple(fields.get("quest_ids"))
            player_id = self._positive_int(fields.get("player_id"))
            if quest_ids is None or player_id is None:
                return None
            return FinishedQuestsSnapshotEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                quest_ids=quest_ids,
                player_id=player_id,
            )
        if event_type == "achievement_objective_completed":
            achievement_id = self._positive_int(fields.get("achievement_id"))
            objective_id = self._positive_int(fields.get("objective_id"))
            if achievement_id is None or objective_id is None:
                return None
            return AchievementObjectiveCompletedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                achievement_id=achievement_id,
                objective_id=objective_id,
            )
        if event_type == "achievement_completed":
            achievement_id = self._positive_int(fields.get("achievement_id"))
            if achievement_id is None:
                return None
            return AchievementCompletedEvent(
                session_id=session_id,
                event_id=event_id,
                reliable=True,
                achievement_id=achievement_id,
            )
        return None

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    @classmethod
    def _optional_positive_int(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return cls._positive_int(value)

    @classmethod
    def _positive_int_tuple(cls, value: Any) -> tuple[int, ...] | None:
        if not isinstance(value, (tuple, list)):
            return None
        result: list[int] = []
        seen: set[int] = set()
        for raw in value:
            parsed = cls._positive_int(raw)
            if parsed is None:
                return None
            if parsed not in seen:
                seen.add(parsed)
                result.append(parsed)
        return tuple(result)


__all__ = ["DecodedClientMessage", "ProtocolEventNormalizer"]
