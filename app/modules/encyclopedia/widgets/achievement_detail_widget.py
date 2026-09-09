from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Callable

from PySide6.QtWidgets import QCheckBox, QFrame, QLabel, QProgressBar, QSizePolicy, QVBoxLayout

from app.modules.encyclopedia.models.achievement import Achievement, AchievementObjective
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService
from app.modules.encyclopedia.widgets.achievement_entity_section import AchievementEntitySection
from app.modules.encyclopedia.widgets.achievement_objective_widget import AchievementObjectiveWidget
from app.modules.encyclopedia.widgets.achievement_reward_widget import AchievementRewardWidget


_HIDDEN_OBJECTIVE_TYPES = {"critère pl", "critère ea", "critère qq"}


class AchievementDetailWidget(QFrame):
    def __init__(
        self,
        achievement: Achievement,
        progress_service: AchievementProgressService,
        character_key: str,
        navigate_callback: Callable[[str, int], bool] | None = None,
        linked_quests: Iterable[EntityRef] | None = None,
        linked_monsters: Iterable[EntityRef] | None = None,
        linked_dungeons: Iterable[EntityRef] | None = None,
        objective_completion_overrides: Mapping[int, bool] | None = None,
        readonly_objective_ids: Iterable[int] = (),
        objective_entity_overrides: Mapping[int, EntityRef] | None = None,
        objective_text_overrides: Mapping[int, str] | None = None,
        completion_changed_callback: Callable[[bool], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AchievementDetailBody")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.achievement = achievement
        self.progress_service = progress_service
        self.character_key = character_key
        self.navigate_callback = navigate_callback
        self.completion_changed_callback = completion_changed_callback
        self.linked_quests = tuple(achievement.linked_quests if linked_quests is None else linked_quests)
        self.linked_monsters = tuple(achievement.linked_monsters if linked_monsters is None else linked_monsters)
        self.linked_dungeons = tuple(achievement.linked_dungeons if linked_dungeons is None else linked_dungeons)
        self.objective_completion_overrides = {
            int(key): bool(value) for key, value in (objective_completion_overrides or {}).items()
        }
        self.readonly_objective_ids = {int(value) for value in readonly_objective_ids}
        self.objective_entity_overrides = {
            int(key): value for key, value in (objective_entity_overrides or {}).items()
        }
        self.objective_text_overrides = {
            int(key): str(value) for key, value in (objective_text_overrides or {}).items()
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel(achievement.name)
        title.setObjectName("AchievementDetailTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        if achievement.description:
            description = QLabel(achievement.description)
            description.setObjectName("AchievementDescription")
            description.setWordWrap(True)
            layout.addWidget(description)

        state = progress_service.state_for(character_key)

        def objective_completed(objective_id: int) -> bool:
            if int(objective_id) in self.objective_completion_overrides:
                return self.objective_completion_overrides[int(objective_id)]
            return state.is_objective_completed(achievement.id, int(objective_id))

        progress_objectives = tuple(
            objective
            for objective in achievement.objectives
            if self._counts_for_progress(achievement, objective)
        )
        done = sum(1 for objective in progress_objectives if objective_completed(objective.id))
        total = len(progress_objectives)
        completed = state.is_achievement_completed(achievement.id)
        percent = 100 if completed else int(round((done / total) * 100)) if total else 0

        check = QCheckBox("Succès terminé")
        check.setObjectName("AchievementDoneCheck")
        check.setChecked(completed)
        check.toggled.connect(self._set_achievement_completed)
        layout.addWidget(check)

        self._progress_done = done
        self._progress_total = total
        self.progress_text = QLabel(f"Progression • {done} / {total} objectif(s) • {percent} %")
        self.progress_text.setObjectName("AchievementProgressText")
        layout.addWidget(self.progress_text)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("EncyclopediaProgressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(percent)
        layout.addWidget(self.progress_bar)

        visible_objectives = tuple(
            objective
            for objective in achievement.objectives
            if self._show_objective(achievement, objective)
        )
        quests_replace_objectives = achievement.category_name.casefold() == "quêtes" and bool(self.linked_quests)

        if quests_replace_objectives:
            self._add_entity_section(layout, "Quêtes", self.linked_quests)
        elif visible_objectives:
            section = QLabel("Objectifs")
            section.setObjectName("AchievementSectionTitle")
            layout.addWidget(section)
            for objective in visible_objectives:
                objective_id = int(objective.id)
                widget = AchievementObjectiveWidget(
                    objective,
                    objective_completed(objective_id),
                    progress_service=(
                        None if objective_id in self.readonly_objective_ids else progress_service
                    ),
                    character_key=character_key,
                    text_override=self.objective_text_overrides.get(objective_id),
                    entity_ref_override=self.objective_entity_overrides.get(objective_id),
                    navigate_callback=self.navigate_callback,
                )
                layout.addWidget(widget)

        visible_rewards = [
            reward
            for reward in achievement.rewards
            if str(getattr(reward, "kind", "") or "") not in {"xp", "xp_ratio", "kamas_ratio", "guild_points"}
        ]
        if visible_rewards:
            rewards = QLabel("Récompenses")
            rewards.setObjectName("AchievementSectionTitle")
            layout.addWidget(rewards)
            for reward in visible_rewards:
                layout.addWidget(AchievementRewardWidget(reward))

        # Donjon details already expose the useful monster/success requirement
        # directly in Objectifs. Repeating "Monstres · 1" / "Donjons · 1" adds
        # noise and duplicates the same relation.
        if achievement.category_name.casefold() != "donjons":
            if not quests_replace_objectives:
                self._add_entity_section(layout, "Quêtes", self.linked_quests)
            self._add_entity_section(layout, "Monstres", self.linked_monsters)
            self._add_entity_section(layout, "Donjons", self.linked_dungeons)
        self._add_entity_section(layout, "Succès liés", achievement.linked_achievements)

    @staticmethod
    def _counts_for_progress(achievement: Achievement, objective: AchievementObjective) -> bool:
        objective_type = str(objective.objective_type or "").strip().casefold()
        if objective_type in {"critère pl", "critère ea"}:
            return False
        if objective_type == "critère bi" and achievement.category_name.casefold() == "quêtes":
            return False
        return True

    @classmethod
    def _show_objective(cls, achievement: Achievement, objective: AchievementObjective) -> bool:
        objective_type = str(objective.objective_type or "").strip().casefold()
        if objective_type in _HIDDEN_OBJECTIVE_TYPES:
            return False
        if objective_type == "critère bi" and achievement.category_name.casefold() == "quêtes":
            return False
        return True

    def _set_achievement_completed(self, completed: bool) -> None:
        self.progress_service.set_achievement_completed(
            self.character_key,
            self.achievement.id,
            bool(completed),
        )
        percent = 100 if completed else int(round((self._progress_done / self._progress_total) * 100)) if self._progress_total else 0
        self.progress_text.setText(
            f"Progression • {self._progress_done} / {self._progress_total} objectif(s) • {percent} %"
        )
        self.progress_bar.setValue(percent)
        if self.completion_changed_callback is not None:
            self.completion_changed_callback(bool(completed))

    def _add_entity_section(self, layout: QVBoxLayout, title: str, refs: Iterable[EntityRef]) -> None:
        rows = tuple(refs)
        if not rows:
            return
        layout.addWidget(
            AchievementEntitySection(
                title,
                rows,
                navigate_callback=self.navigate_callback,
            )
        )
