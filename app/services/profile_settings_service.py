from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app.constants import KEY_SELECTED_CHARACTER, KEY_TOPMOST, PROFILE_FILE
from app.core.character_identity import require_character_key
from app.core.json_store import read_json_resilient, _write_json_atomic_unchecked
from app.core.progress_coordinator import coordinator_for


ProfileMutator = Callable[[dict[str, Any]], None]


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
            payload = read_json_resilient(self.profile_path, dict(default or {}))
            return deepcopy(self._coerce_payload(payload, default))

    def mutate(
        self,
        mutator: ProfileMutator,
        *,
        default: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        coordinator = coordinator_for(self.profile_path)
        with coordinator.lock:
            payload = self._coerce_payload(
                read_json_resilient(self.profile_path, dict(default or {})),
                default,
            )
            before = deepcopy(payload)
            mutator(payload)
            changed = payload != before
            if changed:
                _write_json_atomic_unchecked(self.profile_path, payload)
                coordinator.mark_changed()
            return deepcopy(payload), changed

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
