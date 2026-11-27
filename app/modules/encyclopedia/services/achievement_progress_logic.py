from __future__ import annotations

from typing import Any, Mapping
from app.core.numbers import clamped_percent, optional_int as _safe_int, valid_list_int_ids




def achievement_progress_percent(completed: bool, done: int, total: int) -> int:
    """Explicitly checked successes show 100% even with no visible objectives."""
    return 100 if completed else clamped_percent(done, total)


def achievement_objective_counts_for_progress(achievement: Any, objective: Any) -> bool:
    """One existing Success progress policy, including hidden QQ counters."""
    kind = str(getattr(objective, "objective_type", "") or "").strip().casefold()
    category = str(getattr(achievement, "category_name", "") or "").casefold()
    return kind not in {"critère pl", "critère ea"} and not (
        kind == "critère bi" and category == "quêtes"
    )


def achievement_progress_snapshot(
    achievement: Any, state: Any, overrides: Mapping[int, bool] | None = None,
) -> tuple[int, int, bool, int]:
    """Return counts and effective completion from the same progress snapshot."""
    aid = int(getattr(achievement, "id", 0) or 0)
    overrides = overrides or {}
    objectives = tuple(objective for objective in getattr(achievement, "objectives", ()) or ()
                       if achievement_objective_counts_for_progress(achievement, objective))
    done = 0
    for objective in objectives:
        oid = int(getattr(objective, "id", 0) or 0)
        if oid in overrides:
            done += bool(overrides[oid])
        elif state is not None and aid:
            done += bool(state.is_objective_completed(aid, oid))
    total = len(objectives)
    completed = bool(state.is_achievement_completed(aid)) if state is not None and aid else False
    return done, total, completed, achievement_progress_percent(completed, done, total)


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


__all__ = [
    "achievement_progress_percent", "achievement_objective_counts_for_progress",
    "achievement_progress_snapshot", "derive_completion_state",
]
