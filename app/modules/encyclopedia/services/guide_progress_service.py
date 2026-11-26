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


def _preparation_resource_key(value: object) -> str:
    """Accept stable item IDs or the existing hashed-name fallback only."""
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("preparation resource requires a stable item key")
    if value.startswith("item:"):
        suffix = value.removeprefix("item:")
        if suffix.isdigit() and int(suffix) > 0 and str(int(suffix)) == suffix:
            return value
    if value.startswith("name:"):
        digest = value.removeprefix("name:")
        if len(digest) == 16 and all(ch in "0123456789abcdef" for ch in digest):
            return value
    raise ValueError("preparation resource must use item:<id> or name:<digest>")


def _preparation_guide_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 180:
        raise ValueError("preparation requires a stable guide ID")
    return value


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

    def preparation_quantity(
        self, character_key: str, guide_id: str, resource_key: str,
    ) -> int:
        """Read one explicit quantity; absent state is zero, not network stock."""
        key = require_character_key(character_key)
        guide = _preparation_guide_id(guide_id)
        resource = _preparation_resource_key(resource_key)
        self._ensure_fresh()
        return self._read_preparation_counts_map(key).get(guide, {}).get(resource, 0)

    def set_preparation_quantity(
        self, character_key: str, guide_id: str, resource_key: str,
        quantity: int, *, required: int, expected_quantity: int | None = None,
    ) -> bool:
        """Persist one character's manual amount via the shared atomic batch."""
        key = require_character_key(character_key)
        expected = {key: expected_quantity} if expected_quantity is not None else None
        return self.set_preparation_quantities_for_characters(
            guide_id, resource_key, {key: quantity}, {key: required},
            expected_quantities=expected,
        )

    def set_preparation_quantities_for_characters(
        self, guide_id: str, resource_key: str,
        quantities: dict[str, int], required_by_character: dict[str, int],
        *, expected_quantities: dict[str, int] | None = None,
    ) -> bool:
        """One compare-and-swap disk transaction for a selected Guide team.

        Caller verifies source authorization. Never deduce actual stock from
        a character's network session or from another character's inventory.
        """
        guide = _preparation_guide_id(guide_id)
        resource = _preparation_resource_key(resource_key)
        if not isinstance(quantities, dict) or not quantities:
            return False
        if not isinstance(required_by_character, dict):
            raise ValueError("required preparation amounts must be a character map")
        keys = tuple(require_character_key(value) for value in quantities)
        if (len(set(keys)) != len(keys) or
                set(keys) != set(required_by_character)):
            raise ValueError("preparation character set does not match requirements")
        if expected_quantities is not None and (
            not isinstance(expected_quantities, dict)
            or set(expected_quantities) != set(keys)
        ):
            raise ValueError("expected preparation states must match participants")
        for key in keys:
            amount = quantities[key]
            maximum = required_by_character[key]
            if (type(maximum) is not int or maximum < 0 or
                    type(amount) is not int or not 0 <= amount <= maximum):
                raise ValueError("preparation quantity outside required bounds")
            if expected_quantities is not None and (
                type(expected_quantities[key]) is not int
                or expected_quantities[key] < 0
            ):
                raise ValueError("invalid expected preparation quantity")
        with self._coordinator.lock:
            self.progress = self._load()
            current = {
                key: self._read_preparation_counts_map(key).get(guide, {}).get(resource, 0)
                for key in keys
            }
            if expected_quantities is not None and current != expected_quantities:
                self._accept_snapshot_locked(changed=False)
                raise RuntimeError("Preparation changed since reading; reload before editing")
            if all(current[key] == quantities[key] for key in keys):
                self._accept_snapshot_locked(changed=False)
                return False
            for key in keys:
                character = mutable_progress_character(self.progress, key)
                counts = mutable_progress_mapping(character, "preparation_counts")
                by_guide = counts.setdefault(guide, {})
                amount = quantities[key]
                if amount:
                    by_guide[resource] = amount
                else:
                    by_guide.pop(resource, None)
                    if not by_guide:
                        counts.pop(guide, None)
                    if not counts:
                        character.pop("preparation_counts", None)
            self._save_unlocked()
            self._accept_snapshot_locked(changed=True)
            return True

    def _read_preparation_counts_map(
        self, character_key: str,
    ) -> dict[str, dict[str, int]]:
        character = read_progress_character(self.progress, character_key)
        return read_progress_mapping(character, "preparation_counts")

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

    def _validate_write_snapshot(self) -> None:
        super()._validate_write_snapshot()
        invalid = _guide_progress_schema_error(self.progress)
        if invalid is not None:
            raise ValueError(invalid)


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
        counts = character.get("preparation_counts", {})
        if not isinstance(counts, dict):
            return f"characters[{character_key!r}].preparation_counts doit être un objet"
        for guide_id, resources in counts.items():
            try:
                _preparation_guide_id(guide_id)
            except ValueError:
                return f"preparation_counts: guide ID invalide {guide_id!r}"
            if not isinstance(resources, dict):
                return f"preparation_counts[{guide_id!r}] doit être un objet"
            for resource, quantity in resources.items():
                try:
                    _preparation_resource_key(resource)
                except ValueError:
                    return f"preparation_counts: ressource invalide {resource!r}"
                if type(quantity) is not int or quantity < 0:
                    return f"preparation_counts[{guide_id!r}][{resource!r}] est invalide"
    return None
