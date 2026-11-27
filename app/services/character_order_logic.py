from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from threading import RLock
from typing import TypeVar

from app.core.file_stamp import mtime_ctime_size_stamp

from app.constants import KEY_SESSION_ORDER
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


def character_order_from_profile(payload: object) -> tuple[str, ...]:
    """Decode a stored logical order without treating malformed data as labels."""
    raw = payload.get(KEY_SESSION_ORDER, []) if isinstance(payload, Mapping) else []
    return normalize_character_order(raw) if isinstance(raw, list) else ()


_ORDER_LOCK = RLock()
_ORDER_CACHE: OrderedDict[tuple[str, tuple[int, int, int], bool], tuple[str, ...]] = OrderedDict()


def load_character_order(path: Path, *, strict: bool = False) -> tuple[str, ...]:
    """Reuse only a stable on-disk projection; preserve strict profile readers."""
    from app.core.json_store import read_json_resilient
    path = Path(path)
    stamp = mtime_ctime_size_stamp(path)
    key = (str(path.resolve()), stamp, strict) if stamp is not None else None
    if key is not None:
        with _ORDER_LOCK:
            cached = _ORDER_CACHE.get(key)
            if cached is not None:
                _ORDER_CACHE.move_to_end(key)
                return cached
    if strict:
        from app.services.profile_settings_service import ProfileSettingsService
        payload = ProfileSettingsService(path).load()
    else:
        payload = read_json_resilient(path, None)
    order = character_order_from_profile(payload)
    if key is not None and isinstance(payload, Mapping) and mtime_ctime_size_stamp(path) == stamp:
        with _ORDER_LOCK:
            for old in tuple(_ORDER_CACHE):
                if old[0] == key[0] and old[1] != key[1]:
                    _ORDER_CACHE.pop(old)
            _ORDER_CACHE[key] = order
            _ORDER_CACHE.move_to_end(key)
            while len(_ORDER_CACHE) > 16:
                _ORDER_CACHE.popitem(last=False)
    return order


def clear_character_order_cache() -> None:
    with _ORDER_LOCK:
        _ORDER_CACHE.clear()


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
    # sorted() is stable: unknown characters preserve their input order,
    # without invoking the potentially costly label getter twice per row.
    return tuple(sorted(
        rows,
        key=lambda row: positions.get(normalize_key(label_getter(row)), fallback_index),
    ))


__all__ = ["character_order_from_profile", "normalize_character_order", "sort_character_rows", "load_character_order", "clear_character_order_cache"]
