from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_GUIDE_PARTICIPANTS,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.core.character_identity import character_key, is_character_key, iter_verified_character_bindings
from app.core.json_store import read_json_resilient
from app.core.file_stamp import file_revision
from app.core.profile_settings import default_profiles
from app.quest_catalog import QuestCharacter
from app.pages.quest_character_cache import cached_load_quest_characters as load_quest_characters
from app.services.profile_settings_service import ProfileSettingsService


def connected_travel_recipients(rows, selected_keys) -> tuple[str, ...]:
    """Project a unique, currently connected roster in explicit selection order."""
    selected = tuple(selected_keys)
    if len(set(selected)) != len(selected) or any(not is_character_key(key) for key in selected):
        raise ValueError("Identité de sélection ambiguë")
    connections = {}
    for row in rows:
        key = getattr(row, "key", None)
        if key not in selected:
            continue
        if key in connections:
            raise ValueError("Identité de connexion ambiguë")
        connections[key] = getattr(row, "connected", False) is True
    return tuple(key for key in selected if connections.get(key, False))


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
        self._verified_snapshot: tuple[tuple[int, int, int, int], frozenset[str]] | None = None

    def _verified_keys(self) -> frozenset[str]:
        """Reuse only stable, successful network identity reads; fail closed."""
        for _attempt in range(2):
            revision = file_revision(self.binding_path)
            if revision is None:
                self._verified_snapshot = None
                return frozenset()
            cached = self._verified_snapshot
            if cached is not None and cached[0] == revision:
                return cached[1]
            payload = read_json_resilient(self.binding_path, None)
            if file_revision(self.binding_path) != revision:
                continue
            if not isinstance(payload, dict):
                self._verified_snapshot = None
                return frozenset()
            keys = frozenset(
                character_key(ident)
                for ident, _row in iter_verified_character_bindings(payload, include_legacy_slots=True)
            )
            self._verified_snapshot = (revision, keys)
            return keys
        self._verified_snapshot = None
        return frozenset()

    def available_characters(self) -> tuple[QuestCharacter, ...]:
        for _attempt in range(2):
            revision = file_revision(self.binding_path)
            clients_revision = file_revision(self.client_index_path)
            verified = self._verified_keys()
            if not verified:
                return ()
            rows = load_quest_characters(
                self.profile_path, self.client_index_path,
                binding_path=self.binding_path, connected_only=False,
            )
            if (revision == file_revision(self.binding_path)
                    and clients_revision == file_revision(self.client_index_path)):
                return tuple(row for row in rows if row.key in verified)
        return ()

    def available_travel_characters(self) -> tuple[QuestCharacter, ...]:
        """Require live transport as well as the verified local window roster.

        Selection and manual progression retain offline characters; only
        automatic travel consumes this stricter read model.
        """
        from app.network.character_runtime_state import character_runtime_state

        rows = self.available_characters()
        connected = character_runtime_state().connected_character_keys()
        return tuple(replace(row, connected=row.connected and row.key in connected)
                     for row in rows)

    def _validated_selected_keys(self, values) -> tuple[str, ...]:
        """Single filter for selection read/write; keep offline verified IDs."""
        verified = self._verified_keys()
        selected = []
        seen = set()
        for value in values:
            key = str(value).strip()
            if key not in seen and is_character_key(key) and key in verified:
                seen.add(key)
                selected.append(key)
        return tuple(selected)

    def selected_keys(self) -> tuple[str, ...]:
        payload = self.settings.load_fields((KEY_GUIDE_PARTICIPANTS,), default_profiles())
        values = payload.get(KEY_GUIDE_PARTICIPANTS, [])
        if not isinstance(values, list):
            return ()
        return self._validated_selected_keys(values)

    def save_selected_keys(self, values) -> tuple[str, ...]:
        selected = self._validated_selected_keys(values)
        self.settings.update_values(
            {KEY_GUIDE_PARTICIPANTS: list(selected)},
            default=default_profiles(),
        )
        return selected


__all__ = ["GuideParticipantService", "connected_travel_recipients"]
