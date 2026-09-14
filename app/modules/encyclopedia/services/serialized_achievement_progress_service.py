from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.json_store import read_json_validated, write_json_atomic
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
        payload = read_json_validated(
            self.path,
            _empty_progress(),
            _achievement_progress_schema_error,
        )
        payload.setdefault("version", 1)
        payload.setdefault("characters", {})
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

    @staticmethod
    def _alignment_orders(side: str) -> dict[str, tuple[int, ...]]:
        from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS

        rows = ORDER_QUEST_IDS.get(str(side), {})
        return rows if isinstance(rows, dict) else {}

    def alignment_order_choice(self, character_key: str) -> tuple[str, str] | None:
        key = str(character_key or "").strip()
        if not key:
            return None
        self._ensure_fresh()
        characters = self.progress.get("characters", {})
        character = characters.get(key, {}) if isinstance(characters, dict) else {}
        value = character.get("alignment_order") if isinstance(character, dict) else None
        if not isinstance(value, dict):
            return None
        side = str(value.get("side") or "").strip().casefold()
        if side not in {"bonta", "brakmar"}:
            return None
        orders = self._alignment_orders(side)

        order_id = self._safe_int(value.get("order_id"))
        if order_id is not None:
            for order_name, quest_ids in orders.items():
                if quest_ids and int(quest_ids[0]) == order_id:
                    return side, order_name
            return None

        # Compatibility read for profiles created before stable order IDs.
        legacy_order = str(value.get("order") or "").strip()
        if legacy_order in orders:
            return side, legacy_order
        return None

    @staticmethod
    def _alignment_order_signature(character: dict[str, Any]) -> tuple[str, str]:
        value = character.get("alignment_order")
        if not isinstance(value, dict):
            return ("", "")
        side = str(value.get("side") or "").strip().casefold()
        if value.get("order_id") is not None:
            return side, f"id:{value.get('order_id')}"
        return side, f"legacy:{str(value.get('order') or '').strip()}"

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

    def set_achievement_completed(self, character_key: str, achievement_id: int, completed: bool) -> bool:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            character = self._character(key)
            values = {
                int(value)
                for value in character.get("completed_achievements", [])
                if self._safe_int(value) is not None
            }
            achievement_id = int(achievement_id)
            if (achievement_id in values) == bool(completed):
                return False
            super().set_achievement_completed(key, achievement_id, completed)
            return True

    def set_objective_completed(
        self,
        character_key: str,
        achievement_id: int,
        objective_id: int,
        completed: bool,
    ) -> bool:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            character = self._character(key)
            rows = character.get("completed_objectives", {})
            values = rows.get(str(int(achievement_id)), []) if isinstance(rows, dict) else []
            completed_ids = {
                int(value)
                for value in values
                if isinstance(values, list) and self._safe_int(value) is not None
            }
            objective_id = int(objective_id)
            if (objective_id in completed_ids) == bool(completed):
                return False
            super().set_objective_completed(key, achievement_id, objective_id, completed)
            return True

    def set_alignment_order_choice(self, character_key: str, side: str, order_name: str) -> bool:
        key = require_character_key(character_key)
        normalized_side = str(side or "").strip().casefold()
        normalized_order = str(order_name or "").strip()
        if normalized_side not in {"bonta", "brakmar"}:
            raise ValueError(f"Cité d'alignement inconnue : {side!r}")
        quest_ids = self._alignment_orders(normalized_side).get(normalized_order)
        if not quest_ids:
            raise ValueError(f"Ordre d'alignement inconnu : {order_name!r}")
        order_id = int(quest_ids[0])
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            character = self._character(key)
            if self._alignment_order_signature(character) == (normalized_side, f"id:{order_id}"):
                return False
            character["alignment_order"] = {
                "side": normalized_side,
                "order_id": order_id,
            }
            self.save()
            return True

    def clear_alignment_order_choice(self, character_key: str) -> bool:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = self._load()
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()
            self._invalidate_runtime_caches()
            character = self._character(key)
            if "alignment_order" not in character:
                return False
            super().clear_alignment_order_choice(key)
            return True

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


def _achievement_progress_schema_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "la racine doit être un objet"
    if payload.get("version", 1) != 1:
        return f"version inconnue: {payload.get('version')!r}"
    characters = payload.get("characters", {})
    if not isinstance(characters, dict):
        return "characters doit être un objet"
    for character_key, character in characters.items():
        if not isinstance(character, dict):
            return f"characters[{character_key!r}] doit être un objet"
        for field in ("completed_achievements", "auto_completed_achievements"):
            if field in character and not isinstance(character[field], list):
                return f"characters[{character_key!r}].{field} doit être une liste"
        for field in ("completed_objectives", "auto_completed_objectives"):
            rows = character.get(field, {})
            if not isinstance(rows, dict):
                return f"characters[{character_key!r}].{field} doit être un objet"
            for achievement_id, values in rows.items():
                if not isinstance(values, list):
                    return f"{field}[{achievement_id!r}] doit être une liste"
        if "alignment_order" in character and not isinstance(character["alignment_order"], dict):
            return f"characters[{character_key!r}].alignment_order doit être un objet"
    return None


__all__ = ["ACHIEVEMENT_PROGRESS_FILE", "AchievementProgressService"]
