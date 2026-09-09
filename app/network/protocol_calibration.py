from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Callable

from app.network.character_resolver import CharacterSlotResolver
from app.network.current_protocol_profile import (
    DOFUS_361010_PROFILE,
    dofus_361010_candidate_manifest,
    dofus_361010_profile_digest,
)
from app.network.events import CharacterIdentifiedEvent, QuestCompletedEvent, QuestJournalSnapshotEvent
from app.network.normalizer import ProtocolEventNormalizer
from app.network.quest_final_step_filter import FinalQuestStepEvidenceDecoder
from app.network.transport import CapturedProtocolMessage, TransportSessionClosed
from app.quest_catalog import QuestCatalog


@dataclass(frozen=True, slots=True)
class QuestJournalCalibrationEvidence:
    """Exact-build proof sufficient to reconcile the reviewed idr journal only.

    This evidence deliberately does not authorize the live idz completion rule.
    Live completion still requires the full ProtocolCalibrationCertificate below.
    """

    game_version: str
    build_sha256: str
    evidence_revision: str
    source_commit: str
    profile_digest: str
    character_key: str
    character_id: int
    character_name: str = ""
    session_id: str = ""
    quest_journal_type_url: str = ""
    journal_verified_quest_ids: tuple[int, ...] = ()
    journal_observation_count: int = 0


@dataclass(frozen=True, slots=True)
class ProtocolCalibrationCertificate:
    """Volatile proof that the reviewed profile matched one exact local build."""

    game_version: str
    build_sha256: str
    evidence_revision: str
    source_commit: str
    profile_digest: str
    character_key: str
    character_id: int
    verified_quest_ids: tuple[int, ...]
    character_name: str = ""
    session_id: str = ""
    quest_journal_type_url: str = ""
    journal_verified_quest_ids: tuple[int, ...] = ()
    journal_observation_count: int = 0
    finished_quests_snapshot_type_url: str = ""
    snapshot_verified_quest_ids: tuple[int, ...] = ()
    snapshot_observation_count: int = 0


@dataclass(frozen=True, slots=True)
class ProtocolCalibrationStatus:
    ready: bool
    reason: str
    build_sha256: str
    identified_session_count: int
    max_distinct_completion_count: int
    quest_journal_observation_count: int = 0
    quest_journal_verified_count: int = 0
    snapshot_candidate_count: int = 0
    snapshot_candidate_type_url: str = ""
    journal_evidence: QuestJournalCalibrationEvidence | None = None
    journal_evidences: tuple[QuestJournalCalibrationEvidence, ...] = ()
    certificate: ProtocolCalibrationCertificate | None = None


@dataclass(slots=True)
class _SessionCalibrationState:
    character_key: str = ""
    character_name: str = ""
    character_id: int = 0
    completion_ids: set[int] = field(default_factory=set)
    journal_finished_ids: set[int] = field(default_factory=set)
    journal_observation_count: int = 0
    activity_sequence: int = 0


@dataclass(slots=True)
class _PendingJournalState:
    finished_ids: set[int] = field(default_factory=set)
    observation_count: int = 0


