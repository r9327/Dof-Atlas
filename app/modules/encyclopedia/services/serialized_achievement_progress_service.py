from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.core.json_store import read_json_validated, write_json_atomic
from app.core.numbers import valid_list_int_ids
from app.core.character_identity import require_character_key
from app.core.progress_coordinator import (
    CoordinatedProgressReader, coordinator_for,
    complete_progress_root, empty_progress_payload as _empty_progress,
    progress_characters_for_validation, progress_mapping_values_error,
    read_progress_character, read_progress_mapping,
)
from app.modules.encyclopedia.services.progress_service import (
    ACHIEVEMENT_PROGRESS_FILE,
    AchievementProgressService as LegacyAchievementProgressService,
)


def read_json_resilient(path: Path, default: Any) -> Any:
    """Compatibility seam backed by strict achievement validation."""

    return read_json_validated(path, default, _achievement_progress_schema_error)


class AchievementProgressService(CoordinatedProgressReader, LegacyAchievementProgressService):
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
            self._record_snapshot_identity_locked()

    def _coordinated_load(self) -> dict[str, Any]:
        return self._load()

    def _coordinated_invalidate(self) -> None:
        self._invalidate_runtime_caches()

    def _load(self) -> dict[str, Any]:
        return complete_progress_root(read_json_resilient(self.path, _empty_progress()))

    def _invalidate_runtime_caches(self) -> None:
        self._completion_cache.clear()
        self._automatic_sync_cache.clear()

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
        character = read_progress_character(self.progress, key)
        value = character.get("alignment_order")
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
            self._require_current_snapshot_locked("Achievement")
            self._persist_progress_snapshot_locked(
                lambda: write_json_atomic(self.path, self.progress),
            )
            self._accept_snapshot_locked(changed=True)

    def set_achievement_completed(self, character_key: str, achievement_id: int, completed: bool) -> bool:
        return self.set_achievements_completed(character_key, (int(achievement_id),), completed)

    def set_achievements_completed(
        self,
        character_key: str,
        achievement_ids: Iterable[int],
        completed: bool = True,
    ) -> bool:
        """Publish one coordinated write for a batch of achievement completion changes."""
        key = require_character_key(character_key)
        ids = set(achievement_ids)
        if not ids:
            return False
        with self._coordinator.lock:
            self._replace_snapshot_locked(self._coordinator.generation)
            character = self._character(key)
            values = set(valid_list_int_ids(character.get("completed_achievements", [])))
            updated = values | ids if completed else values - ids
            if updated == values:
                return False
            character["completed_achievements"] = sorted(updated)
            self.save()
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
            self._replace_snapshot_locked(self._coordinator.generation)
            character = self._character(key)
            rows = read_progress_mapping(character, "completed_objectives")
            values = rows.get(str(int(achievement_id)), [])
            completed_ids = valid_list_int_ids(values)
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
            self._replace_snapshot_locked(self._coordinator.generation)
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
            self._replace_snapshot_locked(self._coordinator.generation)
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
            self.refresh_if_changed()
            return super().sync_from_quest_progress(
                key,
                achievement_provider,
                quest_progress_service,
                guide_provider,
            )


def _achievement_progress_schema_error(payload: Any) -> str | None:
    characters, error = progress_characters_for_validation(payload)
    if error is not None:
        return error
    for character_key, character in characters.items():
        for field in ("completed_achievements", "auto_completed_achievements"):
            if field in character and not isinstance(character[field], list):
                return f"characters[{character_key!r}].{field} doit être une liste"
        for field in ("completed_objectives", "auto_completed_objectives"):
            rows = character.get(field, {})
            if not isinstance(rows, dict):
                return f"characters[{character_key!r}].{field} doit être un objet"
            error = progress_mapping_values_error(field, rows, value_type=list)
            if error is not None:
                return error
        if "alignment_order" in character and not isinstance(character["alignment_order"], dict):
            return f"characters[{character_key!r}].alignment_order doit être un objet"
    return None


__all__ = ["ACHIEVEMENT_PROGRESS_FILE", "AchievementProgressService"]
