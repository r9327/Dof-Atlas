from __future__ import annotations

from pathlib import Path

from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_GUIDE_PARTICIPANTS,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.core.character_identity import is_character_key
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

    def available_characters(self) -> tuple[QuestCharacter, ...]:
        return tuple(
            load_quest_characters(
                self.profile_path,
                self.client_index_path,
                binding_path=self.binding_path,
                connected_only=False,
            )
        )

    def selected_keys(self) -> tuple[str, ...]:
        payload = self.settings.load(default_profiles())
        values = payload.get(KEY_GUIDE_PARTICIPANTS, [])
        if not isinstance(values, list):
            return ()
        return tuple(
            dict.fromkeys(
                str(value).strip()
                for value in values
                if is_character_key(str(value).strip())
            )
        )

    def save_selected_keys(self, values) -> tuple[str, ...]:
        selected = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in values
                if is_character_key(str(value).strip())
            )
        )
        self.settings.update_values(
            {KEY_GUIDE_PARTICIPANTS: list(selected)},
            default=default_profiles(),
        )
        return selected


__all__ = ["GuideParticipantService"]
