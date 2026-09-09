from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock, local
from typing import Any

from app import storage as _storage
from app.constants import PROFILE_FILE
from app.services.profile_settings_service import ProfileSettingsService


_ORIGINAL_READ_JSON = _storage.read_json
_ORIGINAL_WRITE_JSON = _storage.write_json
_PROFILE_CACHE_LOCK = RLock()
_PROFILE_CACHE_STAMP: tuple[int, int, int] | None = None
_PROFILE_CACHE_VALUE: dict[str, Any] | None = None
_PROFILE_THREAD_STATE = local()


def _profile_stamp(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return (int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size))


def _remember_profile_snapshot(payload: Any) -> None:
    if isinstance(payload, dict):
        _PROFILE_THREAD_STATE.last_read = deepcopy(payload)
    else:
        _PROFILE_THREAD_STATE.last_read = None


def _publish_profile_cache(path: Path, payload: Any) -> None:
    global _PROFILE_CACHE_STAMP, _PROFILE_CACHE_VALUE
    stamp = _profile_stamp(path)
    with _PROFILE_CACHE_LOCK:
        if stamp is None or not isinstance(payload, dict):
            _PROFILE_CACHE_STAMP = None
            _PROFILE_CACHE_VALUE = None
            return
        _PROFILE_CACHE_STAMP = stamp
        _PROFILE_CACHE_VALUE = deepcopy(payload)


def clear_profile_runtime_cache() -> None:
    global _PROFILE_CACHE_STAMP, _PROFILE_CACHE_VALUE
    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE_STAMP = None
        _PROFILE_CACHE_VALUE = None
    _PROFILE_THREAD_STATE.last_read = None


def cached_read_json(path: Path, default: Any) -> Any:
    """Reuse the small shell profile while preserving independent mutable snapshots."""

    global _PROFILE_CACHE_STAMP, _PROFILE_CACHE_VALUE

    resolved = Path(path)
    if resolved != Path(PROFILE_FILE):
        return _ORIGINAL_READ_JSON(resolved, default)

    before = _profile_stamp(resolved)
    if before is not None:
        with _PROFILE_CACHE_LOCK:
            if before == _PROFILE_CACHE_STAMP and _PROFILE_CACHE_VALUE is not None:
                value = deepcopy(_PROFILE_CACHE_VALUE)
                _remember_profile_snapshot(value)
                return value

    value = _ORIGINAL_READ_JSON(resolved, default)
    after = _profile_stamp(resolved)
    # Atomic profile writes replace the path. Only cache a read when the file
    # signature stayed stable across the operation, avoiding a stale snapshot
    # being published under a newer replacement's stamp.
    if before is not None and before == after and isinstance(value, dict):
        with _PROFILE_CACHE_LOCK:
            _PROFILE_CACHE_STAMP = after
            _PROFILE_CACHE_VALUE = deepcopy(value)
    _remember_profile_snapshot(value)
    return value


def cached_write_json(path: Path, payload: Any) -> None:
    """Coordinate legacy PROFILE_FILE read/mutate/write callers by top-level delta.

    Several old shell/UI callers still perform ``read_json(PROFILE_FILE)``,
    mutate one setting, then pass the whole dictionary back to ``write_json``.
    The dictionary may be stale by then. Keep that compatibility API, but derive
    only the caller's changes from its last profile read and replay those changes
    through ProfileSettingsService, which reloads the latest disk state while
    holding the shared per-path coordinator lock.

    Non-profile JSON writes remain untouched. A profile write without a prior
    dictionary read keeps replacement semantics, but still executes while
    holding the same coordinator lock so it cannot race another canonical
    profile mutation.
    """

    resolved = Path(path)
    if resolved != Path(PROFILE_FILE):
        _ORIGINAL_WRITE_JSON(resolved, payload)
        return

    service = ProfileSettingsService(resolved)
    baseline = getattr(_PROFILE_THREAD_STATE, "last_read", None)

    if isinstance(payload, dict) and isinstance(baseline, dict):
        sentinel = object()
        updates: dict[str, Any] = {}
        removals: list[str] = []
        for key in set(baseline) | set(payload):
            before = baseline.get(key, sentinel)
            after = payload.get(key, sentinel)
            if before == after:
                continue
            if after is sentinel:
                removals.append(str(key))
            else:
                updates[str(key)] = after

        saved, _changed = service.update_values(updates, remove_keys=removals)
        _publish_profile_cache(resolved, saved)
        _remember_profile_snapshot(saved)
        return

    if isinstance(payload, dict):
        replacement = deepcopy(payload)

        def replace(current: dict[str, Any]) -> None:
            current.clear()
            current.update(replacement)

        saved, _changed = service.mutate(replace)
        _publish_profile_cache(resolved, saved)
        _remember_profile_snapshot(saved)
        return

    # PROFILE_FILE is expected to be a mapping. Preserve the historical generic
    # fallback for malformed/external callers rather than changing that contract.
    _ORIGINAL_WRITE_JSON(resolved, payload)
    clear_profile_runtime_cache()


__all__ = [
    "cached_read_json",
    "cached_write_json",
    "clear_profile_runtime_cache",
]
