from __future__ import annotations

from typing import Any, Mapping
from app.core.numbers import clamped_percent, optional_int as _safe_int, valid_list_int_ids




def achievement_progress_percent(completed: bool, done: int, total: int) -> int:
    """Explicitly checked successes show 100% even with no visible objectives."""
    return 100 if completed else clamped_percent(done, total)


def derive_completion_state(
    character: Mapping[str, Any],
) -> tuple[frozenset[int], dict[int, frozenset[int]]]:
    """Merge manual and derived achievement completion into the runtime state."""
    completed: set[int] = set()
    for field in ("completed_achievements", "auto_completed_achievements"):
        completed.update(valid_list_int_ids(character.get(field, [])))

    objectives: dict[int, set[int]] = {}
    for field in ("completed_objectives", "auto_completed_objectives"):
        objective_rows = character.get(field, {})
        if not isinstance(objective_rows, dict):
            continue
        for achievement_id, values in objective_rows.items():
            aid = _safe_int(achievement_id)
            if aid is None:
                continue
            objectives.setdefault(aid, set()).update(valid_list_int_ids(values))

    return (
        frozenset(completed),
        {aid: frozenset(values) for aid, values in objectives.items()},
    )


__all__ = ["achievement_progress_percent", "derive_completion_state"]
