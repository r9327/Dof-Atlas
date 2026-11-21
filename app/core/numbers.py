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


def coerce_positive_int(value: object) -> int | None:
    """Legacy network positive-integer coercion (True historically means 1).

    Keep this separate from positive_int, which must reject bool identifiers.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def optional_int(value: object, default: int | None = None) -> int | None:
    """Preserve legacy int coercion, returning the caller's optional fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
