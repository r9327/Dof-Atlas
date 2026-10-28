from __future__ import annotations

from pathlib import Path

from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_GUIDE_PARTICIPANTS,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.core.character_identity import character_key, is_character_key
from app.core.json_store import read_json_resilient
from app.core.profile_settings import default_profiles
from app.quest_catalog import QuestCharacter, load_quest_characters
from app.services.profile_settings_service import ProfileSettingsService


class GuideParticipantService:
    """Persist explicit ID-backed Guide movement participants."""

    def __init__(
        self,
        profile_path: Path = PROFILE_FILE,
        client_index_path: Path = CLIENT_INDEX_JSON,
        binding_path: Path = NETWORK_CHARACTER_BINDINGS_FILE,
    ) -> None:
        self.profile_path = Path(profile_path)
        self.client_index_path = Path(client_index_path)
        self.binding_path = Path(binding_path)
        self.settings = ProfileSettingsService(self.profile_path)

    def _verified_keys(self) -> set[str]:
        """Only network-proven identities are eligible as Guide participants."""
        payload = read_json_resilient(self.binding_path, {})
        rows = payload.get("characters", {}) if isinstance(payload, dict) else {}
        verified: set[str] = set()
        for raw_id, row in rows.items() if isinstance(rows, dict) else ():
            if not isinstance(row, dict) or row.get("source") != "verified_network_identity":
                continue
            try:
                verified.add(character_key(raw_id))
            except ValueError:
                continue
        # Pre-registry verified rows stored their genuine Dofus ID under
        # character_id; the Organizer slot itself is never used as identity.
        slots = payload.get("slots", {}) if isinstance(payload, dict) else {}
        for row in slots.values() if isinstance(slots, dict) else ():
            if not isinstance(row, dict) or row.get("source") != "verified_network_identity":
                continue
            try:
                verified.add(character_key(row.get("character_id")))
            except ValueError:
                continue
        return verified

    def available_characters(self) -> tuple[QuestCharacter, ...]:
        verified = self._verified_keys()
        return tuple(
            row
            for row in load_quest_characters(
                self.profile_path,
                self.client_index_path,
                binding_path=self.binding_path,
                connected_only=False,
            )
            if row.key in verified
        )

    def selected_keys(self) -> tuple[str, ...]:
        payload = self.settings.load(default_profiles())
        values = payload.get(KEY_GUIDE_PARTICIPANTS, [])
        if not isinstance(values, list):
            return ()
        verified = self._verified_keys()
        return tuple(
            dict.fromkeys(
                str(value).strip()
                for value in values
                if is_character_key(str(value).strip())
                and str(value).strip() in verified
            )
        )

    def save_selected_keys(self, values) -> tuple[str, ...]:
        verified = self._verified_keys()
        selected = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in values
                if is_character_key(str(value).strip())
                and str(value).strip() in verified
            )
        )
        self.settings.update_values(
            {KEY_GUIDE_PARTICIPANTS: list(selected)},
            default=default_profiles(),
        )
        return selected


__all__ = ["GuideParticipantService"]
