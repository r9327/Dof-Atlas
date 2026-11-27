from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app.constants import KEY_SELECTED_CHARACTER, KEY_TOPMOST, PROFILE_FILE
from app.core.character_identity import require_character_key
from app.core.file_stamp import resolved_file_revision
from app.core.json_store import read_json_validated, _write_json_atomic_unchecked
from app.core.progress_coordinator import coordinator_for


ProfileMutator = Callable[[dict[str, Any]], None]
_FIELD_CACHE_LOCK = RLock()
_FIELD_CACHE: OrderedDict[tuple[object, ...], dict[str, Any]] = OrderedDict()
_FIELD_CACHE_LIMIT = 16


class ProfileSettingsService:
    """Coordinate targeted mutations of the shared Atlas profile JSON.

    PROFILE_FILE contains unrelated shell, Organizer and encyclopedia settings.
    Every mutation therefore reloads the latest disk state while holding the
    per-path coordinator lock, applies only the requested change and publishes
    the coordinator generation after the atomic replacement.
    """

    def __init__(self, profile_path: Path = PROFILE_FILE) -> None:
        self.profile_path = Path(profile_path)

    @staticmethod
    def _coerce_payload(value: Any, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return dict(default or {})

    def load(self, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
        coordinator = coordinator_for(self.profile_path)
        with coordinator.lock:
            payload = read_json_validated(
                self.profile_path,
                dict(default or {}),
                self._profile_schema_error,
            )
            return deepcopy(self._coerce_payload(payload, default))

    def load_fields(
        self, keys: Iterable[str], default: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read a small strict projection without retaining the full profile.

        The cache is shared across live readers and keyed by the disk revision
        plus the coordinator generation. Missing/corrupt files never seed it.
        Mutations still reload and validate the complete document from disk.
        """
        fields = tuple(dict.fromkeys(str(key) for key in keys))
        if not fields:
            return {}
        coordinator = coordinator_for(self.profile_path)
        with coordinator.lock:
            identity, revision = resolved_file_revision(self.profile_path)
            generation = coordinator.generation
            key = (identity, revision, generation, fields)
            if revision is not None:
                with _FIELD_CACHE_LOCK:
                    cached = _FIELD_CACHE.get(key)
                    if cached is not None:
                        _FIELD_CACHE.move_to_end(key)
                        return deepcopy(cached)
            payload = read_json_validated(
                self.profile_path, dict(default or {}), self._profile_schema_error,
            )
            projected = {field: payload[field] for field in fields if field in payload}
            if revision is not None and resolved_file_revision(self.profile_path) == (identity, revision):
                with _FIELD_CACHE_LOCK:
                    for old in tuple(_FIELD_CACHE):
                        if old[0] == identity and old[1:3] != key[1:3]:
                            _FIELD_CACHE.pop(old)
                    _FIELD_CACHE[key] = deepcopy(projected)
                    _FIELD_CACHE.move_to_end(key)
                    while len(_FIELD_CACHE) > _FIELD_CACHE_LIMIT:
                        _FIELD_CACHE.popitem(last=False)
            return deepcopy(projected)

    def mutate(
        self,
        mutator: ProfileMutator,
        *,
        default: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        coordinator = coordinator_for(self.profile_path)
        with coordinator.lock:
            payload = self._coerce_payload(
                read_json_validated(
                    self.profile_path,
                    dict(default or {}),
                    self._profile_schema_error,
                ),
                default,
            )
            before = deepcopy(payload)
            mutator(payload)
            changed = payload != before
            if changed:
                _write_json_atomic_unchecked(self.profile_path, payload)
                coordinator.mark_changed()
            return deepcopy(payload), changed

    @staticmethod
    def _profile_schema_error(payload: Any) -> str | None:
        return None if isinstance(payload, dict) else "la racine doit être un objet"

    def update_values(
        self,
        values: Mapping[str, Any] | None = None,
        *,
        remove_keys: Iterable[str] = (),
        default: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        updates = dict(values or {})
        if KEY_SELECTED_CHARACTER in updates:
            selected = updates[KEY_SELECTED_CHARACTER]
            updates[KEY_SELECTED_CHARACTER] = (
                "" if selected == "" else require_character_key(selected)
            )
        removals = tuple(str(key) for key in remove_keys)

        def apply(payload: dict[str, Any]) -> None:
            for key in removals:
                payload.pop(key, None)
            payload.update(updates)

        return self.mutate(apply, default=default)

    def set_value(self, key: str, value: Any) -> bool:
        _payload, changed = self.update_values({str(key): value})
        return changed

    def remove_value(self, key: str) -> bool:
        _payload, changed = self.update_values(remove_keys=(str(key),))
        return changed

    def set_selected_character(self, character_key: str) -> bool:
        if character_key == "":
            return self.set_value(KEY_SELECTED_CHARACTER, "")
        return self.set_value(
            KEY_SELECTED_CHARACTER,
            require_character_key(character_key),
        )

    def clear_selected_character_if(self, character_key: str) -> bool:
        expected = str(character_key or "")
        changed = False

        def clear(payload: dict[str, Any]) -> None:
            nonlocal changed
            if str(payload.get(KEY_SELECTED_CHARACTER, "") or "") != expected:
                return
            payload[KEY_SELECTED_CHARACTER] = ""
            changed = True

        self.mutate(clear)
        return changed

    def set_topmost(self, enabled: bool) -> bool:
        return self.set_value(KEY_TOPMOST, bool(enabled))


__all__ = ["ProfileSettingsService"]
