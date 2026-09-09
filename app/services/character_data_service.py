from __future__ import annotations

from pathlib import Path
from threading import RLock

from app.constants import (
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
    QUEST_PROGRESS_FILE,
)
from app.core.character_identity import character_id_from_key
from app.core.json_store import read_json_resilient, write_json_atomic
from app.modules.encyclopedia.services.guide_progress_service import GUIDE_PROGRESS_FILE
from app.modules.encyclopedia.services.progress_coordinator import coordinator_for
from app.modules.encyclopedia.services.progress_service import ACHIEVEMENT_PROGRESS_FILE
from app.network.character_resolver import _BINDING_LOCK as _NETWORK_BINDING_LOCK
from app.network.character_runtime_state import character_runtime_state
from app.services.character_order_service import CharacterOrderService
from app.services.profile_settings_service import ProfileSettingsService


_DELETE_LOCK = RLock()


class CharacterDataService:
    """Delete Atlas-owned data for one verified character identity.

    The live client index is deliberately not mutated here: it represents the
    current Windows/Dofus runtime, not saved Atlas character data. If a deleted
    character is still connected, passive Npcap detection may legitimately
    learn it again later.
    """

    def __init__(
        self,
        *,
        profile_path: Path = PROFILE_FILE,
        binding_path: Path = NETWORK_CHARACTER_BINDINGS_FILE,
        quest_progress_path: Path = QUEST_PROGRESS_FILE,
        achievement_progress_path: Path = ACHIEVEMENT_PROGRESS_FILE,
        guide_progress_path: Path = GUIDE_PROGRESS_FILE,
    ) -> None:
        self.profile_path = Path(profile_path)
        self.profile_settings = ProfileSettingsService(self.profile_path)
        self.binding_path = Path(binding_path)
        self.progress_paths = (
            Path(quest_progress_path),
            Path(achievement_progress_path),
            Path(guide_progress_path),
        )

    @staticmethod
    def _character_id(character_key: str) -> int | None:
        return character_id_from_key(character_key)

    def delete_character(self, character_key: str) -> bool:
        key = str(character_key or "").strip()
        character_id = self._character_id(key)
        if character_id is None:
            return False

        changed = False
        with _DELETE_LOCK:
            order_label = self._binding_name(character_id)
            for path in self.progress_paths:
                changed = self._remove_progress_character(path, key) or changed
            changed = self._remove_binding(character_id) or changed
            if order_label:
                changed = (
                    CharacterOrderService(self.profile_path).remove_label(order_label)
                    or changed
                )
            changed = self._clear_selected_profile_key(key) or changed
            changed = character_runtime_state().remove_character(key) or changed
        return changed

    @staticmethod
    def _remove_progress_character(path: Path, character_key: str) -> bool:
        coordinator = coordinator_for(path)
        with coordinator.lock:
            payload = read_json_resilient(path, {"version": 1, "characters": {}})
            if not isinstance(payload, dict):
                payload = {"version": 1, "characters": {}}
            characters = payload.get("characters")
            if not isinstance(characters, dict) or character_key not in characters:
                return False
            characters.pop(character_key, None)
            write_json_atomic(path, payload)
            coordinator.mark_changed()
            return True

    def _binding_name(self, character_id: int) -> str:
        """Resolve the saved name for a verified identity before deleting it."""

        with _NETWORK_BINDING_LOCK:
            payload = read_json_resilient(self.binding_path, {})
            if not isinstance(payload, dict):
                return ""

            characters = payload.get("characters")
            row = characters.get(str(character_id)) if isinstance(characters, dict) else None
            if isinstance(row, dict):
                name = str(row.get("name") or "").strip()
                if name:
                    return name

            old_slots = payload.get("slots")
            if not isinstance(old_slots, dict):
                return ""
            for row in old_slots.values():
                if not isinstance(row, dict):
                    continue
                try:
                    row_character_id = int(row.get("character_id"))
                except (TypeError, ValueError):
                    continue
                if row_character_id != character_id:
                    continue
                name = str(row.get("name") or "").strip()
                if name:
                    return name
        return ""

    def _remove_binding(self, character_id: int) -> bool:
        # CharacterSlotResolver and class enrichment use this exact same lock.
        # Holding it across reload -> mutation -> atomic replace prevents either
        # writer from publishing an older snapshot over an independent update.
        with _NETWORK_BINDING_LOCK:
            payload = read_json_resilient(self.binding_path, {})
            if not isinstance(payload, dict):
                payload = {}
            changed = False
            characters = payload.get("characters")
            if isinstance(characters, dict) and str(character_id) in characters:
                characters.pop(str(character_id), None)
                changed = True

            old_slots = payload.get("slots")
            if isinstance(old_slots, dict):
                stale_slots: list[str] = []
                for raw_slot, row in old_slots.items():
                    if not isinstance(row, dict):
                        continue
                    try:
                        row_character_id = int(row.get("character_id"))
                    except (TypeError, ValueError):
                        continue
                    if row_character_id == character_id:
                        stale_slots.append(str(raw_slot))
                for raw_slot in stale_slots:
                    old_slots.pop(raw_slot, None)
                    changed = True

            if changed:
                write_json_atomic(self.binding_path, payload)
            return changed

    def _clear_selected_profile_key(self, character_key: str) -> bool:
        return self.profile_settings.clear_selected_character_if(character_key)


__all__ = ["CharacterDataService"]
