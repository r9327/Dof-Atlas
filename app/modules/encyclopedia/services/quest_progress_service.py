from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.constants import QUEST_PROGRESS_FILE
from app.core.character_identity import require_character_key
from app.core.progress_coordinator import coordinator_for
from app.quest_catalog import load_quest_progress, save_quest_progress


class QuestProgressService:
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
            self._seen_generation = self._coordinator.generation
            self._disk_signature = self._current_disk_signature()

    def _current_disk_signature(self) -> tuple[int, int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size)

    def _clear_read_caches(self) -> None:
        self._completed_quest_ids_cache.clear()
        self._completed_objective_ids_cache.clear()
        self._completed_item_ids_cache.clear()

    def _ensure_fresh(self) -> None:
        if self._seen_generation == self._coordinator.generation:
            return
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self.progress = load_quest_progress(self.path)
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._clear_read_caches()

    def refresh_if_changed(self) -> bool:
        """Refresh only when coordinated or on-disk progress actually changed.

        The coordinator generation catches writes from live Atlas services. The
        file signature additionally preserves detection of an external writer
        without reparsing the JSON merely because a tab became visible again.
        """

        with self._coordinator.lock:
            generation = self._coordinator.generation
            disk_signature = self._current_disk_signature()
            if generation == self._seen_generation and disk_signature == self._disk_signature:
                return False
            self.progress = load_quest_progress(self.path)
            self._seen_generation = generation
            self._disk_signature = self._current_disk_signature()
            self._clear_read_caches()
            return True

    def reload(self) -> dict[str, Any]:
        """Reload progress when the coordinated generation or file changed."""

        with self._coordinator.lock:
            generation = self._coordinator.generation
            disk_signature = self._current_disk_signature()
            if generation == self._seen_generation and disk_signature == self._disk_signature:
                return self.progress
            self.progress = load_quest_progress(self.path)
            self._seen_generation = generation
            self._disk_signature = self._current_disk_signature()
            self._clear_read_caches()
        return self.progress

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
        if not isinstance(done, dict):
            snapshot = frozenset()
        else:
            snapshot = frozenset(
                int(quest_id)
                for quest_id, completed in done.items()
                if completed and self._safe_int(quest_id) is not None
            )
        self._completed_quest_ids_cache[key] = snapshot
        return snapshot

    def is_quest_completed(self, character_key: str, quest_id: int) -> bool:
        return int(quest_id) in self._completed_quest_ids_snapshot(character_key)

    def completed_quest_ids(self, character_key: str) -> set[int]:
        return set(self._completed_quest_ids_snapshot(character_key))

    def set_quest_completed(self, character_key: str, quest_id: int, completed: bool) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            done = character.get("done")
            if not isinstance(done, dict):
                done = {}
                character["done"] = done
            key = str(int(quest_id))
            if completed:
                done[key] = True
            else:
                done.pop(key, None)
            self._write_locked()

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
            done = character.get("done")
            if not isinstance(done, dict):
                done = {}
                character["done"] = done

            changed = False
            for quest_id in sorted(normalized):
                key = str(quest_id)
                if completed:
                    if done.get(key) is True:
                        continue
                    done[key] = True
                    changed = True
                elif key in done:
                    done.pop(key, None)
                    changed = True

            if not changed:
                # Keep this instance synchronized with the latest peer-written
                # snapshot without publishing a redundant generation.
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._clear_read_caches()
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
        rows = character.get("completed_quest_objectives", {})
        values = rows.get(str(key[1]), []) if isinstance(rows, dict) else []
        if not isinstance(values, list):
            snapshot = frozenset()
        else:
            snapshot = frozenset(
                int(value)
                for value in values
                if self._safe_int(value) is not None
            )
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
    ) -> None:
        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            rows = character.setdefault("completed_quest_objectives", {})
            if not isinstance(rows, dict):
                rows = {}
                character["completed_quest_objectives"] = rows
            key = str(int(quest_id))
            values = {
                int(value)
                for value in rows.get(key, [])
                if self._safe_int(value) is not None
            }
            if completed:
                values.add(int(objective_id))
            else:
                values.discard(int(objective_id))
            if values:
                rows[key] = sorted(values)
            else:
                rows.pop(key, None)
            self._write_locked()

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
        items = character.get("quest_items", {})
        quest_items = items.get(str(key[1]), {}) if isinstance(items, dict) else {}
        if not isinstance(quest_items, dict):
            snapshot = frozenset()
        else:
            snapshot = frozenset(
                int(item_id)
                for item_id, completed in quest_items.items()
                if completed and self._safe_int(item_id) is not None
            )
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
    ) -> None:
        """Mutate one quest-item checkbox under the shared file coordinator."""

        key = require_character_key(character_key)
        with self._coordinator.lock:
            self.progress = load_quest_progress(self.path)
            character = self._mutable_character(key)
            items = character.setdefault("quest_items", {})
            if not isinstance(items, dict):
                items = {}
                character["quest_items"] = items
            quest_key = str(int(quest_id))
            quest_items = items.setdefault(quest_key, {})
            if not isinstance(quest_items, dict):
                quest_items = {}
                items[quest_key] = quest_items
            item_key = str(int(item_id))
            if completed:
                quest_items[item_key] = True
            else:
                quest_items.pop(item_key, None)
                if not quest_items:
                    items.pop(quest_key, None)
            self._write_locked()

    def save(self) -> None:
        """Compatibility save for deliberate direct edits of ``progress``.

        Typed mutation methods remain the normal API. A compatibility caller is
        allowed to persist its local snapshot only while no peer instance has
        published a newer generation. Refusing a stale whole-file save is safer
        than silently overwriting progress written by another live surface.
        """
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self.progress = load_quest_progress(self.path)
                self._seen_generation = self._coordinator.generation
                self._disk_signature = self._current_disk_signature()
                self._clear_read_caches()
                raise RuntimeError(
                    "Quest progress snapshot is stale; reload and apply the mutation again."
                )
            self._validate_write_snapshot()
            save_quest_progress(self.progress, self.path)
            self._seen_generation = self._coordinator.mark_changed()
            self._disk_signature = self._current_disk_signature()
            self._clear_read_caches()

    def _write_locked(self) -> None:
        self._validate_write_snapshot()
        save_quest_progress(self.progress, self.path)
        self._seen_generation = self._coordinator.mark_changed()
        self._disk_signature = self._current_disk_signature()
        self._clear_read_caches()

    def _read_character(self, character_key: str) -> dict[str, Any]:
        characters = self.progress.get("characters", {})
        if not isinstance(characters, dict):
            return {}
        key = str(character_key or "").strip()
        if not key:
            return {}
        character = characters.get(key, {})
        return character if isinstance(character, dict) else {}

    def _mutable_character(self, character_key: str) -> dict[str, Any]:
        characters = self.progress.setdefault("characters", {})
        if not isinstance(characters, dict):
            characters = {}
            self.progress["characters"] = characters
        key = require_character_key(character_key)
        character = characters.setdefault(key, {"done": {}})
        if not isinstance(character, dict):
            character = {"done": {}}
            characters[key] = character
        if not isinstance(character.get("done"), dict):
            character["done"] = {}
        return character

    def _validate_write_snapshot(self) -> None:
        characters = self.progress.get("characters", {})
        if not isinstance(characters, dict):
            raise ValueError("progress characters must be a mapping")
        for character_key in characters:
            require_character_key(character_key)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
