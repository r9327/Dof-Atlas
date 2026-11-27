from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TypeVar

from app.constants import KEY_SESSION_ORDER, PROFILE_FILE
from app.core.text import normalize_key
from app.services.character_order_logic import load_character_order, normalize_character_order, sort_character_rows
from app.services.profile_settings_service import ProfileSettingsService


_T = TypeVar("_T")


class CharacterOrderService:
    """Canonical persistence for the user-defined logical character order.

    ``KEY_SESSION_ORDER`` is kept for backward compatibility with existing
    profiles, but its value is now treated as a compact logical order rather
    than Organizer's eight physical UI slots. Legacy sparse lists remain
    readable and are compacted on the next valid save.
    """

    def __init__(self, profile_path: Path = PROFILE_FILE) -> None:
        self.profile_path = Path(profile_path)
        self.profile_settings = ProfileSettingsService(self.profile_path)

    def load_order(self) -> tuple[str, ...]:
        return load_character_order(self.profile_path, strict=True)

    def sort_rows(self, rows: Sequence[_T], *, label_getter) -> tuple[_T, ...]:
        """Use the same stable order policy as all non-persistent character views."""
        return sort_character_rows(rows, self.load_order(), label_getter=label_getter)

    @staticmethod
    def _normalized_labels(labels: Iterable[object]) -> list[str]:
        return list(normalize_character_order(labels))

    @classmethod
    def _compact_order(cls, raw_order: object, desired: Sequence[str]) -> list[str]:
        """Merge an explicit order without losing legacy/offline tokens.

        Characters present in ``desired`` are reordered relative to each other.
        Existing tokens absent from ``desired`` keep their logical anchor so a
        connected-only caller cannot silently erase or relocate an offline
        character. New desired characters are appended only when no existing
        logical position can host them.
        """

        existing = cls._normalized_labels(raw_order) if isinstance(raw_order, list) else []
        if not existing:
            return list(desired)

        desired_set = set(desired)
        reorder_positions = [
            index for index, key in enumerate(existing) if key in desired_set
        ]
        order = list(existing)

        placed = 0
        for index, key in zip(reorder_positions, desired):
            order[index] = key
            placed += 1

        order.extend(desired[placed:])
        return order

    def save_labels(self, labels: Iterable[str]) -> bool:
        desired = self._normalized_labels(labels)
        changed = False

        def save(payload: dict) -> None:
            nonlocal changed
            raw_order = payload.get(KEY_SESSION_ORDER, [])
            order = self._compact_order(raw_order, desired)
            if raw_order == order:
                return
            payload[KEY_SESSION_ORDER] = order
            changed = True

        self.profile_settings.mutate(save)
        return changed

    def remove_label(self, label: str) -> bool:
        """Remove one explicitly deleted character from the canonical order."""

        key = normalize_key(label)
        if not key:
            return False
        changed = False

        def remove(payload: dict) -> None:
            nonlocal changed
            raw_order = payload.get(KEY_SESSION_ORDER, [])
            if not isinstance(raw_order, list):
                return
            order = self._normalized_labels(raw_order)
            if key not in order:
                return
            payload[KEY_SESSION_ORDER] = [value for value in order if value != key]
            changed = True

        self.profile_settings.mutate(remove)
        return changed


__all__ = ["CharacterOrderService"]
