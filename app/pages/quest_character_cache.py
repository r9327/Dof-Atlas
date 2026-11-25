from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from threading import RLock

from app import quest_catalog as _quest_catalog
from app.constants import (
    CLIENT_INDEX_JSON,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.core.file_stamp import mtime_ctime_size_stamp_or_zero, file_revision
from app.services.character_order_logic import (
    load_character_order, clear_character_order_cache, sort_character_rows,
)


_ORIGINAL_LOAD_QUEST_CHARACTERS = _quest_catalog.load_quest_characters
_LOCK = RLock()
_CACHE: OrderedDict[tuple[object, ...], tuple[_quest_catalog.QuestCharacter, ...]] = OrderedDict()
_MAX_CACHE_ENTRIES = 16


def _resolved_binding_path(
    profile_path: Path,
    client_index_path: Path,
    binding_path: Path | None,
) -> Path | None:
    if binding_path is not None:
        return Path(binding_path)
    if profile_path == PROFILE_FILE and client_index_path == CLIENT_INDEX_JSON:
        return Path(NETWORK_CHARACTER_BINDINGS_FILE)
    return None


def quest_character_source_signature(
    profile_path: Path = PROFILE_FILE,
    client_index_path: Path = CLIENT_INDEX_JSON,
    slot_count: int = 8,
    binding_path: Path | None = None,
    connected_only: bool = False,
) -> tuple[object, ...]:
    profile_path = Path(profile_path)
    client_index_path = Path(client_index_path)
    slot_count = max(1, int(slot_count))
    resolved_binding = _resolved_binding_path(profile_path, client_index_path, binding_path)
    return (
        str(profile_path),
        load_character_order(profile_path),
        str(client_index_path),
        mtime_ctime_size_stamp_or_zero(client_index_path),
        str(resolved_binding) if resolved_binding is not None else "",
        mtime_ctime_size_stamp_or_zero(resolved_binding),
        slot_count,
        bool(connected_only),
        # Preserve the historical signature fields while also detecting an
        # atomic replacement with preserved size/timestamps on Windows.
        file_revision(client_index_path),
        file_revision(resolved_binding),
    )


def _clone_characters(
    rows: tuple[_quest_catalog.QuestCharacter, ...],
) -> list[_quest_catalog.QuestCharacter]:
    return [replace(row) for row in rows]


def cached_load_quest_characters(
    profile_path: Path = PROFILE_FILE,
    client_index_path: Path = CLIENT_INDEX_JSON,
    slot_count: int = 8,
    binding_path: Path | None = None,
    connected_only: bool = False,
) -> list[_quest_catalog.QuestCharacter]:
    profile_path = Path(profile_path)
    client_index_path = Path(client_index_path)
    signature = quest_character_source_signature(
        profile_path,
        client_index_path,
        slot_count,
        binding_path,
        connected_only,
    )
    with _LOCK:
        cached = _CACHE.get(signature)
        if cached is not None:
            _CACHE.move_to_end(signature)
            return _clone_characters(cached)

    rows = _ORIGINAL_LOAD_QUEST_CHARACTERS(
        profile_path,
        client_index_path,
        slot_count,
        binding_path,
        connected_only,
    )
    # Use the very order that keyed this load, not a second profile read.
    # Otherwise a concurrent reorder can store the wrong order under this key.
    ordered = sort_character_rows(rows, signature[1], label_getter=lambda row: row.label)
    frozen = tuple(replace(row) for row in ordered)
    # Avoid caching a roster read across a concurrent client/binding rewrite.
    # The logical order remains the single captured snapshot for this call.
    if (mtime_ctime_size_stamp_or_zero(client_index_path) != signature[3]
            or mtime_ctime_size_stamp_or_zero(_resolved_binding_path(profile_path, client_index_path, binding_path)) != signature[5]
            or file_revision(client_index_path) != signature[8]
            or file_revision(_resolved_binding_path(profile_path, client_index_path, binding_path)) != signature[9]):
        return _clone_characters(frozen)
    with _LOCK:
        cached = _CACHE.get(signature)
        if cached is None:
            _CACHE[signature] = frozen
            while len(_CACHE) > _MAX_CACHE_ENTRIES:
                _CACHE.popitem(last=False)
            cached = frozen
        _CACHE.move_to_end(signature)
    return _clone_characters(cached)


def clear_quest_character_cache() -> None:
    with _LOCK:
        _CACHE.clear()
    clear_character_order_cache()


__all__ = [
    "cached_load_quest_characters",
    "clear_quest_character_cache",
    "quest_character_source_signature",
]
