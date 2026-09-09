from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

from app.core.text import normalize_key


_T = TypeVar("_T")


def normalize_character_order(labels: Iterable[object]) -> tuple[str, ...]:
    """Return the compact, normalized logical character order."""

    order: list[str] = []
    seen: set[str] = set()
    for raw_label in labels:
        key = normalize_key(raw_label)
        if not key or key in seen:
            continue
        seen.add(key)
        order.append(key)
    return tuple(order)


def sort_character_rows(
    rows: Sequence[_T],
    order: Iterable[object],
    *,
    label_getter: Callable[[_T], object],
) -> tuple[_T, ...]:
    """Stable-sort rows by the canonical logical character order."""

    positions = {
        key: index
        for index, key in enumerate(normalize_character_order(order))
    }
    fallback_index = len(positions)
    indexed = tuple(enumerate(rows))
    return tuple(
        row
        for _original_index, row in sorted(
            indexed,
            key=lambda pair: (
                positions.get(normalize_key(label_getter(pair[1])), fallback_index),
                0 if normalize_key(label_getter(pair[1])) in positions else 1,
                pair[0],
            ),
        )
    )


__all__ = ["normalize_character_order", "sort_character_rows"]
