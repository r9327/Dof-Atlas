from __future__ import annotations

from typing import Any, Mapping
from app.core.numbers import optional_int as _safe_int, valid_int_ids




def derive_completion_state(
    character: Mapping[str, Any],
) -> tuple[frozenset[int], dict[int, frozenset[int]]]:
    """Merge manual and derived achievement completion into the runtime state."""
    completed = set(valid_int_ids(character.get("completed_achievements", [])))
    completed.update(valid_int_ids(character.get("auto_completed_achievements", [])))

    objectives: dict[int, set[int]] = {}
    for field in ("completed_objectives", "auto_completed_objectives"):
        objective_rows = character.get(field, {})
        if not isinstance(objective_rows, dict):
            continue
        for achievement_id, values in objective_rows.items():
            aid = _safe_int(achievement_id)
            if aid is None:
                continue
            rows = values if isinstance(values, list) else []
            objectives.setdefault(aid, set()).update(valid_int_ids(rows))

    return (
        frozenset(completed),
        {aid: frozenset(values) for aid, values in objectives.items()},
    )


__all__ = ["derive_completion_state"]
