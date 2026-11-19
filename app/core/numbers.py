"""Pure, strict positive integer codec for local Atlas contracts.

Reject bool, invalid encodings and overflow without importing Qt, network,
filesystem or game data. Callers with different integer semantics keep their
own validators rather than silently changing behavior.
"""
from __future__ import annotations


def positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None
