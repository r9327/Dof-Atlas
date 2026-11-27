from __future__ import annotations


from app.modules.encyclopedia.services.guide_progress_wording import guide_progress_noun


def _progress_status_index(completed: int, total: int) -> int:
    """Single completion boundary for visual and human-readable Guide states."""
    if total and completed >= total:
        return 2
    return 1 if completed > 0 else 0


def guide_progress_state(completed: int, total: int) -> str:
    """Return the stable presentation state used by Guide progress widgets."""
    return ("Non commencé", "En cours", "Terminé")[
        _progress_status_index(completed, total)
    ]


def guide_progress_style_state(completed: int, total: int) -> str:
    """Canonical Qt style role for Guide progress, separate from display text."""
    return ("todo", "partial", "done")[_progress_status_index(completed, total)]


__all__ = ["guide_progress_noun", "guide_progress_state", "guide_progress_style_state"]
