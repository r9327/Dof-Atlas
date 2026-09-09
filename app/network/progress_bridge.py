from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from logging import Logger
from typing import Any

from app.core.logger import get_runtime_logger
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.network.character_resolver import CharacterSlotResolver
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
from app.quest_catalog import QuestCatalog


@dataclass(frozen=True, slots=True)
class EventApplicationResult:
    accepted: bool
    changed: bool
    reason: str
    character_key: str = ""


class NetworkProgressBridge:
    """Apply trusted client events through the existing progression services.

    This class owns no persistent progression. It keeps only volatile
    connection/session routing, a bounded event-id cache, and at most one
    pre-identity reviewed idr journal per transport session. Persistent truth
    remains in QuestProgressService / AchievementProgressService and Guide
    progress continues to derive from those existing services.

    A reviewed idr can arrive while entering the world before the final kvi+kva
    character correlation. Such a journal is retained in semantic form only and
    cannot mutate anything until that exact transport session proves a concrete
    character id. Unresolved identity, re-identification, session close and
    reset all discard the pending journal, preventing cross-character reuse.

    Character/session routing events deliberately bypass event-id dedupe. The
    same character-identification payload can be valid more than once on one
    connection (for example A -> B -> A); suppressing the second A would route
    later progression to the wrong character. Dedupe entries are also discarded
    whenever that session changes identity or closes, so an identical quest
    payload produced later by another character cannot inherit the old route's
    duplicate namespace.
    """

    def __init__(
        self,
        *,
        quest_catalog: QuestCatalog,
        quest_progress_service: QuestProgressService,
        achievement_progress_service: AchievementProgressService,
        achievement_provider: Any,
        guide_provider: Any = None,
        character_resolver: CharacterSlotResolver | None = None,
        logger: Logger | None = None,
        dedupe_limit: int = 4096,
    ) -> None:
        self.quest_catalog = quest_catalog
        self.quest_progress_service = quest_progress_service
        self.achievement_progress_service = achievement_progress_service
        self.achievement_provider = achievement_provider
        self.guide_provider = guide_provider
        self.character_resolver = character_resolver or CharacterSlotResolver()
        self.logger = logger or get_runtime_logger()
        self._state_lock = threading.RLock()
        self._session_characters: dict[str, str] = {}
        self._session_character_names: dict[str, str] = {}
        self._session_character_ids: dict[str, int] = {}
        self._pending_quest_journals: dict[str, QuestJournalSnapshotEvent] = {}
        self._seen_event_keys: set[tuple[str, str]] = set()
        self._seen_event_order: deque[tuple[str, str]] = deque()
        self._dedupe_limit = max(64, int(dedupe_limit))

    def handle(self, event: BusinessNetworkEvent) -> EventApplicationResult:
        if not bool(getattr(event, "reliable", False)):
            return EventApplicationResult(False, False, "unreliable_event")

        session_id = str(getattr(event, "session_id", "") or "").strip()
        if not session_id:
            return EventApplicationResult(False, False, "missing_session")

        event_id = str(getattr(event, "event_id", "") or "").strip()
        dedupe_allowed = not isinstance(event, (CharacterIdentifiedEvent, SessionClosedEvent))
        event_key = (session_id, event_id) if event_id and dedupe_allowed else None
        with self._state_lock:
            if event_key is not None and event_key in self._seen_event_keys:
                return EventApplicationResult(
                    True,
                    False,
                    "duplicate_event",
                    self._session_characters.get(session_id, ""),
                )

            try:
                result = self._dispatch(session_id, event)
            except Exception:
                self.logger.exception(
                    "Network event application failed: type=%s session=%s",
                    type(event).__name__,
                    session_id,
                )
                return EventApplicationResult(
                    False,
                    False,
                    "application_error",
                    self._session_characters.get(session_id, ""),
                )

            if event_key is not None and result.accepted:
                self._remember_event(event_key)
            return result

    def forget_session(self, session_id: str) -> None:
        key = str(session_id or "").strip()
        if not key:
            return
        with self._state_lock:
            self._forget_session_unlocked(key)

    def reset_sessions(self) -> None:
        """Drop all volatile routing, pending-journal and dedupe state."""

        with self._state_lock:
            self._session_characters.clear()
            self._session_character_names.clear()
            self._session_character_ids.clear()
            self._pending_quest_journals.clear()
            self._seen_event_keys.clear()
            self._seen_event_order.clear()

    def session_character_key(self, session_id: str) -> str:
        key = str(session_id or "").strip()
        with self._state_lock:
            return self._session_characters.get(key, "")

    def _dispatch(
        self,
        session_id: str,
        event: BusinessNetworkEvent,
    ) -> EventApplicationResult:
        if isinstance(event, SessionClosedEvent):
            previous = self._session_characters.get(session_id, "")
            self._forget_session_unlocked(session_id)
            return EventApplicationResult(
                True,
                bool(previous),
                "session_closed",
                previous,
            )
        if isinstance(event, CharacterIdentifiedEvent):
            return self._identify_character(session_id, event)
        if isinstance(event, QuestJournalSnapshotEvent):
            if not self._character_key_or_empty(session_id):
                # idr can precede final kvi+kva correlation. Retain only the
                # newest whole semantic journal for this transport session; no
                # progression service is touched until identity is proven.
                self._pending_quest_journals[session_id] = event
                return EventApplicationResult(
                    True,
                    False,
                    "quest_journal_pending_identity",
                )
            return self._apply_quest_journal_snapshot(session_id, event)
        if isinstance(event, FinishedQuestsSnapshotEvent):
            return self._apply_finished_quests_snapshot(session_id, event)
        if isinstance(event, QuestCompletedEvent):
            return self._complete_quest(session_id, event)
        if isinstance(event, QuestObjectiveCompletedEvent):
            return self._complete_quest_objective(session_id, event)
        if isinstance(event, QuestStartedEvent):
            return self._observe_quest_started(session_id, event)
        if isinstance(event, AchievementCompletedEvent):
            return self._complete_achievement(session_id, event)
        if isinstance(event, AchievementObjectiveCompletedEvent):
            return self._complete_achievement_objective(session_id, event)
        return EventApplicationResult(False, False, "unknown_event")

    def _identify_character(
        self,
        session_id: str,
        event: CharacterIdentifiedEvent,
    ) -> EventApplicationResult:
        resolve_for_session = getattr(self.character_resolver, "resolve_for_session", None)
        if callable(resolve_for_session):
            try:
                resolution = resolve_for_session(
                    event.character_name,
                    session_id,
                    event.character_id,
                )
            except TypeError:
                # Preserve compatibility with injected resolvers implementing
                # the original two-argument session API.
                resolution = resolve_for_session(event.character_name, session_id)
        else:
            resolution = self.character_resolver.resolve(event.character_name)
        if resolution is None:
            # A reliable character-change event that cannot be mapped must clear
            # the old session route and any pre-identity journal. Keeping either
            # would risk attributing progression to the wrong character.
            self._forget_session_unlocked(session_id)
            self.logger.warning(
                "Network character unresolved; session progression disabled: session=%s name=%r",
                session_id,
                event.character_name,
            )
            return EventApplicationResult(False, False, "character_unresolved")

        previous = self._session_characters.get(session_id, "")
        previous_character_id = self._positive_int(self._session_character_ids.get(session_id))
        character_id = self._positive_int(event.character_id)
        pending_journal = (
            self._pending_quest_journals.pop(session_id, None)
            if not previous
            else None
        )
        if previous:
            # Any identity after the first is a fresh routing boundary. A
            # journal captured before that boundary must never follow it.
            self._pending_quest_journals.pop(session_id, None)
        if previous != resolution.character_key or previous_character_id != character_id:
            self._forget_session_dedupe_unlocked(session_id)

        self._session_characters[session_id] = resolution.character_key
        self._session_character_names[session_id] = resolution.label
        if character_id is None:
            self._session_character_ids.pop(session_id, None)
        else:
            self._session_character_ids[session_id] = character_id
        route_changed = previous != resolution.character_key
        self.logger.info(
            "Network character mapped: session=%s character=%s key=%s",
            session_id,
            resolution.label,
            resolution.character_key,
        )

        # Apply the pending idr only on the first positively identified route,
        # and only when correlated identity supplied a concrete character id.
        # _apply_quest_journal_snapshot performs the same id/catalog guards used
        # for journals that arrive after identity.
        if pending_journal is not None and character_id is not None:
            journal_result = self._apply_quest_journal_snapshot(session_id, pending_journal)
            if journal_result.accepted:
                return EventApplicationResult(
                    True,
                    bool(route_changed or journal_result.changed),
                    "character_identified_with_quest_journal",
                    resolution.character_key,
                )

        return EventApplicationResult(
            True,
            route_changed,
            "character_identified" if route_changed else "character_unchanged",
            resolution.character_key,
        )

    def _apply_quest_journal_snapshot(
        self,
        session_id: str,
        event: QuestJournalSnapshotEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")

        # The reviewed idr journal has no player-id field. Its attribution is
        # therefore valid only when this exact transport session has already
        # proven a concrete character id through correlated kvi+kva identity.
        if self._positive_int(self._session_character_ids.get(session_id)) is None:
            self.logger.warning(
                "Network quest journal rejected without verified session character id: session=%s",
                session_id,
            )
            return EventApplicationResult(False, False, "character_id_missing", character_key)

        known_finished: set[int] = set()
        unknown_count = 0
        for raw_quest_id in event.finished_quest_ids:
            quest_id = self._positive_int(raw_quest_id)
            if quest_id is None or quest_id not in self.quest_catalog.by_id:
                unknown_count += 1
                continue
            known_finished.add(quest_id)

        if unknown_count:
            self.logger.info(
                "Network quest journal ignored %d finished quest ids absent from local catalog: session=%s",
                unknown_count,
                session_id,
            )

        # idr also contains active quests. They are deliberately ignored here;
        # active never means completed. Finished progress is additive only, so a
        # quest missing from one journal never clears manual or migrated state.
        quest_changed = False
        if known_finished:
            quest_changed = self.quest_progress_service.set_quests_completed(
                character_key,
                known_finished,
                True,
            )

        # Run the shared derivation once after the whole batch. This keeps
        # achievement/guide synchronization consistent without hundreds of
        # intermediate writes or refresh generations.
        achievement_changed = self.achievement_progress_service.sync_from_quest_progress(
            character_key,
            self.achievement_provider,
            self.quest_progress_service,
            self.guide_provider,
        )
        changed = bool(quest_changed or achievement_changed)
        if not known_finished:
            reason = "quest_journal_no_known_finished_quests"
        elif quest_changed:
            reason = "quest_journal_reconciled"
        else:
            reason = "quest_journal_already_reconciled"
        return EventApplicationResult(True, changed, reason, character_key)

    def _apply_finished_quests_snapshot(
        self,
        session_id: str,
        event: FinishedQuestsSnapshotEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")

        player_id = self._positive_int(event.player_id)
        expected_player_id = self._positive_int(self._session_character_ids.get(session_id))
        if expected_player_id is None:
            self.logger.warning(
                "Network quest snapshot rejected without verified session character id: session=%s",
                session_id,
            )
            return EventApplicationResult(False, False, "character_id_missing", character_key)
        if player_id is None:
            self.logger.warning(
                "Network quest snapshot rejected without player id: session=%s",
                session_id,
            )
            return EventApplicationResult(False, False, "snapshot_player_id_missing", character_key)
        if player_id != expected_player_id:
            self.logger.warning(
                "Network quest snapshot rejected on character id mismatch: session=%s",
                session_id,
            )
            return EventApplicationResult(False, False, "character_id_mismatch", character_key)

        # The legacy QuestsEvent alias was learned from payload shape alone and
        # can collide with catalogue-like messages. Keep this old mutation
        # boundary closed permanently; current catch-up uses the separately
        # reviewed idr journal path above.
        self.logger.warning(
            "Network finished-quest snapshot rejected: legacy alias is unverified."
        )
        return EventApplicationResult(
            False,
            False,
            "finished_quests_snapshot_unverified",
            character_key,
        )

    def _complete_quest(
        self,
        session_id: str,
        event: QuestCompletedEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")

        quest_id = self._positive_int(event.quest_id)
        if quest_id is None or quest_id not in self.quest_catalog.by_id:
            return EventApplicationResult(False, False, "unknown_quest", character_key)

        quest_changed = not self.quest_progress_service.is_quest_completed(character_key, quest_id)
        if quest_changed:
            self.quest_progress_service.set_quest_completed(character_key, quest_id, True)

        # Always run the existing derivation even for a duplicate quest state.
        # This repairs a previous interrupted achievement sync without rewriting
        # quest progression, while the service itself only persists if changed.
        achievement_changed = self.achievement_progress_service.sync_from_quest_progress(
            character_key,
            self.achievement_provider,
            self.quest_progress_service,
            self.guide_provider,
        )
        changed = bool(quest_changed or achievement_changed)
        return EventApplicationResult(
            True,
            changed,
            "quest_completed" if quest_changed else "quest_already_completed",
            character_key,
        )

    def _complete_quest_objective(
        self,
        session_id: str,
        event: QuestObjectiveCompletedEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")

        quest_id = self._positive_int(event.quest_id)
        objective_id = self._positive_int(event.objective_id)
        quest = self.quest_catalog.by_id.get(quest_id or -1)
        if quest is None:
            return EventApplicationResult(False, False, "unknown_quest", character_key)
        known_objectives = {
            int(objective.id)
            for step in quest.steps
            for objective in step.objectives
            if self._positive_int(getattr(objective, "id", None)) is not None
        }
        if objective_id is None or objective_id not in known_objectives:
            return EventApplicationResult(False, False, "unknown_quest_objective", character_key)

        if self.quest_progress_service.is_objective_completed(character_key, quest_id, objective_id):
            return EventApplicationResult(True, False, "quest_objective_already_completed", character_key)
        self.quest_progress_service.set_objective_completed(
            character_key,
            quest_id,
            objective_id,
            True,
        )
        return EventApplicationResult(True, True, "quest_objective_completed", character_key)

    def _observe_quest_started(
        self,
        session_id: str,
        event: QuestStartedEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")
        quest_id = self._positive_int(event.quest_id)
        if quest_id is None or quest_id not in self.quest_catalog.by_id:
            return EventApplicationResult(False, False, "unknown_quest", character_key)
        # There is intentionally no new persistent "started quests" store. The
        # current project has no such shared contract yet; observe only.
        return EventApplicationResult(True, False, "quest_started_observed", character_key)

    def _complete_achievement(
        self,
        session_id: str,
        event: AchievementCompletedEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")
        achievement_id = self._positive_int(event.achievement_id)
        if achievement_id is None or self.achievement_provider.get_by_id(achievement_id) is None:
            return EventApplicationResult(False, False, "unknown_achievement", character_key)
        if self.achievement_progress_service.is_achievement_completed(character_key, achievement_id):
            return EventApplicationResult(True, False, "achievement_already_completed", character_key)
        self.achievement_progress_service.set_achievement_completed(
            character_key,
            achievement_id,
            True,
        )
        return EventApplicationResult(True, True, "achievement_completed", character_key)

    def _complete_achievement_objective(
        self,
        session_id: str,
        event: AchievementObjectiveCompletedEvent,
    ) -> EventApplicationResult:
        character_key = self._character_key_or_empty(session_id)
        if not character_key:
            return EventApplicationResult(False, False, "character_not_identified")
        achievement_id = self._positive_int(event.achievement_id)
        objective_id = self._positive_int(event.objective_id)
        achievement = self.achievement_provider.get_by_id(achievement_id or -1)
        if achievement is None:
            return EventApplicationResult(False, False, "unknown_achievement", character_key)
        known_objectives = {
            int(objective.id)
            for objective in tuple(getattr(achievement, "objectives", ()) or ())
            if self._positive_int(getattr(objective, "id", None)) is not None
        }
        if objective_id is None or objective_id not in known_objectives:
            return EventApplicationResult(False, False, "unknown_achievement_objective", character_key)
        if self.achievement_progress_service.is_objective_completed(
            character_key,
            achievement_id,
            objective_id,
        ):
            return EventApplicationResult(True, False, "achievement_objective_already_completed", character_key)
        self.achievement_progress_service.set_objective_completed(
            character_key,
            achievement_id,
            objective_id,
            True,
        )
        return EventApplicationResult(True, True, "achievement_objective_completed", character_key)

    def _character_key_or_empty(self, session_id: str) -> str:
        return self._session_characters.get(session_id, "")

    def _forget_session_unlocked(self, session_id: str) -> None:
        self._session_characters.pop(session_id, None)
        self._session_character_names.pop(session_id, None)
        self._session_character_ids.pop(session_id, None)
        self._pending_quest_journals.pop(session_id, None)
        self._forget_session_dedupe_unlocked(session_id)

    def _forget_session_dedupe_unlocked(self, session_id: str) -> None:
        expired = {key for key in self._seen_event_keys if key[0] == session_id}
        if not expired:
            return
        self._seen_event_keys.difference_update(expired)
        self._seen_event_order = deque(
            key for key in self._seen_event_order if key not in expired
        )

    def _remember_event(self, event_key: tuple[str, str]) -> None:
        if event_key in self._seen_event_keys:
            return
        self._seen_event_keys.add(event_key)
        self._seen_event_order.append(event_key)
        while len(self._seen_event_order) > self._dedupe_limit:
            expired = self._seen_event_order.popleft()
            self._seen_event_keys.discard(expired)

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None


__all__ = ["EventApplicationResult", "NetworkProgressBridge"]
