"""Pure, Qt-free integer codecs shared by Atlas services.

Use the strict positive parser for identifiers, and the legacy-compatible
optional parser when a Guide accepts any int-coercible value. The two
contracts deliberately differ for booleans and non-positive integers.
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


def optional_int(value: object) -> int | None:
    """Preserve Guide integer coercion: booleans and negatives are accepted."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
