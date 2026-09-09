from __future__ import annotations

from logging import Logger
from typing import Any

from app.core.logger import get_runtime_logger
from app.network.current_protocol_profile import DOFUS_361010_PROFILE
from app.network.diagnostics import (
    DEBUG_GATE,
    network_debug_enabled,
    network_debug_log,
    protocol_payload_summary,
)
from app.network.events import (
    AchievementCompletedEvent,
    AchievementObjectiveCompletedEvent,
    BusinessNetworkEvent,
    CharacterIdentifiedEvent,
    QuestCompletedEvent,
    QuestJournalSnapshotEvent,
    QuestObjectiveCompletedEvent,
    QuestStartedEvent,
)
from app.network.progress_bridge import EventApplicationResult, NetworkProgressBridge
from app.network.protocol_calibration import CurrentProtocolCalibration
from app.network.transport import (
    CapturedProtocolMessage,
    ProtocolMessageDecoder,
    TransportSessionClosed,
)


class DiagnosticProtocolMessageDecoder:
    """Observe the verified runtime decoder without changing its trust contract.

    The wrapper is strictly passive: it delegates the semantic decision to the
    existing exact-build decoder and only emits bounded structured diagnostics
    when ATLAS_NETWORK_DEBUG (or ATLAS_NETWORK_DEBUG_DEEP) is enabled.
    """

    def __init__(self, delegate: ProtocolMessageDecoder, *, logger: Logger | None = None) -> None:
        self.delegate = delegate
        self.logger = logger or get_runtime_logger()

    def decode(self, message: CapturedProtocolMessage):
        self._log_packet(message)
        decoded = self.delegate.decode(message)
        if decoded is None:
            self._log_unhandled(message)
            return None

        network_debug_log(
            self.logger,
            "[NETWORK][MESSAGE][DECODED]",
            session=message.session_id,
            message_type=message.type_url,
            direction=message.direction,
            event_type=decoded.event_type,
            event_id=decoded.event_id,
            verified=decoded.verified,
            decoded_fields=tuple(sorted(str(key) for key in decoded.fields)),
            payload_summary=protocol_payload_summary(message.payload),
        )
        self._log_semantic_raw(message, decoded)
        return decoded

    def session_closed(self, session_id: str) -> None:
        hook = getattr(self.delegate, "session_closed", None)
        if callable(hook):
            hook(session_id)

    def reset(self) -> None:
        hook = getattr(self.delegate, "reset", None)
        if callable(hook):
            hook()

    def _log_packet(self, message: CapturedProtocolMessage) -> None:
        if not network_debug_enabled():
            return
        key = f"packet:{message.type_url}:{message.direction}"
        if not DEBUG_GATE.should_log(key, first=2, every=250):
            return
        network_debug_log(
            self.logger,
            "[NETWORK][PACKET][RECEIVED]",
            session=message.session_id,
            message_type=message.type_url,
            direction=message.direction,
            payload_summary=protocol_payload_summary(message.payload),
            occurrence=DEBUG_GATE.count(key),
        )

    def _log_unhandled(self, message: CapturedProtocolMessage) -> None:
        if not network_debug_enabled():
            return
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return
        if not str(message.type_url or "").startswith("type.ankama.com/"):
            return
        key = f"unhandled:{message.type_url}"
        if not DEBUG_GATE.should_log(key, first=1, every=500):
            return
        summary = protocol_payload_summary(message.payload)
        network_debug_log(
            self.logger,
            "[NETWORK][UNHANDLED]",
            session=message.session_id,
            message_type=message.type_url,
            opcode=message.type_url.rsplit("/", 1)[-1],
            payload_fields=summary.get("payload_fields", ()),
            payload_summary=summary,
            occurrence=DEBUG_GATE.count(key),
            diagnostic_hint=(
                "No verified semantic mapping. Correlate this type with controlled "
                "level/achievement/quest actions before adding any decoder."
            ),
        )

    def _log_semantic_raw(self, message: CapturedProtocolMessage, decoded: Any) -> None:
        fields = decoded.fields
        event_type = str(decoded.event_type or "").casefold()
        common = {
            "session": message.session_id,
            "message_type": message.type_url,
            "opcode": message.type_url.rsplit("/", 1)[-1],
            "source": message.type_url,
            "event_id": decoded.event_id,
        }
        if event_type == "character_identified":
            network_debug_log(
                self.logger,
                "[NETWORK][CHARACTER][RAW]",
                **common,
                character_id=fields.get("character_id"),
                name=fields.get("character_name"),
                class_raw=None,
                level_raw=None,
                note="current verified identity contract exposes id+name only",
            )
        elif event_type == "quest_journal_snapshot":
            finished = tuple(fields.get("finished_quest_ids", ()) or ())
            active = tuple(fields.get("active_quest_ids", ()) or ())
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_HISTORY][RAW]",
                **common,
                character_id=None,
                completed_count=len(finished),
                completed_ids=finished,
                active_ids=active,
                payload_summary=protocol_payload_summary(message.payload),
            )
        elif event_type == "quest_completed":
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_FINISHED][RAW]",
                **common,
                character_id=None,
                quest_id=fields.get("quest_id"),
                step_id=fields.get("validated_step_id"),
                payload_summary=protocol_payload_summary(message.payload),
            )
        elif event_type == "quest_started":
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_STARTED][RAW]",
                **common,
                quest_id=fields.get("quest_id"),
            )
        elif event_type == "quest_objective_completed":
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_OBJECTIVE][RAW]",
                **common,
                quest_id=fields.get("quest_id"),
                objective_id=fields.get("objective_id"),
            )
        elif event_type == "achievement_completed":
            network_debug_log(
                self.logger,
                "[NETWORK][ACHIEVEMENT][RAW]",
                **common,
                achievement_id=fields.get("achievement_id"),
            )
        elif event_type == "achievement_objective_completed":
            network_debug_log(
                self.logger,
                "[NETWORK][ACHIEVEMENT_OBJECTIVE][RAW]",
                **common,
                achievement_id=fields.get("achievement_id"),
                objective_id=fields.get("objective_id"),
            )


