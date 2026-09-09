from __future__ import annotations

from typing import Any, Mapping


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def derive_completion_state(
    character: Mapping[str, Any],
) -> tuple[frozenset[int], dict[int, frozenset[int]]]:
    """Merge manual and derived achievement completion into the runtime state."""
    completed = {
        int(value)
        for value in character.get("completed_achievements", [])
        if _safe_int(value) is not None
    }
    completed.update(
        int(value)
        for value in character.get("auto_completed_achievements", [])
        if _safe_int(value) is not None
    )

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
            objectives.setdefault(aid, set()).update(
                int(value)
                for value in rows
                if _safe_int(value) is not None
            )

    return (
        frozenset(completed),
        {aid: frozenset(values) for aid, values in objectives.items()},
    )


__all__ = ["derive_completion_state"]
