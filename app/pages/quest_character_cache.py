from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any

from app import quest_catalog as _quest_catalog
from app.constants import (
    CLIENT_INDEX_JSON,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.core.file_stamp import mtime_ctime_size_stamp_or_zero
from app.core.json_store import read_json_resilient
from app.services.character_order_logic import (
    character_order_from_profile,
    sort_character_rows,
)


_ORIGINAL_LOAD_QUEST_CHARACTERS = _quest_catalog.load_quest_characters
_LOCK = RLock()
_CACHE: OrderedDict[tuple[object, ...], tuple[_quest_catalog.QuestCharacter, ...]] = OrderedDict()
_MAX_CACHE_ENTRIES = 16


def _file_stamp(path: Path | None) -> tuple[int, int, int]:
    return mtime_ctime_size_stamp_or_zero(path) if path is not None else (0, 0, 0)


def _semantic_session_order(profile_path: Path) -> tuple[str, ...]:
    return character_order_from_profile(read_json_resilient(profile_path, {}))


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
        _semantic_session_order(profile_path),
        str(client_index_path),
        _file_stamp(client_index_path),
        str(resolved_binding) if resolved_binding is not None else "",
        _file_stamp(resolved_binding),
        slot_count,
        bool(connected_only),
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
    if (_file_stamp(client_index_path) != signature[3]
            or _file_stamp(_resolved_binding_path(profile_path, client_index_path, binding_path)) != signature[5]):
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


__all__ = [
    "cached_load_quest_characters",
    "clear_quest_character_cache",
    "quest_character_source_signature",
]