class InstrumentedCurrentProtocolCalibration(CurrentProtocolCalibration):
    """Current calibration with passive diagnostics around the existing proof engine."""

    def observe(self, item: CapturedProtocolMessage | TransportSessionClosed):
        if isinstance(item, CapturedProtocolMessage) and network_debug_enabled():
            key = f"calibration-packet:{item.type_url}:{item.direction}"
            if DEBUG_GATE.should_log(key, first=2, every=250):
                network_debug_log(
                    get_runtime_logger(),
                    "[NETWORK][PACKET][RECEIVED]",
                    session=item.session_id,
                    message_type=item.type_url,
                    direction=item.direction,
                    phase="calibration",
                    payload_summary=protocol_payload_summary(item.payload),
                    occurrence=DEBUG_GATE.count(key),
                )
        return super().observe(item)

    def _observe_business_event(self, event: object) -> None:
        logger = get_runtime_logger()
        if network_debug_enabled():
            if isinstance(event, CharacterIdentifiedEvent):
                network_debug_log(
                    logger,
                    "[NETWORK][CHARACTER][DETECTED]",
                    phase="calibration",
                    session=event.session_id,
                    character_id=event.character_id,
                    name=event.character_name,
                    source=DOFUS_361010_PROFILE.character_selected_type_url,
                    class_name=None,
                    level=None,
                )
            elif isinstance(event, QuestJournalSnapshotEvent):
                network_debug_log(
                    logger,
                    "[NETWORK][QUEST_HISTORY][NORMALIZED]",
                    phase="calibration",
                    session=event.session_id,
                    completed_network_ids=event.finished_quest_ids,
                    active_network_ids=event.active_quest_ids,
                    source=DOFUS_361010_PROFILE.quest_journal_type_url,
                )
            elif isinstance(event, QuestCompletedEvent):
                network_debug_log(
                    logger,
                    "[NETWORK][QUEST_FINISHED][NORMALIZED]",
                    phase="calibration",
                    session=event.session_id,
                    quest_id=event.quest_id,
                    step_id=event.validated_step_id,
                    source=DOFUS_361010_PROFILE.quest_step_validated_type_url,
                )
        super()._observe_business_event(event)


