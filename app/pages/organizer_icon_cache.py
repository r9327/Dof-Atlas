from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from app.constants import NETWORK_CHARACTER_BINDINGS_FILE
from app.network.character_resolver import merge_verified_binding_classes
from app.pages import organizer_page as _organizer_page


_LOCK = RLock()
_SOURCE_STAMP: tuple[tuple[str, int, int], tuple[str, int, int]] | None = None
_CLASS_BY_CHARACTER: dict[str, str] = {}
_ICON_BY_CLASS: dict[str, Path] = {}
_PRESERVE_SIGNATURE: tuple[object, ...] | None = None


def _file_stamp(path: Path) -> tuple[str, int, int]:
    resolved = str(path.resolve())
    try:
        stat = path.stat()
    except OSError:
        return (resolved, 0, 0)
    return (resolved, int(stat.st_mtime_ns), int(stat.st_size))


def _client_index_path() -> Path:
    return Path(_organizer_page.CLIENT_INDEX_JSON)


def _binding_path() -> Path:
    return Path(NETWORK_CHARACTER_BINDINGS_FILE)


def _valid_class_key(value: Any) -> str:
    class_key = _organizer_page.normalize_key(value)
    return class_key if class_key in _organizer_page.DOFUS_CLASS_DEFINITIONS else ""


def _add_candidate(candidates: dict[str, set[str]], name: Any, class_key: Any) -> None:
    character_key = _organizer_page.normalize_key(name)
    resolved_class = _valid_class_key(class_key)
    if character_key and resolved_class:
        candidates.setdefault(character_key, set()).add(resolved_class)


def _collect_client_candidates(payload: object, candidates: dict[str, set[str]]) -> None:
    clients = payload.get("clients", []) if isinstance(payload, dict) else []
    for client in clients if isinstance(clients, list) else []:
        if not isinstance(client, dict):
            continue
        display_name = str(client.get("character_name") or "").strip()
        class_key = _valid_class_key(client.get("class_key"))
        if not class_key:
            class_key = _organizer_page.dofus_class_key_from_window_name(client.get("name")) or ""
        _add_candidate(candidates, display_name, class_key)


def _collect_binding_candidates(payload: object, candidates: dict[str, set[str]]) -> None:
    if not isinstance(payload, dict):
        return
    for group_name in ("characters", "legacy_slots", "slots"):
        rows = payload.get(group_name, {})
        for row in rows.values() if isinstance(rows, dict) else []:
            if not isinstance(row, dict):
                continue
            if str(row.get("source") or "") != "verified_network_identity":
                continue
            _add_candidate(candidates, row.get("name"), row.get("class_key"))


def _source_stamp() -> tuple[tuple[str, int, int], tuple[str, int, int]]:
    return (_file_stamp(_client_index_path()), _file_stamp(_binding_path()))


def _rebuild_character_class_cache(
    stamp: tuple[tuple[str, int, int], tuple[str, int, int]],
) -> None:
    global _SOURCE_STAMP, _CLASS_BY_CHARACTER

    candidates: dict[str, set[str]] = {}
    client_payload = _organizer_page.read_json(_client_index_path(), {"clients": []})
    binding_payload = _organizer_page.read_json(_binding_path(), {"slots": {}})
    _collect_client_candidates(client_payload, candidates)
    _collect_binding_candidates(binding_payload, candidates)

    _CLASS_BY_CHARACTER = {
        character_key: next(iter(class_keys))
        for character_key, class_keys in candidates.items()
        if len(class_keys) == 1
    }
    _SOURCE_STAMP = stamp


def _live_session_class_candidates(sessions: list[dict[str, Any]] | None) -> dict[str, set[str]]:
    candidates: dict[str, set[str]] = {}
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        raw_name = str(session.get("nom") or session.get("name") or "").strip()
        class_key = _organizer_page.dofus_class_key_from_window_name(raw_name)
        if not class_key:
            continue
        display_name = _organizer_page.clean_auto_group_name(raw_name) or raw_name
        _add_candidate(candidates, display_name, class_key)
    return candidates


def preserve_verified_character_classes(
    sessions: list[dict[str, Any]] | None = None,
) -> bool:
    """Keep known classes without preserving stale runtime window handles.

    Organizer deliberately rewrites ``client_index.json`` with no clients before
    the first asynchronous scan so macros cannot reuse stale HWND/PID values.
    Before that safe reset, copy only unambiguous class metadata onto character
    identities already verified by the passive network resolver. Current Unity
    titles can refresh that metadata when they explicitly expose a class.
    """

    global _PRESERVE_SIGNATURE, _SOURCE_STAMP

    session_candidates = _live_session_class_candidates(sessions)
    session_signature = tuple(
        sorted(
            (name, tuple(sorted(class_keys)))
            for name, class_keys in session_candidates.items()
        )
    )
    signature = (*_source_stamp(), session_signature)
    with _LOCK:
        if signature == _PRESERVE_SIGNATURE:
            return False

    candidates: dict[str, set[str]] = {}
    client_payload = _organizer_page.read_json(_client_index_path(), {"clients": []})
    _collect_client_candidates(client_payload, candidates)
    for character_key, class_keys in session_candidates.items():
        candidates.setdefault(character_key, set()).update(class_keys)

    changed = merge_verified_binding_classes(
        _binding_path(),
        candidates,
        set(_organizer_page.DOFUS_CLASS_DEFINITIONS),
    )
    final_signature = (*_source_stamp(), session_signature)
    with _LOCK:
        _PRESERVE_SIGNATURE = final_signature
        if changed:
            _SOURCE_STAMP = None
    return changed


def cached_dofus_class_key_for_character_name(value: Any) -> str | None:
    character_key = _organizer_page.normalize_key(value)
    if not character_key:
        return None
    stamp = _source_stamp()
    with _LOCK:
        if stamp != _SOURCE_STAMP:
            _rebuild_character_class_cache(stamp)
        return _CLASS_BY_CHARACTER.get(character_key)


def cached_class_icon_path_for_window_name(value: Any) -> Path | None:
    class_key = (
        _organizer_page.dofus_class_key_from_window_name(value)
        or cached_dofus_class_key_for_character_name(value)
    )
    if not class_key:
        return None
    with _LOCK:
        cached = _ICON_BY_CLASS.get(class_key)
        if cached is not None and cached.exists():
            return cached
    for path in _organizer_page.class_icon_candidates(class_key):
        if path.exists():
            with _LOCK:
                _ICON_BY_CLASS[class_key] = path
            return path
    return None


def clear_organizer_icon_cache() -> None:
    global _SOURCE_STAMP, _CLASS_BY_CHARACTER, _PRESERVE_SIGNATURE
    with _LOCK:
        _SOURCE_STAMP = None
        _CLASS_BY_CHARACTER = {}
        _PRESERVE_SIGNATURE = None
        _ICON_BY_CLASS.clear()


__all__ = [
    "cached_class_icon_path_for_window_name",
    "cached_dofus_class_key_for_character_name",
    "clear_organizer_icon_cache",
    "preserve_verified_character_classes",
]
