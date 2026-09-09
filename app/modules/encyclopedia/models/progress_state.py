from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProgressState:
    completed_achievements: set[int] = field(default_factory=set)
    completed_objectives: dict[int, set[int]] = field(default_factory=dict)

    def is_achievement_completed(self, achievement_id: int) -> bool:
        return int(achievement_id) in self.completed_achievements

    def is_objective_completed(self, achievement_id: int, objective_id: int) -> bool:
        return int(objective_id) in self.completed_objectives.get(int(achievement_id), set())
