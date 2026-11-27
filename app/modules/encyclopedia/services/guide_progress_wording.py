"""Shared Guide completion labels, independent of Qt and screen layout."""
from __future__ import annotations


def guide_progress_noun(
    guide: object, total: int, *, empty_counts_as_quests: bool = False,
) -> str:
    """Preserve distinct legacy labels for route cards and progress headers."""
    steps = tuple(getattr(guide, "required_steps", ()) or ())
    quests_only = (not steps and empty_counts_as_quests) or (
        bool(steps) and all(step.step_type == "quest" for step in steps)
    )
    if total and quests_only:
        return "quête" if total == 1 else "quêtes"
    return "étape" if total == 1 else "étapes"


__all__ = ["guide_progress_noun"]
