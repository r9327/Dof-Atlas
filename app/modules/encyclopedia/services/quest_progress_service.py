from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.constants import QUEST_PROGRESS_FILE
from app.core.character_identity import require_character_key
from app.core.json_store import read_json_validated
from app.core.numbers import optional_int, valid_list_int_ids, valid_truthy_int_ids
from app.core.progress_coordinator import (
    CoordinatedProgressReader, coordinator_for,
    complete_progress_root, empty_progress_payload as _empty_progress,
    mutable_progress_character, progress_characters_for_validation, progress_mapping_values_error, read_progress_character,
    read_progress_mapping, mutable_progress_mapping, update_progress_flag,
)
from app.quest_catalog import save_quest_progress


def _quest_progress_schema_error(payload: Any) -> str | None:
    characters, error = progress_characters_for_validation(payload)
    if error is not None:
        return error
    for character_key, character in characters.items():
        for field in ("done", "completed_quest_objectives", "quest_items"):
            if field in character and not isinstance(character[field], dict):
                return f"characters[{character_key!r}].{field} doit être un objet"
        objectives = character.get("completed_quest_objectives", {})
        error = progress_mapping_values_error("completed_quest_objectives", objectives, value_type=list)
        if error is not None:
            return error
        error = progress_mapping_values_error("quest_items", character.get("quest_items", {}), value_type=dict)
        if error is not None:
            return error
    return None


def load_quest_progress(path: Path) -> dict[str, Any]:
    return complete_progress_root(
        read_json_validated(path, _empty_progress(), _quest_progress_schema_error)
    )