class InstrumentedNetworkProgressBridge(NetworkProgressBridge):
    """Read-only observation layer around the existing progression bridge.

    All mutations still happen in NetworkProgressBridge and the existing shared
    progression services. This subclass only snapshots state before/after and
    emits causal logs, so enabling diagnostics cannot create a second source of
    truth or make an otherwise rejected event acceptable.
    """

    def handle(self, event: BusinessNetworkEvent) -> EventApplicationResult:
        if not network_debug_enabled():
            return super().handle(event)

        session_id = str(getattr(event, "session_id", "") or "")
        old_character = self.session_character_key(session_id)
        before = self._state(old_character)
        self._log_before(event, old_character, before)
        result = super().handle(event)
        new_character = result.character_key or self.session_character_key(session_id)
        after = self._state(new_character)
        self._log_after(event, result, old_character, new_character, before, after)
        return result

    def _state(self, character_key: str) -> dict[str, Any]:
        key = str(character_key or "")
        if not key:
            return {
                "completed_quests": frozenset(),
                "completed_achievements": frozenset(),
            }
        try:
            quests = frozenset(self.quest_progress_service.completed_quest_ids(key))
        except Exception:
            quests = frozenset()
        try:
            achievement_state = self.achievement_progress_service.state_for(key)
            achievements = frozenset(
                int(value)
                for value in getattr(achievement_state, "completed_achievements", set())
            )
        except Exception:
            achievements = frozenset()
        return {
            "completed_quests": quests,
            "completed_achievements": achievements,
        }

    def _log_before(self, event: BusinessNetworkEvent, character_key: str, state: dict[str, Any]) -> None:
        session_id = str(getattr(event, "session_id", "") or "")
        character_id = self._positive_int(self._session_character_ids.get(session_id))
        if isinstance(event, CharacterIdentifiedEvent):
            network_debug_log(
                self.logger,
                "[NETWORK][CHARACTER][DETECTED]",
                session=session_id,
                character_id=event.character_id,
                name=event.character_name,
                class_name=None,
                level=None,
                atlas_profile_id=character_key or None,
                source="CharacterIdentifiedEvent",
                event_id=event.event_id,
            )
            return

        if isinstance(event, QuestJournalSnapshotEvent):
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_HISTORY][NORMALIZED]",
                session=session_id,
                character_id=character_id,
                atlas_character=character_key or None,
                completed_network_ids=event.finished_quest_ids,
                active_network_ids=event.active_quest_ids,
                event_id=event.event_id,
            )
            for raw_quest_id in event.finished_quest_ids:
                self._log_quest_candidate(
                    character_key,
                    character_id,
                    int(raw_quest_id),
                    state,
                    evidence_type="completed_quest_list",
                    source="network_history",
                )
            return

        if isinstance(event, QuestCompletedEvent):
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_FINISHED][NORMALIZED]",
                session=session_id,
                character_id=character_id,
                quest_id=event.quest_id,
                step_id=event.validated_step_id,
                event_id=event.event_id,
            )
            network_debug_log(
                self.logger,
                "[QUEST_AUTO_VALIDATE][LIVE_EVENT]",
                trace_id=self._trace_id(event.quest_id),
                character_id=character_id,
                atlas_character=character_key or None,
                quest_id=event.quest_id,
                step_id=event.validated_step_id,
            )
            self._log_quest_candidate(
                character_key,
                character_id,
                int(event.quest_id),
                state,
                evidence_type="quest_finished_event",
                source="network_live_event",
            )
            return

        if isinstance(event, QuestObjectiveCompletedEvent):
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_OBJECTIVE]",
                trace_id=self._trace_id(event.quest_id),
                session=session_id,
                character_id=character_id,
                atlas_character=character_key or None,
                quest_id=event.quest_id,
                step_id=None,
                objective_id=event.objective_id,
                status="completed",
            )
            network_debug_log(
                self.logger,
                "[QUEST_AUTO_VALIDATE][SAFETY_CHECK]",
                trace_id=self._trace_id(event.quest_id),
                character_id=character_id,
                quest_id=event.quest_id,
                quest_name=self._quest_name(event.quest_id),
                evidence_type="objective_event",
                evidence_value=event.objective_id,
                confidence="objective_only",
                accepted=False,
                reason="objective_completion_is_not_quest_completion",
            )
            return

        if isinstance(event, QuestStartedEvent):
            network_debug_log(
                self.logger,
                "[NETWORK][QUEST_STARTED][NORMALIZED]",
                trace_id=self._trace_id(event.quest_id),
                session=session_id,
                character_id=character_id,
                atlas_character=character_key or None,
                quest_id=event.quest_id,
            )
            return

        if isinstance(event, AchievementCompletedEvent):
            achievement = self.achievement_provider.get_by_id(int(event.achievement_id))
            network_debug_log(
                self.logger,
                "[NETWORK][ACHIEVEMENT][DETECTED]",
                session=session_id,
                character_id=character_id,
                achievement_id_raw=event.achievement_id,
                normalized_id=event.achievement_id,
                completed=True,
                source="verified_network_event",
            )
            network_debug_log(
                self.logger,
                "[PROGRESS][ACHIEVEMENT][MATCH]",
                network_id=event.achievement_id,
                atlas_id=event.achievement_id if achievement is not None else None,
                atlas_name=getattr(achievement, "name", None) if achievement is not None else None,
                status="matched" if achievement is not None else "unknown",
            )
            return

        if isinstance(event, AchievementObjectiveCompletedEvent):
            network_debug_log(
                self.logger,
                "[NETWORK][ACHIEVEMENT_OBJECTIVE][NORMALIZED]",
                session=session_id,
                character_id=character_id,
                achievement_id=event.achievement_id,
                objective_id=event.objective_id,
            )

    def _log_quest_candidate(
        self,
        character_key: str,
        character_id: int | None,
        quest_id: int,
        state: dict[str, Any],
        *,
        evidence_type: str,
        source: str,
    ) -> None:
        trace_id = self._trace_id(quest_id)
        quest = self.quest_catalog.by_id.get(int(quest_id))
        matched = quest is not None
        network_debug_log(
            self.logger,
            "[QUEST_MATCH][START]",
            trace_id=trace_id,
            network_quest_id=quest_id,
        )
        if matched:
            network_debug_log(
                self.logger,
                "[QUEST_MATCH][RESULT]",
                trace_id=trace_id,
                network_quest_id=quest_id,
                atlas_quest_id=quest_id,
                atlas_quest_name=getattr(quest, "name", None),
                strategy="direct_id",
                result="matched",
            )
        else:
            network_debug_log(
                self.logger,
                "[QUEST_MATCH][FAILED]",
                trace_id=trace_id,
                network_quest_id=quest_id,
                reason="network_id_absent_from_atlas_catalog",
                possible_matches=(),
            )

        accepted = bool(character_key and character_id is not None and matched)
        reason = (
            "explicit_completed_quest_for_verified_character"
            if accepted
            else (
                "character_not_verified"
                if not character_key or character_id is None
                else "quest_id_not_in_atlas_catalog"
            )
        )
        network_debug_log(
            self.logger,
            "[QUEST_AUTO_VALIDATE][SAFETY_CHECK]",
            trace_id=trace_id,
            character_id=character_id,
            atlas_character=character_key or None,
            quest_id=quest_id,
            quest_name=getattr(quest, "name", None) if quest is not None else None,
            evidence_type=evidence_type,
            evidence_value=quest_id,
            confidence="explicit" if accepted else "rejected",
            accepted=accepted,
            reason=reason,
        )
        network_debug_log(
            self.logger,
            "[QUEST_AUTO_VALIDATE][REQUEST]",
            trace_id=trace_id,
            character_id=character_id,
            atlas_character=character_key or None,
            network_quest_id=quest_id,
            atlas_quest_id=quest_id if matched else None,
            quest_name=getattr(quest, "name", None) if quest is not None else None,
            source=source,
        )
        network_debug_log(
            self.logger,
            "[QUEST_AUTO_VALIDATE][STATE_BEFORE]",
            trace_id=trace_id,
            character_id=character_id,
            quest_id=quest_id,
            already_completed_local=quest_id in state["completed_quests"],
            guide_completed=quest_id in state["completed_quests"],
            quest_tab_completed=quest_id in state["completed_quests"],
            success_progress_completed_count=len(state["completed_achievements"]),
        )

    def _log_after(
        self,
        event: BusinessNetworkEvent,
        result: EventApplicationResult,
        old_character: str,
        new_character: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        session_id = str(getattr(event, "session_id", "") or "")
        character_id = self._positive_int(self._session_character_ids.get(session_id))

        if isinstance(event, CharacterIdentifiedEvent):
            if old_character != new_character:
                network_debug_log(
                    self.logger,
                    "[PROGRESS][CHARACTER_SWITCH]",
                    character_id=character_id,
                    old_character=old_character or None,
                    new_character=new_character or None,
                    reason="network_detected",
                    session=session_id,
                    accepted=result.accepted,
                )
            self._log_persist_load(new_character, character_id)
            self._log_character_snapshot(new_character, character_id, session_id)
            if result.reason == "character_unresolved":
                network_debug_log(
                    self.logger,
                    "[PROGRESS][CHARACTER_SWITCH]",
                    old_character=old_character or None,
                    new_character=None,
                    reason="network_detected_unresolved",
                    session=session_id,
                    accepted=False,
                )
            network_debug_log(
                self.logger,
                "[NETWORK][LEVEL][UNAVAILABLE]",
                character_id=character_id,
                atlas_character=new_character or None,
                reason="no_verified_level_decoder_in_current_protocol_profile",
            )
            network_debug_log(
                self.logger,
                "[NETWORK][ACHIEVEMENTS][SUMMARY_UNAVAILABLE]",
                character_id=character_id,
                atlas_character=new_character or None,
                reason="no_verified_achievement_summary_decoder_in_current_protocol_profile",
            )
            return

        if isinstance(event, QuestJournalSnapshotEvent):
            self._log_quest_batch_after(event, result, new_character, character_id, before, after)
            return

        if isinstance(event, QuestCompletedEvent):
            self._log_single_quest_after(event, result, new_character, character_id, before, after)
            return

        if isinstance(event, QuestObjectiveCompletedEvent):
            network_debug_log(
                self.logger,
                "[PROGRESS][SYNC]",
                trace_id=self._trace_id(event.quest_id),
                character_id=character_id,
                atlas_character=new_character or None,
                quest_id=event.quest_id,
                guide_updated=False,
                quest_catalog_updated=False,
                achievement_progress_updated=False,
                persisted=bool(result.changed),
                result=result.reason,
                note="objective state may persist; whole quest intentionally remains incomplete",
            )
            return

        if isinstance(event, AchievementCompletedEvent):
            before_count = len(before["completed_achievements"])
            after_count = len(after["completed_achievements"])
            network_debug_log(
                self.logger,
                "[PROGRESS][ACHIEVEMENTS][APPLIED]",
                character_id=character_id,
                atlas_character=new_character or None,
                old_count=before_count,
                new_count=after_count,
                old_points=None,
                new_points=None,
                total=None,
                result=result.reason,
            )
            self._log_achievement_report(new_character, character_id, before_count, after_count)

    def _log_quest_batch_after(
        self,
        event: QuestJournalSnapshotEvent,
        result: EventApplicationResult,
        character_key: str,
        character_id: int | None,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        matched = {
            int(quest_id)
            for quest_id in event.finished_quest_ids
            if int(quest_id) in self.quest_catalog.by_id
        }
        unknown = tuple(
            sorted(
                int(quest_id)
                for quest_id in event.finished_quest_ids
                if int(quest_id) not in self.quest_catalog.by_id
            )
        )
        before_done = before["completed_quests"]
        after_done = after["completed_quests"]
        newly = matched.intersection(after_done).difference(before_done)
        already = matched.intersection(before_done)

        for quest_id in sorted(matched):
            trace_id = self._trace_id(quest_id)
            is_after = quest_id in after_done
            was_before = quest_id in before_done
            apply_result = (
                "already_validated" if was_before and is_after
                else "validated" if is_after
                else "rejected"
            )
            network_debug_log(
                self.logger,
                "[QUEST_AUTO_VALIDATE][APPLY]",
                trace_id=trace_id,
                character_id=character_id,
                atlas_character=character_key or None,
                quest_id=quest_id,
                result=apply_result,
                bridge_result=result.reason,
            )
            network_debug_log(
                self.logger,
                "[QUEST_AUTO_VALIDATE][STATE_AFTER]",
                trace_id=trace_id,
                character_id=character_id,
                quest_id=quest_id,
                quest_completed=is_after,
                guide_synced=is_after,
                quest_tab_synced=is_after,
                success_synced=True,
            )
            network_debug_log(
                self.logger,
                "[PROGRESS][SYNC]",
                trace_id=trace_id,
                character_id=character_id,
                atlas_character=character_key or None,
                quest_id=quest_id,
                guide_updated=is_after,
                quest_catalog_updated=is_after,
                achievement_progress_updated=(
                    len(after["completed_achievements"]) != len(before["completed_achievements"])
                ),
                persisted=quest_id in newly,
            )
            if quest_id in newly:
                network_debug_log(
                    self.logger,
                    "[PROGRESS][PERSIST][WRITE]",
                    trace_id=trace_id,
                    character_id=character_id,
                    atlas_character=character_key or None,
                    quest_id=quest_id,
                    path_or_store=str(getattr(self.quest_progress_service, "path", "")),
                    success=True,
                )
            if not is_after:
                network_debug_log(
                    self.logger,
                    "[PROGRESS][SYNC_MISMATCH]",
                    trace_id=trace_id,
                    quest_id=quest_id,
                    guide_status="incomplete",
                    quest_tab_status="incomplete",
                    achievement_status="unknown",
                    bridge_result=result.reason,
                )

        network_debug_log(
            self.logger,
            "[NETWORK][QUEST_SYNC_REPORT]",
            character_id=character_id,
            atlas_character=character_key or None,
            network_completed_total=len(event.finished_quest_ids),
            matched_atlas=len(matched),
            already_completed=len(already),
            newly_validated=len(newly),
            unknown_ids=unknown,
            ambiguous_ids=(),
            rejected_for_safety=(len(unknown) + (0 if result.accepted else len(matched))),
            active_quests_count=len(event.active_quest_ids),
            bridge_result=result.reason,
        )
        self._log_character_snapshot(
            character_key,
            character_id,
            str(getattr(event, "session_id", "") or ""),
            network_completed=len(event.finished_quest_ids),
            matched=len(matched),
            unknown=len(unknown),
            before_count=len(before_done),
            after_count=len(after_done),
            active_count=len(event.active_quest_ids),
        )

    def _log_single_quest_after(
        self,
        event: QuestCompletedEvent,
        result: EventApplicationResult,
        character_key: str,
        character_id: int | None,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        quest_id = int(event.quest_id)
        trace_id = self._trace_id(quest_id)
        was_before = quest_id in before["completed_quests"]
        is_after = quest_id in after["completed_quests"]
        network_debug_log(
            self.logger,
            "[QUEST_AUTO_VALIDATE][APPLY]",
            trace_id=trace_id,
            character_id=character_id,
            atlas_character=character_key or None,
            quest_id=quest_id,
            result=(
                "already_validated" if was_before and is_after
                else "validated" if is_after
                else "rejected"
            ),
            bridge_result=result.reason,
        )
        network_debug_log(
            self.logger,
            "[QUEST_AUTO_VALIDATE][STATE_AFTER]",
            trace_id=trace_id,
            quest_completed=is_after,
            guide_synced=is_after,
            quest_tab_synced=is_after,
            success_synced=True,
        )
        network_debug_log(
            self.logger,
            "[PROGRESS][SYNC]",
            trace_id=trace_id,
            character_id=character_id,
            atlas_character=character_key or None,
            quest_id=quest_id,
            guide_updated=is_after,
            quest_catalog_updated=is_after,
            achievement_progress_updated=(
                len(after["completed_achievements"]) != len(before["completed_achievements"])
            ),
            persisted=bool(is_after and not was_before),
        )
        if is_after and not was_before:
            network_debug_log(
                self.logger,
                "[PROGRESS][PERSIST][WRITE]",
                trace_id=trace_id,
                character_id=character_id,
                atlas_character=character_key or None,
                quest_id=quest_id,
                path_or_store=str(getattr(self.quest_progress_service, "path", "")),
                success=True,
            )

    def _log_persist_load(self, character_key: str, character_id: int | None) -> None:
        state = self._state(character_key)
        network_debug_log(
            self.logger,
            "[PROGRESS][PERSIST][LOAD]",
            character_id=character_id,
            atlas_character=character_key or None,
            path_or_store=str(getattr(self.quest_progress_service, "path", "")),
            completed_quests_count=len(state["completed_quests"]),
            completed_achievements_count=len(state["completed_achievements"]),
            level=None,
            achievement_points=None,
        )

    def _log_character_snapshot(
        self,
        character_key: str,
        character_id: int | None,
        session_id: str,
        *,
        network_completed: int | None = None,
        matched: int | None = None,
        unknown: int | None = None,
        before_count: int | None = None,
        after_count: int | None = None,
        active_count: int | None = None,
    ) -> None:
        state = self._state(character_key)
        name = self._session_character_names.get(session_id, "")
        network_debug_log(
            self.logger,
            "[NETWORK][CHARACTER_SNAPSHOT]",
            character_id=character_id,
            name=name or None,
            class_name=None,
            level=None,
            atlas_character=character_key or None,
            achievement_count_network=None,
            achievement_points=None,
            achievement_total=None,
            atlas_completed_achievements=len(state["completed_achievements"]),
            completed_quests_network_count=network_completed,
            completed_quests_atlas_matched=matched,
            completed_quests_unknown=unknown,
            active_quests_count=active_count,
            atlas_completed_quests_before_sync=before_count,
            atlas_completed_quests_after_sync=(
                after_count if after_count is not None else len(state["completed_quests"])
            ),
        )

    def _log_achievement_report(
        self,
        character_key: str,
        character_id: int | None,
        before_count: int,
        after_count: int,
    ) -> None:
        network_debug_log(
            self.logger,
            "[NETWORK][ACHIEVEMENT_SYNC_REPORT]",
            character_id=character_id,
            atlas_character=character_key or None,
            network_completed_total=None,
            matched_atlas=None,
            newly_validated=max(0, after_count - before_count),
            unknown_ids=(),
            achievement_points=None,
            achievement_count=None,
            achievement_total=None,
            atlas_completed_achievement_count=after_count,
            note="network summary count/points are unavailable until a verified decoder is identified",
        )

    def _quest_name(self, quest_id: int) -> str | None:
        quest = self.quest_catalog.by_id.get(int(quest_id))
        return str(getattr(quest, "name", "") or "") or None

    @staticmethod
    def _trace_id(quest_id: int) -> str:
        return f"QUEST-{int(quest_id)}"


__all__ = [
    "DiagnosticProtocolMessageDecoder",
    "InstrumentedCurrentProtocolCalibration",
    "InstrumentedNetworkProgressBridge",
]