class CurrentProtocolCalibration:
    """Prove final-step live completion and reviewed quest journal on one build.

    A reviewed idr journal is independently useful for additive catch-up as soon
    as this exact transport session proves correlated character identity. That
    partial evidence never authorizes live completion. The full runtime mapping
    still requires at least two distinct known quest completions through reviewed
    idz step-validation messages whose step is exactly the quest's final local
    ordered step, plus at least one strictly decoded idr journal on that session.

    idr normally arrives while entering the world and can precede the final
    kvi+kva character correlation. A pre-identity journal is retained only as
    volatile evidence for that transport session and attached to its first
    successful identity. Any later character identity replaces all prior
    evidence, so A -> B switches can never inherit A's journal or completions.
    """

    def __init__(
        self,
        *,
        build_sha256: str,
        active_build_sha256_provider: Callable[[], str | None],
        quest_catalog: QuestCatalog,
        character_resolver: CharacterSlotResolver | None = None,
        minimum_distinct_completions: int = 2,
    ) -> None:
        fingerprint = str(build_sha256 or "").strip().casefold()
        if not _is_sha256(fingerprint):
            raise ValueError("build_sha256 must be a 64-character SHA-256 digest")
        if active_build_sha256_provider is None:
            raise ValueError("active_build_sha256_provider is required")
        minimum = int(minimum_distinct_completions)
        if minimum < 2:
            raise ValueError("minimum_distinct_completions must be at least 2")

        self.build_sha256 = fingerprint
        self.active_build_sha256_provider = active_build_sha256_provider
        self.quest_catalog = quest_catalog
        self.character_resolver = character_resolver or CharacterSlotResolver()
        self._identity_events: deque[CharacterIdentifiedEvent] = deque()
        self.minimum_distinct_completions = minimum
        candidate_decoder = dofus_361010_candidate_manifest(
            fingerprint,
            include_quest_journal=True,
        ).build_decoder(
            active_build_sha256_provider=active_build_sha256_provider,
        )
        # idz proves a step, not the whole quest. Keep non-final idz out of the
        # semantic event stream entirely so calibration can never count it as a
        # completed quest even before the persistent progress bridge exists.
        self.decoder = FinalQuestStepEvidenceDecoder(candidate_decoder, quest_catalog)
        self.normalizer = ProtocolEventNormalizer()
        self._sessions: dict[str, _SessionCalibrationState] = {}
        self._pending_journals: dict[str, _PendingJournalState] = {}
        self._activity_sequence = 0
        self._invalidated_reason = ""

    def observe(
        self,
        item: CapturedProtocolMessage | TransportSessionClosed,
    ) -> ProtocolCalibrationStatus:
        if isinstance(item, TransportSessionClosed):
            self.session_closed(item.session_id)
            return self.status()
        if not isinstance(item, CapturedProtocolMessage):
            return self.status()

        # Outbound packets are capture-only evidence for diagnostics and
        # request/response correlation. They must never participate in semantic
        # mapping calibration, even if a decoder accidentally accepts them.
        if item.direction != "server_to_client":
            return self.status()

        if not self._build_matches():
            self._invalidate("build_changed")
            return self.status()
        if self._invalidated_reason:
            return self.status()

        decoded = self.decoder.decode(item)
        if decoded is not None:
            event = self.normalizer.normalize(decoded)
            if event is not None:
                self._observe_business_event(event)

        return self.status()

    def _observe_business_event(self, event: object) -> None:
        session_id = str(getattr(event, "session_id", "") or "").strip()
        if not session_id:
            return

        if isinstance(event, CharacterIdentifiedEvent):
            self._activity_sequence += 1
            resolve_for_session = getattr(self.character_resolver, "resolve_for_session", None)
            if callable(resolve_for_session):
                try:
                    resolution = resolve_for_session(
                        event.character_name,
                        session_id,
                        event.character_id,
                    )
                except TypeError:
                    resolution = resolve_for_session(event.character_name, session_id)
            else:
                resolution = self.character_resolver.resolve(event.character_name)
            character_id = _positive_int(event.character_id)
            if resolution is None or character_id is None:
                self._sessions.pop(session_id, None)
                self._pending_journals.pop(session_id, None)
                return

            previous = self._sessions.get(session_id)
            pending = self._pending_journals.pop(session_id, None) if previous is None else None
            state = _SessionCalibrationState(
                character_key=resolution.character_key,
                character_name=str(event.character_name or "").strip(),
                character_id=character_id,
                activity_sequence=self._activity_sequence,
            )
            if pending is not None:
                state.journal_finished_ids = set(pending.finished_ids)
                state.journal_observation_count = int(pending.observation_count)
            self._sessions[session_id] = state
            if previous is None or previous.character_key != state.character_key:
                self._identity_events.append(event)
            return

        if isinstance(event, QuestJournalSnapshotEvent):
            self._activity_sequence += 1
            known_finished = self._known_finished_ids(event.finished_quest_ids)
            state = self._sessions.get(session_id)
            if state is None:
                pending = self._pending_journals.setdefault(session_id, _PendingJournalState())
                pending.finished_ids = known_finished
                pending.observation_count += 1
                return
            if not state.character_key or state.character_id <= 0:
                return
            state.journal_finished_ids = known_finished
            state.journal_observation_count += 1
            state.activity_sequence = self._activity_sequence
            return

        state = self._sessions.get(session_id)
        if state is None or not state.character_key or state.character_id <= 0:
            return

        if isinstance(event, QuestCompletedEvent):
            self._activity_sequence += 1
            quest_id = _positive_int(event.quest_id)
            if quest_id is None or quest_id not in self.quest_catalog.by_id:
                return
            # Current calibration never accepts a protocol-agnostic one-shot
            # completion. The candidate is specifically idz, so require its
            # concrete step evidence again even though the outer decoder already
            # checked it. This guards the certificate against future decoder
            # changes accidentally dropping validated_step_id.
            step_id = _positive_int(event.validated_step_id)
            if step_id is None:
                return
            quest = self.quest_catalog.by_id.get(quest_id)
            if quest is None or not quest.steps:
                return
            final_step_id = _positive_int(getattr(quest.steps[-1], "id", None))
            if final_step_id is None or step_id != final_step_id:
                return
            state.completion_ids.add(quest_id)
            state.activity_sequence = self._activity_sequence

    def _known_finished_ids(self, values: tuple[int, ...]) -> set[int]:
        known: set[int] = set()
        for raw_quest_id in values:
            quest_id = _positive_int(raw_quest_id)
            if quest_id is not None and quest_id in self.quest_catalog.by_id:
                known.add(quest_id)
        return known

    def drain_identity_events(self) -> tuple[CharacterIdentifiedEvent, ...]:
        """Reader-owned notifications, independent of quest calibration readiness."""
        events = tuple(self._identity_events)
        self._identity_events.clear()
        return events

    def session_closed(self, session_id: str) -> None:
        session = str(session_id or "").strip()
        if session:
            self._sessions.pop(session, None)
            self._pending_journals.pop(session, None)
        hook = getattr(self.decoder, "session_closed", None)
        if callable(hook):
            hook(session)

    def reset(self) -> None:
        self._identity_events.clear()
        self._sessions.clear()
        self._pending_journals.clear()
        self._invalidated_reason = ""
        self._activity_sequence = 0
        hook = getattr(self.decoder, "reset", None)
        if callable(hook):
            hook()

    def status(self) -> ProtocolCalibrationStatus:
        if self._invalidated_reason:
            return ProtocolCalibrationStatus(
                ready=False,
                reason=self._invalidated_reason,
                build_sha256=self.build_sha256,
                identified_session_count=0,
                max_distinct_completion_count=0,
            )

        identified = [
            state
            for state in self._sessions.values()
            if state.character_key and state.character_id > 0
        ]
        best = max(identified, key=self._state_rank, default=None)
        best_session_id = next(
            (session_id for session_id, state in self._sessions.items() if state is best),
            "",
        )
        completion_count = len(best.completion_ids) if best is not None else 0
        journal_observation_count = best.journal_observation_count if best is not None else 0
        journal_verified_count = len(best.journal_finished_ids) if best is not None else 0

        if best is None:
            reason = "awaiting_character_identity"
        elif journal_observation_count < 1:
            reason = "awaiting_quest_journal"
        elif completion_count < self.minimum_distinct_completions:
            reason = "awaiting_distinct_quest_completions"
        else:
            reason = "profile_calibrated"

        journal_evidence = None
        if best is not None and journal_observation_count > 0:
            journal_evidence = QuestJournalCalibrationEvidence(
                game_version=DOFUS_361010_PROFILE.game_version,
                build_sha256=self.build_sha256,
                evidence_revision=DOFUS_361010_PROFILE.evidence_revision,
                source_commit=DOFUS_361010_PROFILE.source_commit,
                profile_digest=dofus_361010_profile_digest(),
                character_key=best.character_key,
                character_name=best.character_name,
                character_id=best.character_id,
                session_id=best_session_id,
                quest_journal_type_url=DOFUS_361010_PROFILE.quest_journal_type_url,
                journal_verified_quest_ids=tuple(sorted(best.journal_finished_ids)),
                journal_observation_count=journal_observation_count,
            )

        # Keep evidence for every identified client. Calibration readiness can
        # still be decided from the strongest session because the protocol map
        # is build-wide, while journal catch-up remains strictly per character.
        journal_evidences = tuple(
            QuestJournalCalibrationEvidence(
                game_version=DOFUS_361010_PROFILE.game_version,
                build_sha256=self.build_sha256,
                evidence_revision=DOFUS_361010_PROFILE.evidence_revision,
                source_commit=DOFUS_361010_PROFILE.source_commit,
                profile_digest=dofus_361010_profile_digest(),
                character_key=state.character_key,
                character_name=state.character_name,
                character_id=state.character_id,
                session_id=session_id,
                quest_journal_type_url=DOFUS_361010_PROFILE.quest_journal_type_url,
                journal_verified_quest_ids=tuple(sorted(state.journal_finished_ids)),
                journal_observation_count=state.journal_observation_count,
            )
            for session_id, state in self._sessions.items()
            if state.character_key
            and state.character_id > 0
            and state.journal_observation_count > 0
        )

        certificate = None
        if reason == "profile_calibrated" and best is not None:
            certificate = ProtocolCalibrationCertificate(
                game_version=DOFUS_361010_PROFILE.game_version,
                build_sha256=self.build_sha256,
                evidence_revision=DOFUS_361010_PROFILE.evidence_revision,
                source_commit=DOFUS_361010_PROFILE.source_commit,
                profile_digest=dofus_361010_profile_digest(),
                character_key=best.character_key,
                character_name=best.character_name,
                character_id=best.character_id,
                session_id=best_session_id,
                verified_quest_ids=tuple(sorted(best.completion_ids)),
                quest_journal_type_url=DOFUS_361010_PROFILE.quest_journal_type_url,
                journal_verified_quest_ids=tuple(sorted(best.journal_finished_ids)),
                journal_observation_count=journal_observation_count,
            )
        return ProtocolCalibrationStatus(
            ready=certificate is not None,
            reason=reason,
            build_sha256=self.build_sha256,
            identified_session_count=len(identified),
            max_distinct_completion_count=completion_count,
            quest_journal_observation_count=journal_observation_count,
            quest_journal_verified_count=journal_verified_count,
            journal_evidence=journal_evidence,
            journal_evidences=journal_evidences,
            certificate=certificate,
        )

    def _state_rank(self, state: _SessionCalibrationState) -> tuple[int, int, int, int]:
        return (
            1 if state.journal_observation_count > 0 else 0,
            min(len(state.completion_ids), self.minimum_distinct_completions),
            len(state.completion_ids),
            state.activity_sequence,
        )

    def _build_matches(self) -> bool:
        try:
            active = str(self.active_build_sha256_provider() or "").strip().casefold()
        except Exception:
            return False
        return active == self.build_sha256

    def _invalidate(self, reason: str) -> None:
        self._sessions.clear()
        self._pending_journals.clear()
        self._invalidated_reason = str(reason or "calibration_invalidated")
        hook = getattr(self.decoder, "reset", None)
        if callable(hook):
            hook()


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = [
    "CurrentProtocolCalibration",
    "ProtocolCalibrationCertificate",
    "ProtocolCalibrationStatus",
    "QuestJournalCalibrationEvidence",
]
