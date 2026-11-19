"""Pure-data coordinate normalization shared by the Guide and Macro paths.

The caller is responsible for matching its own input format (bracketed
source coordinates or DOFUS chat commands). Never import Qt or Windows here.
"""
from __future__ import annotations


def normalize_coordinate_pair(
    x: str, y: str, *, lower_exclusive: int = -(2**31),
) -> str | None:
    """Return canonical signed coordinates without accepting overflow.

    Keep the historical ten-digit input limit and reject the reserved
    signed-32-bit lower bound. A caller may provide its source sentinel.
    """
    parts = (x, y)
    if any(len(part.lstrip("-")) > 10 for part in parts):
        return None
    try:
        first, second = (int(part) for part in parts)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(lower_exclusive < value < 2**31 for value in (first, second)):
        return None
    return f"{first},{second}"
