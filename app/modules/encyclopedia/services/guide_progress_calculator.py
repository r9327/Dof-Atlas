from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.modules.encyclopedia.models import Guide, GuideStep
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.guide_quest_view_model import trackable_quest_objective_ids
from app.quest_catalog import QuestRecord


@dataclass(frozen=True, slots=True)
class ProgressCount:
    completed: int
    total: int

    @property
    def is_complete(self) -> bool:
        return bool(self.total and self.completed >= self.total)


class GuideProgressCalculator:
    def __init__(
        self,
        quest_progress_service: QuestProgressService,
        guide_progress_service: GuideProgressService,
        achievement_progress_service: AchievementProgressService,
        quest_by_id: dict[int, QuestRecord],
    ) -> None:
        self.quest_progress_service = quest_progress_service
        self.guide_progress_service = guide_progress_service
        self.achievement_progress_service = achievement_progress_service
        self.quest_by_id = quest_by_id
        self._trackable_objective_ids: dict[int, tuple[int, ...]] = {}

    def guide_progress(self, guide: Guide, character_key: str) -> ProgressCount:
        return self.quest_steps_progress(guide, guide.required_steps, character_key)

    def quest_steps_progress(
        self,
        guide: Guide,
        steps: Iterable[GuideStep],
        character_key: str,
    ) -> ProgressCount:
        """Count the real, unique quest progress represented by a guide block."""
        return self.quest_ids_progress(
            guide.id,
            (step.entity_id for step in steps if (
                step.step_type == "quest"
                and step.entity_id is not None
                and step.counts_for_completion
            )),
            character_key,
        )

    def quest_ids_progress(
        self,
        guide_id: str,
        quest_ids: Iterable[int],
        character_key: str,
    ) -> ProgressCount:
        """Count unique quest progress without materializing GuideStep objects."""

        ids: list[int] = []
        seen: set[int] = set()
        for raw_id in quest_ids:
            quest_id = int(raw_id)
            if quest_id in seen:
                continue
            seen.add(quest_id)
            ids.append(quest_id)
        if not ids:
            return ProgressCount(0, 0)

        completed_quest_ids = self.quest_progress_service.completed_quest_ids(character_key)
        completed = 0
        for quest_id in ids:
            if quest_id in completed_quest_ids:
                completed += 1
                continue
            quest = self.quest_by_id.get(quest_id)
            if quest is None:
                continue
            if not self._objective_details_available(quest):
                if not self.quest_progress_service.completed_objectives(character_key, quest_id):
                    continue
            if self.quest_progress(quest, character_key, quest_completed=False).is_complete:
                completed += 1
        return ProgressCount(completed, len(ids))

    def steps_progress(self, guide: Guide, steps: Iterable[GuideStep], character_key: str) -> ProgressCount:
        required = [step for step in steps if step.counts_for_completion]
        if not required:
            return ProgressCount(0, 0)
        completed_quest_ids = self.quest_progress_service.completed_quest_ids(character_key)
        completed = sum(
            1
            for step in required
            if self.step_completed(
                guide,
                step,
                character_key,
                completed_quest_ids=completed_quest_ids,
            )
        )
        return ProgressCount(completed, len(required))

    def quest_progress(
        self,
        quest: QuestRecord,
        character_key: str,
        *,
        quest_completed: bool | None = None,
    ) -> ProgressCount:
        objective_ids = self._trackable_ids_for(quest)
        if not objective_ids:
            return ProgressCount(0, 0)
        if quest_completed is None:
            quest_completed = self.quest_progress_service.is_quest_completed(character_key, quest.id)
        if quest_completed:
            return ProgressCount(len(objective_ids), len(objective_ids))

        # Read the completed objective set once. The previous scalar loop called
        # is_objective_completed() for every objective, repeatedly resolving the
        # same character/quest maps and rebuilding the same set on long guides.
        completed_objective_ids = self.quest_progress_service.completed_objectives(
            character_key,
            quest.id,
        )
        completed = sum(1 for objective_id in objective_ids if objective_id in completed_objective_ids)
        return ProgressCount(completed, len(objective_ids))

    def _trackable_ids_for(self, quest: QuestRecord) -> tuple[int, ...]:
        quest_id = int(quest.id)
        objective_ids = self._trackable_objective_ids.get(quest_id)
        if objective_ids is None:
            objective_ids = self.trackable_objective_ids(quest)
            self._trackable_objective_ids[quest_id] = objective_ids
        return objective_ids

    @staticmethod
    def _objective_details_available(quest: QuestRecord) -> bool:
        """Return whether objective metadata is already resident for a lazy quest."""

        details = getattr(quest, "_details", None)
        cached = getattr(details, "cached", None)
        if not callable(cached):
            return True
        try:
            return bool(cached(int(quest.id)))
        except Exception:
            return False

    def step_completed(
        self,
        guide: Guide,
        step: GuideStep,
        character_key: str,
        *,
        completed_quest_ids: set[int] | frozenset[int] | None = None,
    ) -> bool:
        if step.step_type == "quest" and step.entity_id is not None:
            quest_id = int(step.entity_id)
            quest = self.quest_by_id.get(quest_id)
            if completed_quest_ids is None:
                quest_completed = self.quest_progress_service.is_quest_completed(character_key, quest_id)
            else:
                quest_completed = quest_id in completed_quest_ids
            if quest_completed:
                return True
            if quest is None:
                return False
            if not self._objective_details_available(quest):
                # Most Guide/Home rows have no objective-level progress. Avoid
                # synchronously loading every quest detail just to rediscover that
                # fact. If objective progress exists, preserve the historical
                # completion semantics and load only that specific quest detail.
                if not self.quest_progress_service.completed_objectives(
                    character_key,
                    quest_id,
                ):
                    return False
            return self.quest_progress(
                quest,
                character_key,
                quest_completed=False,
            ).is_complete
        if step.step_type == "info":
            return self.guide_progress_service.is_manual_step_completed(character_key, guide.id, step.id)
        if step.step_type == "achievement" and step.entity_id is not None:
            return self.achievement_progress_service.is_achievement_completed(character_key, int(step.entity_id))
        return False

    @staticmethod
    def trackable_objective_ids(quest: QuestRecord) -> tuple[int, ...]:
        return trackable_quest_objective_ids(quest)
