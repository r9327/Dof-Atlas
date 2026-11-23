from __future__ import annotations


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


__all__ = ["guide_progress_state", "guide_progress_style_state"]
