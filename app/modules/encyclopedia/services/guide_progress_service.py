from __future__ import annotations

from pathlib import Path
from typing import Any

from app.constants import DATA_DIR
from app.core.character_identity import require_character_key
from app.core.json_store import read_json_resilient, write_json_atomic
from app.core.progress_coordinator import coordinator_for


GUIDE_PROGRESS_FILE = DATA_DIR / "encyclopedia" / "progress" / "guide_progress.json"


def _empty_progress() -> dict[str, Any]:
    return {"version": 1, "characters": {}}


class GuideProgressService:
    def __init__(self, path: Path = GUIDE_PROGRESS_FILE) -> None:
        self.path = Path(path)
        self._coordinator = coordinator_for(self.path)
        self._manual_steps_cache: dict[tuple[str, str], frozenset[str]] = {}
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()

    def _current_disk_signature(self) -> tuple[int, int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size)

    def _clear_manual_steps_cache(self) -> None:
        self._manual_steps_cache.clear()

    def _ensure_fresh(self) -> None:
        if self._seen_generation == self._coordinator.generation:
            return
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self.progress = self._load()
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._clear_manual_steps_cache()

    def refresh_if_changed(self) -> bool:
        with self._coordinator.lock:
            generation = self._coordinator.generation
            disk_signature = self._current_disk_signature()
            if generation == self._seen_generation and disk_signature == self._disk_signature:
                return False
            self.progress = self._load()
            self._seen_generation = generation
            self._disk_signature = self._current_disk_signature()
            self._clear_manual_steps_cache()
            return True

    def reload(self) -> dict[str, Any]:
        with self._coordinator.lock:
            generation = self._coordinator.generation
            disk_signature = self._current_disk_signature()
            if generation == self._seen_generation and disk_signature == self._disk_signature:
                return self.progress
            self.progress = self._load()
            self._seen_generation = generation
            self._disk_signature = self._current_disk_signature()
            self._clear_manual_steps_cache()
        return self.progress

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
            str(value)
            for value in values
            if isinstance(values, list) and str(value)
        )
        self._manual_steps_cache[key] = snapshot
        return snapshot

    def manual_steps(self, character_key: str, guide_id: str) -> set[str]:
        # Public callers keep receiving an isolated mutable set while hot
        # membership checks below share the immutable cached snapshot.
        return set(self._manual_steps_snapshot(character_key, guide_id))

    def is_manual_step_completed(self, character_key: str, guide_id: str, step_id: str) -> bool:
        return str(step_id) in self._manual_steps_snapshot(character_key, guide_id)

    def set_manual_step_completed(
        self,
        character_key: str,
        guide_id: str,
        step_id: str,
        completed: bool,
    ) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            # Always mutate the latest on-disk payload. The generation bump makes
            # every other live GuideProgressService refresh on its next read.
            self.progress = self._load()
            self._disk_signature = self._current_disk_signature()
            guide_steps = self._manual_steps_map(key)
            raw_values = guide_steps.get(str(guide_id), [])
            values = {
                str(value)
                for value in raw_values if isinstance(raw_values, list) and str(value)
            }
            if completed:
                values.add(str(step_id))
            else:
                values.discard(str(step_id))
            if values:
                guide_steps[str(guide_id)] = sorted(values)
            else:
                guide_steps.pop(str(guide_id), None)
            self._save_unlocked()
            self._seen_generation = self._coordinator.mark_changed()
            self._disk_signature = self._current_disk_signature()
            self._clear_manual_steps_cache()

    def save(self) -> None:
        """Persist a deliberate compatibility snapshot only when it is current."""
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self.progress = self._load()
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._clear_manual_steps_cache()
                raise RuntimeError(
                    "Guide progress snapshot is stale; reload and apply the mutation again."
                )
            self._validate_write_snapshot()
            self._save_unlocked()
            self._seen_generation = self._coordinator.mark_changed()
            self._disk_signature = self._current_disk_signature()
            self._clear_manual_steps_cache()

    def _save_unlocked(self) -> None:
        self._validate_write_snapshot()
        write_json_atomic(self.path, self.progress)

    def _load(self) -> dict[str, Any]:
        payload = read_json_resilient(self.path, _empty_progress())
        if not isinstance(payload, dict):
            return _empty_progress()
        payload.setdefault("version", 1)
        if not isinstance(payload.get("characters"), dict):
            payload["characters"] = {}
        return payload

    def _manual_steps_map(self, character_key: str) -> dict[str, list[str]]:
        characters = self.progress.setdefault("characters", {})
        if not isinstance(characters, dict):
            characters = {}
            self.progress["characters"] = characters
        key = require_character_key(character_key)
        character = characters.setdefault(key, {})
        if not isinstance(character, dict):
            character = {}
            characters[key] = character
        manual_steps = character.setdefault("manual_steps", {})
        if not isinstance(manual_steps, dict):
            manual_steps = {}
            character["manual_steps"] = manual_steps
        return manual_steps

    def _read_manual_steps_map(self, character_key: str) -> dict[str, list[str]]:
        characters = self.progress.get("characters", {})
        if not isinstance(characters, dict):
            return {}
        character = characters.get(str(character_key or "").strip(), {})
        if not isinstance(character, dict):
            return {}
        manual_steps = character.get("manual_steps", {})
        return manual_steps if isinstance(manual_steps, dict) else {}

    def _validate_write_snapshot(self) -> None:
        characters = self.progress.get("characters", {})
        if not isinstance(characters, dict):
            raise ValueError("progress characters must be a mapping")
        for character_key in characters:
            require_character_key(character_key)
