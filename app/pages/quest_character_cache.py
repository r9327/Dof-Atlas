from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from app import quest_catalog as _quest_catalog
from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_SESSION_ORDER,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.core.json_store import read_json_resilient
from app.services.character_order_logic import (
    normalize_character_order,
    sort_character_rows,
)


_ORIGINAL_LOAD_QUEST_CHARACTERS = _quest_catalog.load_quest_characters
_LOCK = RLock()
_CACHE: dict[tuple[object, ...], tuple[_quest_catalog.QuestCharacter, ...]] = {}
_CACHE_ORDER: list[tuple[object, ...]] = []
_MAX_CACHE_ENTRIES = 16


def _file_stamp(path: Path | None) -> tuple[int, int]:
    if path is None:
        return (0, 0)
    try:
        stat = Path(path).stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _semantic_session_order(profile_path: Path) -> tuple[str, ...]:
    payload = read_json_resilient(profile_path, {})
    raw_order = payload.get(KEY_SESSION_ORDER, []) if isinstance(payload, dict) else []
    if not isinstance(raw_order, list):
        return ()
    return normalize_character_order(raw_order)


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
    return [
        _quest_catalog.QuestCharacter(
            key=row.key,
            label=row.label,
            slot=row.slot,
            connected=row.connected,
        )
        for row in rows
    ]


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
            return _clone_characters(cached)

    rows = _ORIGINAL_LOAD_QUEST_CHARACTERS(
        profile_path,
        client_index_path,
        slot_count,
        binding_path,
        connected_only,
    )
    rows = list(
        sort_character_rows(
            rows,
            _semantic_session_order(profile_path),
            label_getter=lambda row: row.label,
        )
    )
    frozen = tuple(
        _quest_catalog.QuestCharacter(
            key=row.key,
            label=row.label,
            slot=row.slot,
            connected=row.connected,
        )
        for row in rows
    )
    with _LOCK:
        cached = _CACHE.get(signature)
        if cached is None:
            _CACHE[signature] = frozen
            if signature not in _CACHE_ORDER:
                _CACHE_ORDER.append(signature)
            while len(_CACHE_ORDER) > _MAX_CACHE_ENTRIES:
                oldest = _CACHE_ORDER.pop(0)
                _CACHE.pop(oldest, None)
            cached = frozen
    return _clone_characters(cached)


def clear_quest_character_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _CACHE_ORDER.clear()


__all__ = [
    "cached_load_quest_characters",
    "clear_quest_character_cache",
    "quest_character_source_signature",
]
