"""Pure, Qt-free integer codecs shared by Atlas services.

Use the strict positive parser for identifiers, and the legacy-compatible
optional parser when a Guide accepts any int-coercible value. The two
contracts deliberately differ for booleans and non-positive integers.
"""
from __future__ import annotations

from collections.abc import Iterable


INT32_MAX = (1 << 31) - 1
INT32_MIN = -(1 << 31)


def clamp_int32(value: int) -> int:
    """Clamp Python integers to the signed native range used by Qt editors."""
    return max(INT32_MIN, min(INT32_MAX, value))


def positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return coerce_positive_int(value)


def coerce_positive_int(value: object) -> int | None:
    """Legacy network positive-integer coercion (True historically means 1).

    Keep this separate from positive_int, which must reject bool identifiers.
    """
    parsed = optional_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def optional_int(value: object, default: int | None = None) -> int | None:
    """Preserve legacy int coercion, returning the caller's optional fallback."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def valid_int_ids(values: Iterable[object]) -> frozenset[int]:
    """Decode legacy completion IDs once, omitting invalid values."""
    return frozenset(
        parsed for raw in values if (parsed := optional_int(raw)) is not None
    )


def ordered_int_ids(values: Iterable[object]) -> tuple[int, ...]:
    """Decode once, deduplicate in source order and avoid quadratic list scans."""
    return tuple(dict.fromkeys(
        parsed for raw in values if (parsed := optional_int(raw)) is not None
    ))


def valid_list_int_ids(values: object) -> frozenset[int]:
    """Decode persisted JSON ID lists; malformed containers never imply completion."""
    return valid_int_ids(values) if isinstance(values, list) else frozenset()


def valid_truthy_int_ids(values: object) -> frozenset[int]:
    """Decode IDs from the persisted Quest boolean-map representation."""
    if not isinstance(values, dict):
        return frozenset()
    return valid_int_ids(raw for raw, completed in values.items() if completed)


def exact_native_integer(
    value: object, maximum: int, *, allow_zero: bool = False,
) -> int | None:
    """Accept exact bounded native IDs, never float, bool or Unicode digits."""
    if type(value) is int:
        parsed = value
    elif type(value) is str and value.isascii() and value.strip().isdecimal():
        try:
            parsed = int(value.strip())
        except (ValueError, OverflowError):
            return None
    else:
        return None
    return parsed if (0 if allow_zero else 1) <= parsed <= maximum else None


def clamped_percent(completed: int, total: int) -> int:
    """Apply Atlas' rounded whole-percent rule for bounded progress bars."""
    if not total:
        return 0
    return max(0, min(100, int(round((completed / total) * 100))))


def format_grouped_int(value: int) -> str:
    """Format UI counts with stable space grouping, independently of system locale."""
    return f"{int(value):,}".replace(",", " ")
