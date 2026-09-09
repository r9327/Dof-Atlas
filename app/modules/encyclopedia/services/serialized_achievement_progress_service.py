from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.json_store import read_json_resilient, write_json_atomic
from app.core.character_identity import require_character_key
from app.core.progress_coordinator import coordinator_for
from app.modules.encyclopedia.services.achievement_progress_logic import derive_completion_state
from app.modules.encyclopedia.services.progress_service import (
    ACHIEVEMENT_PROGRESS_FILE,
    AchievementProgressService as LegacyAchievementProgressService,
)


def _empty_progress() -> dict[str, Any]:
    return {"version": 1, "characters": {}}


class AchievementProgressService(LegacyAchievementProgressService):
    """Concurrency-safe facade over the existing achievement progress engine.

    All instances for the same progress file share a lock and generation. Writes
    reload the latest payload before applying domain logic, while stale readers
    automatically refresh before returning state. Production persistence is
    routed through the common resilient JSON store; the inherited class remains
    domain compatibility only.
    """

    def __init__(self, path: Path = ACHIEVEMENT_PROGRESS_FILE) -> None:
        self._coordinator = coordinator_for(Path(path))
        with self._coordinator.lock:
            super().__init__(Path(path))
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()

    def _completion_state(
        self,
        character_key: str,
    ) -> tuple[frozenset[int], dict[int, frozenset[int]]]:
        key = str(character_key or "").strip()
        if not key:
            return frozenset(), {}
        cached = self._completion_cache.get(key)
        if cached is not None:
            return cached
        result = derive_completion_state(self._character(key))
        self._completion_cache[key] = result
        return result

    def _current_disk_signature(self) -> tuple[int, int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size)

    def _load(self) -> dict[str, Any]:
        payload = read_json_resilient(self.path, _empty_progress())
        if not isinstance(payload, dict):
            return _empty_progress()
        payload.setdefault("version", 1)
        if not isinstance(payload.get("characters"), dict):
            payload["characters"] = {}
        return payload

    def _invalidate_runtime_caches(self) -> None:
        self._completion_cache.clear()
        self._automatic_sync_cache.clear()

    def _ensure_fresh(self) -> None:
        # Hot completion reads intentionally use the in-process generation only.
        # External writers are detected by reload()/refresh_if_changed() without
        # adding a filesystem stat to every objective/achievement lookup.
        if self._seen_generation == self._coordinator.generation:
            return
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self.progress = self._load()
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._invalidate_runtime_caches()

    def refresh_if_changed(self) -> bool:
        with self._coordinator.lock:
            generation = self._coordinator.generation
            disk_signature = self._current_disk_signature()
            if generation == self._seen_generation and disk_signature == self._disk_signature:
                return False
            self.progress = self._load()
            self._seen_generation = generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
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
            self._invalidate_runtime_caches()
            return self.progress

    def state_for(self, character_key: str):
        self._ensure_fresh()
        return super().state_for(character_key)

    def is_achievement_completed(self, character_key: str, achievement_id: int) -> bool:
        self._ensure_fresh()
        return super().is_achievement_completed(character_key, achievement_id)

    def is_objective_completed(self, character_key: str, achievement_id: int, objective_id: int) -> bool:
        self._ensure_fresh()
        return super().is_objective_completed(character_key, achievement_id, objective_id)

    def alignment_order_choice(self, character_key: str) -> tuple[str, str] | None:
        self._ensure_fresh()
        return super().alignment_order_choice(character_key)

    def save(self) -> None:
        """Persist a compatibility snapshot only when no peer changed the file."""
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self.progress = self._load()
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._invalidate_runtime_caches()
                raise RuntimeError(
                    "Achievement progress snapshot is stale; reload and apply the mutation again."
                )
            self._validate_write_snapshot()
            write_json_atomic(self.path, self.progress)
            self._seen_generation = self._coordinator.mark_changed()
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()

    def set_achievement_completed(self, character_key: str, achievement_id: int, completed: bool) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            super().set_achievement_completed(key, achievement_id, completed)

    def set_objective_completed(
        self,
        character_key: str,
        achievement_id: int,
        objective_id: int,
        completed: bool,
    ) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            super().set_objective_completed(key, achievement_id, objective_id, completed)

    def set_alignment_order_choice(self, character_key: str, side: str, order_name: str) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            super().set_alignment_order_choice(key, side, order_name)

    def clear_alignment_order_choice(self, character_key: str) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            super().clear_alignment_order_choice(key)

    def sync_from_quest_progress(
        self,
        character_key: str,
        achievement_provider: Any,
        quest_progress_service: Any,
        guide_provider: Any = None,
    ) -> bool:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            # Unlike a mutation, synchronization does not need an unconditional
            # disk parse when no peer published a newer generation. The inherited
            # input signature then skips the expensive achievement graph pass when
            # quest/manual inputs are unchanged.
            self._ensure_fresh()
            return super().sync_from_quest_progress(
                key,
                achievement_provider,
                quest_progress_service,
                guide_provider,
            )

    def _validate_write_snapshot(self) -> None:
        characters = self.progress.get("characters", {})
        if not isinstance(characters, dict):
            raise ValueError("progress characters must be a mapping")
        for character_key in characters:
            require_character_key(character_key)


__all__ = ["ACHIEVEMENT_PROGRESS_FILE", "AchievementProgressService"]
