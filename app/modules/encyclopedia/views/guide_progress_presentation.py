from __future__ import annotations


def guide_progress_noun(
    guide: object, total: int, *, empty_counts_as_quests: bool = False,
) -> str:
    """Share Guide progress wording with explicit legacy empty-route behavior."""
    steps = tuple(getattr(guide, "required_steps", ()) or ())
    quests_only = (not steps and empty_counts_as_quests) or (
        bool(steps) and all(step.step_type == "quest" for step in steps)
    )
    if total and quests_only:
        return "quête" if total == 1 else "quêtes"
    return "étape" if total == 1 else "étapes"


def guide_progress_state(completed: int, total: int) -> str:
    """Return the stable presentation state used by Guide progress widgets."""
    if total and completed >= total:
        return "Terminé"
    if completed > 0:
        return "En cours"
    return "Non commencé"


def guide_progress_style_state(completed: int, total: int) -> str:
    """Canonical Qt style role for Guide progress, separate from display text."""
    if total and completed >= total:
        return "done"
    return "partial" if completed else "todo"


__all__ = ["guide_progress_noun", "guide_progress_state", "guide_progress_style_state"]
