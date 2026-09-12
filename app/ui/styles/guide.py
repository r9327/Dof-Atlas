from __future__ import annotations

from app.ui.theme import atlas_stylesheet


# Compatibility imports only. Active views inherit the application stylesheet.
guide_manual_stylesheet = atlas_stylesheet
guide_universal_stylesheet = atlas_stylesheet
guide_v5_stylesheet = atlas_stylesheet


__all__ = [
    "guide_manual_stylesheet",
    "guide_universal_stylesheet",
    "guide_v5_stylesheet",
]
