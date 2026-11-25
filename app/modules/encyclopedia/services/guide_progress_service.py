from __future__ import annotations

from pathlib import Path
from typing import Any

from app.constants import DATA_DIR
from app.core.character_identity import require_character_key
from app.core.json_store import read_json_validated, write_json_atomic
from app.core.progress_coordinator import (
    CoordinatedProgressReader, coordinator_for,
    complete_progress_root, empty_progress_payload as _empty_progress,
    mutable_progress_character, progress_characters_for_validation, progress_mapping_values_error, read_progress_character,
    read_progress_mapping, mutable_progress_mapping,
)


GUIDE_PROGRESS_FILE = DATA_DIR / "encyclopedia" / "progress" / "guide_progress.json"


def read_json_resilient(path: Path, default: Any) -> Any:
    """Compatibility seam backed by strict Guide progress validation."""

    return read_json_validated(path, default, _guide_progress_schema_error)


class GuideProgressService(CoordinatedProgressReader):
    def __init__(self, path: Path = GUIDE_PROGRESS_FILE) -> None:
        self.path = Path(path)
        self._coordinator = coordinator_for(self.path)
        self._manual_steps_cache: dict[tuple[str, str], frozenset[str]] = {}
        with self._coordinator.lock:
            self.progress = self._load()
            self._record_snapshot_identity_locked()

    def _coordinated_load(self) -> dict[str, Any]:
        return self._load()

    def _coordinated_invalidate(self) -> None:
        self._manual_steps_cache.clear()

    def _manual_steps_snapshot(self, character_key: str, guide_id: str) -> frozenset[str]:
        self._ensure_fresh()
        normalized_character_key = str(character_key or "").strip()
        if not normalized_character_key:
            return frozenset()
        key = (normalized_character_key, str(guide_id))
        cached = self._manual_steps_cache.get(key)
        if cached is not None:
            return cached
        guide_steps = self._read_manual_steps_map(key[0])
        values = guide_steps.get(key[1], [])
        snapshot = frozenset(
            str(value) for value in (values if isinstance(values, list) else ())
            if str(value)
        )
        self._manual_steps_cache[key] = snapshot
        return snapshot

    def manual_steps(self, character_key: str, guide_id: str) -> set[str]:
        """Return a detached set; callers must not mutate cached snapshots."""
        # Public callers keep receiving an isolated mutable set while hot
        # membership checks below share the immutable cached snapshot.
        return set(self._manual_steps_snapshot(character_key, guide_id))

    def is_manual_step_completed(self, character_key: str, guide_id: str, step_id: str) -> bool:
        return str(step_id) in self._manual_steps_snapshot(character_key, guide_id)

    def set_manual_steps_for_characters(
        self, character_keys, guide_id: str, step_id: str, completed: bool,
        *, expected_completed: dict[str, bool] | None = None,
    ) -> bool:
        """Apply one explicit multi-character check in a single atomic write."""
        keys = tuple(require_character_key(key) for key in character_keys)
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate character in manual progress selection")
        if not keys:
            return False
        if expected_completed is not None and set(expected_completed) != set(keys):
            raise ValueError("expected manual states must match selected characters")
        with self._coordinator.lock:
            self.progress = self._load()
            self._disk_signature = self._current_disk_signature()
            if expected_completed is not None:
                for key in keys:
                    previous_steps = self._read_manual_steps_map(key).get(str(guide_id), [])
                    previous = (
                        str(step_id) in {str(value) for value in previous_steps}
                        if isinstance(previous_steps, list) else False
                    )
                    if previous != bool(expected_completed[key]):
                        self._seen_generation = self._coordinator.generation
                        self._coordinated_invalidate()
                        raise RuntimeError("Guide progress changed since selection; reload before validating")
            changed = False
            for key in keys:
                guide_steps = self._manual_steps_map(key)
                raw = guide_steps.get(str(guide_id), [])
                previous = {str(value) for value in raw if str(value)} if isinstance(raw, list) else set()
                updated = set(previous)
                if completed:
                    updated.add(str(step_id))
                else:
                    updated.discard(str(step_id))
                if updated == previous:
                    continue
                changed = True
                if updated:
                    guide_steps[str(guide_id)] = sorted(updated)
                else:
                    guide_steps.pop(str(guide_id), None)
            if changed:
                self._save_unlocked()
            self._accept_snapshot_locked(changed=changed)
            return changed

    def set_manual_step_completed(
        self,
        character_key: str,
        guide_id: str,
        step_id: str,
        completed: bool,
    ) -> bool:
        return self.set_manual_steps_for_characters(
            (character_key,), guide_id, step_id, completed,
        )

    def save(self) -> None:
        """Persist a deliberate compatibility snapshot only when it is current."""
        with self._coordinator.lock:
            self._require_current_snapshot_locked("Guide")
            self._save_unlocked()
            self._accept_snapshot_locked(changed=True)

    def _save_unlocked(self) -> None:
        self._persist_progress_snapshot_locked(
            lambda: write_json_atomic(self.path, self.progress),
        )

    def _load(self) -> dict[str, Any]:
        return complete_progress_root(read_json_resilient(self.path, _empty_progress()))

    def _manual_steps_map(self, character_key: str) -> dict[str, list[str]]:
        character = mutable_progress_character(self.progress, character_key)
        return mutable_progress_mapping(character, "manual_steps")

    def _read_manual_steps_map(self, character_key: str) -> dict[str, list[str]]:
        character = read_progress_character(self.progress, character_key)
        return read_progress_mapping(character, "manual_steps")

def _guide_progress_schema_error(payload: Any) -> str | None:
    characters, error = progress_characters_for_validation(payload)
    if error is not None:
        return error
    for character_key, character in characters.items():
        manual_steps = character.get("manual_steps", {})
        if not isinstance(manual_steps, dict):
            return f"characters[{character_key!r}].manual_steps doit être un objet"
        error = progress_mapping_values_error("manual_steps", manual_steps, value_type=list)
        if error is not None:
            return error
    return None