class QuestProgressService(CoordinatedProgressReader):
    """Local per-character quest, objective and quest-item progress.

    Multiple UI surfaces may own an instance simultaneously. Mutations always
    reload the latest file under a path-scoped lock, and every successful write
    bumps a shared generation. Other live instances then refresh lazily on their
    next read instead of displaying a stale snapshot indefinitely.
    """

    def __init__(self, path: Path = QUEST_PROGRESS_FILE) -> None:
        self.path = Path(path)
        self._coordinator = coordinator_for(self.path)
        self._completed_quest_ids_cache: dict[str, frozenset[int]] = {}
        self._completed_objective_ids_cache: dict[tuple[str, int], frozenset[int]] = {}
        self._completed_item_ids_cache: dict[tuple[str, int], frozenset[int]] = {}
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            self._record_snapshot_identity_locked()

    def _coordinated_load(self) -> dict[str, Any]:
        return load_quest_progress(self.path)

    def _coordinated_invalidate(self) -> None:
        self._completed_quest_ids_cache.clear()
        self._completed_objective_ids_cache.clear()
        self._completed_item_ids_cache.clear()

    def _completed_quest_ids_snapshot(self, character_key: str) -> frozenset[int]:
        self._ensure_fresh()
        key = str(character_key or "").strip()
        if not key:
            return frozenset()
        cached = self._completed_quest_ids_cache.get(key)
        if cached is not None:
            return cached
        character = self._read_character(key)
        done = character.get("done", {})
        snapshot = valid_truthy_int_ids(done)
        self._completed_quest_ids_cache[key] = snapshot
        return snapshot

    def is_quest_completed(self, character_key: str, quest_id: int) -> bool:
        return int(quest_id) in self._completed_quest_ids_snapshot(character_key)

    def completed_quest_ids(self, character_key: str) -> set[int]:
        return set(self._completed_quest_ids_snapshot(character_key))

    def set_quest_completed(self, character_key: str, quest_id: int, completed: bool) -> bool:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            done = mutable_progress_mapping(character, "done")
            if not update_progress_flag(done, str(int(quest_id)), completed):
                self._accept_snapshot_locked(changed=False)
                return False
            self._write_locked()
            return True

    def set_quests_completed(
        self,
        character_key: str,
        quest_ids: Iterable[int],
        completed: bool = True,
    ) -> bool:
        """Apply many quest completion flags with one coordinated atomic write.

        Network reconciliation can legitimately receive hundreds of completed
        quests in one authoritative server snapshot. Calling the scalar setter
        for every row would repeatedly reload and rewrite the same persistent
        JSON. This batch API preserves the exact same source of truth and lock
        contract while publishing at most one new generation.

        Returns ``True`` only when persistent state changed.
        """

        key = require_character_key(character_key)
        normalized: set[int] = set()
        for raw_quest_id in quest_ids:
            if isinstance(raw_quest_id, bool) or not isinstance(raw_quest_id, int):
                raise ValueError("quest_ids must contain positive integers")
            quest_id = int(raw_quest_id)
            if quest_id <= 0:
                raise ValueError("quest_ids must contain positive integers")
            normalized.add(quest_id)
        if not normalized:
            return False

        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            done = mutable_progress_mapping(character, "done")
            changed = False
            for quest_id in sorted(normalized):
                changed = update_progress_flag(done, str(quest_id), completed) or changed

            if not changed:
                # Keep this instance synchronized with the latest peer-written
                # snapshot without publishing a redundant generation.
                self._accept_snapshot_locked(changed=False)
                return False
            self._write_locked()
            return True

    def _completed_objective_ids_snapshot(
        self,
        character_key: str,
        quest_id: int,
    ) -> frozenset[int]:
        self._ensure_fresh()
        normalized_character_key = str(character_key or "").strip()
        if not normalized_character_key:
            return frozenset()
        key = (normalized_character_key, int(quest_id))
        cached = self._completed_objective_ids_cache.get(key)
        if cached is not None:
            return cached
        character = self._read_character(key[0])
        rows = read_progress_mapping(character, "completed_quest_objectives")
        values = rows.get(str(key[1]), [])
        snapshot = valid_list_int_ids(values)
        self._completed_objective_ids_cache[key] = snapshot
        return snapshot

    def completed_objectives(self, character_key: str, quest_id: int) -> set[int]:
        return set(self._completed_objective_ids_snapshot(character_key, int(quest_id)))

    def is_objective_completed(self, character_key: str, quest_id: int, objective_id: int) -> bool:
        quest_id = int(quest_id)
        if quest_id in self._completed_quest_ids_snapshot(character_key):
            return True
        return int(objective_id) in self._completed_objective_ids_snapshot(
            character_key,
            quest_id,
        )

    def set_objective_completed(
        self,
        character_key: str,
        quest_id: int,
        objective_id: int,
        completed: bool,
    ) -> bool:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            rows = mutable_progress_mapping(character, "completed_quest_objectives")
            key = str(int(quest_id))
            values = set(valid_list_int_ids(rows.get(key, [])))
            previous = set(values)
            if completed:
                values.add(int(objective_id))
            else:
                values.discard(int(objective_id))
            if values == previous:
                self._accept_snapshot_locked(changed=False)
                return False
            if values:
                rows[key] = sorted(values)
            else:
                rows.pop(key, None)
            self._write_locked()
            return True

    def _completed_item_ids_snapshot(
        self,
        character_key: str,
        quest_id: int,
    ) -> frozenset[int]:
        self._ensure_fresh()
        normalized_character_key = str(character_key or "").strip()
        if not normalized_character_key:
            return frozenset()
        key = (normalized_character_key, int(quest_id))
        cached = self._completed_item_ids_cache.get(key)
        if cached is not None:
            return cached
        character = self._read_character(key[0])
        items = read_progress_mapping(character, "quest_items")
        quest_items = read_progress_mapping(items, str(key[1]))
        snapshot = valid_truthy_int_ids(quest_items)
        self._completed_item_ids_cache[key] = snapshot
        return snapshot

    def is_item_completed(self, character_key: str, quest_id: int, item_id: int) -> bool:
        """Return one quest-item checkbox state from a fresh shared snapshot."""

        return int(item_id) in self._completed_item_ids_snapshot(character_key, int(quest_id))

    def completed_item_ids(self, character_key: str, quest_id: int) -> set[int]:
        """Return checked item ids while preserving the historical JSON shape."""

        return set(self._completed_item_ids_snapshot(character_key, int(quest_id)))

    def set_item_completed(
        self,
        character_key: str,
        quest_id: int,
        item_id: int,
        completed: bool,
    ) -> bool:
        """Mutate one quest-item checkbox under the shared file coordinator."""

        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            items = mutable_progress_mapping(character, "quest_items")
            quest_key = str(int(quest_id))
            quest_items = mutable_progress_mapping(items, quest_key)
            changed = update_progress_flag(quest_items, str(int(item_id)), completed)
            if not quest_items:
                items.pop(quest_key, None)
            if not changed:
                self._accept_snapshot_locked(changed=False)
                return False
            self._write_locked()
            return True

    def save(self) -> None:
        """Compatibility save for deliberate direct edits of ``progress``.

        Typed mutation methods remain the normal API. A compatibility caller is
        allowed to persist its local snapshot only while no peer instance has
        published a newer generation. Refusing a stale whole-file save is safer
        than silently overwriting progress written by another live surface.
        """
        with self._coordinator.lock:
            self._require_current_snapshot_locked("Quest")
            self._write_locked()

    def _write_locked(self) -> None:
        self._persist_progress_snapshot_locked(
            lambda: save_quest_progress(self.progress, self.path),
        )
        self._accept_snapshot_locked(changed=True)

    def _read_character(self, character_key: str) -> dict[str, Any]:
        return read_progress_character(self.progress, character_key)

    def _mutable_character(self, character_key: str) -> dict[str, Any]:
        character = mutable_progress_character(
            self.progress, character_key, defaults={"done": {}},
        )
        if not isinstance(character.get("done"), dict):
            character["done"] = {}
        return character

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        return optional_int(value)
