from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import threading

from app.constants import (
    CLIENT_INDEX_JSON,
    DATA_DIR,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
    QUEST_PROGRESS_FILE,
)
from app.core.character_identity import character_key as canonical_character_key
from app.quest_catalog import QuestCharacter, load_quest_characters, normalize_text


_BINDING_LOCK = threading.RLock()
_TCP_SESSION_RE = re.compile(r"^tcp:(\d+):\d+$")


@dataclass(frozen=True, slots=True)
class CharacterResolution:
    character_key: str
    label: str
    slot: int


def merge_verified_binding_classes(
    binding_path: Path,
    class_candidates: dict[str, set[str]],
    valid_class_keys: set[str],
) -> bool:
    """Persist only unambiguous class metadata on already verified identities.

    This never creates a character identity. It only enriches rows that were
    previously learned through the fail-closed network resolver, and it uses
    the same lock/atomic replace path as identity updates so class preservation
    cannot clobber a concurrent network binding refresh.
    """

    path = Path(binding_path)
    valid = {
        str(value or "").strip().casefold()
        for value in valid_class_keys
        if str(value or "").strip()
    }
    normalized_candidates: dict[str, set[str]] = {}
    for raw_name, raw_classes in class_candidates.items():
        name_key = normalize_text(raw_name)
        if not name_key:
            continue
        classes = {
            str(class_key or "").strip().casefold()
            for class_key in raw_classes
            if str(class_key or "").strip().casefold() in valid
        }
        if classes:
            normalized_candidates.setdefault(name_key, set()).update(classes)

    with _BINDING_LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        row_groups = [
            rows
            for key in ("characters", "legacy_slots", "slots")
            if isinstance((rows := payload.get(key)), dict)
        ]
        if not row_groups:
            return False

        verified_name_counts: dict[str, int] = {}
        for rows in row_groups:
            for row in rows.values():
                if not isinstance(row, dict) or str(row.get("source") or "") != "verified_network_identity":
                    continue
                name_key = normalize_text(row.get("name"))
                if name_key:
                    verified_name_counts[name_key] = verified_name_counts.get(name_key, 0) + 1

        changed = False
        for rows in row_groups:
            for raw_key, row in list(rows.items()):
                if not isinstance(row, dict) or str(row.get("source") or "") != "verified_network_identity":
                    continue
                name_key = normalize_text(row.get("name"))
                if not name_key or verified_name_counts.get(name_key) != 1:
                    continue

                candidates = set(normalized_candidates.get(name_key, set()))
                existing_raw = str(row.get("class_key") or "").strip().casefold()
                if existing_raw in valid:
                    candidates.add(existing_raw)

                if len(candidates) == 1:
                    resolved = next(iter(candidates))
                    if existing_raw == resolved and row.get("class_key") == resolved:
                        continue
                    updated = dict(row)
                    updated["class_key"] = resolved
                    rows[str(raw_key)] = updated
                    changed = True
                elif row.get("class_key") and (existing_raw not in valid or len(candidates) > 1):
                    updated = dict(row)
                    updated.pop("class_key", None)
                    rows[str(raw_key)] = updated
                    changed = True

        if not changed:
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return True


class CharacterSlotResolver:
    """Resolve a verified DOFUS identity to an ID-backed Atlas profile.

    Organizer positions are transient presentation metadata. They must never be
    used as progression identities: a different character can occupy the same
    position after a reconnect or a reorder. New network progression is stored
    only under ``character:<dofus-id>`` keys. Historical ``slot:N`` data is
    migrated only when a previously verified binding proves which character it
    belongs to; otherwise it stays quarantined and cannot be inherited.
    """

    def __init__(
        self,
        profile_path: Path = PROFILE_FILE,
        client_index_path: Path = CLIENT_INDEX_JSON,
        binding_path: Path | None = None,
        slot_count: int = 8,
        progress_paths: tuple[Path, ...] | None = None,
    ) -> None:
        self.profile_path = Path(profile_path)
        self.client_index_path = Path(client_index_path)
        if binding_path is None:
            if self.profile_path == PROFILE_FILE and self.client_index_path == CLIENT_INDEX_JSON:
                binding_path = NETWORK_CHARACTER_BINDINGS_FILE
            else:
                binding_path = self.profile_path.parent / "network_character_bindings.json"
        self.binding_path = Path(binding_path)
        self.slot_count = max(1, int(slot_count))
        self.progress_paths = tuple(progress_paths) if progress_paths is not None else (
            QUEST_PROGRESS_FILE,
            DATA_DIR / "encyclopedia" / "progress" / "achievement_progress.json",
            DATA_DIR / "encyclopedia" / "progress" / "guide_progress.json",
        )

    def resolve(self, character_name: str) -> CharacterResolution | None:
        needle = normalize_text(character_name)
        if not needle:
            return None

        characters = load_quest_characters(
            self.profile_path,
            self.client_index_path,
            self.slot_count,
            binding_path=self.binding_path,
        )
        matches = [
            character
            for character in characters
            if self._is_named_match(character, needle)
        ]
        if len(matches) != 1:
            return None
        return self._resolution(matches[0])

    def resolve_for_session(
        self,
        character_name: str,
        session_id: str,
        character_id: int | None = None,
    ) -> CharacterResolution | None:
        """Resolve a verified network identity, falling back to its client PID.

        Unity release windows no longer expose the character name. The passive
        capture session does expose the owning PID (``tcp:<pid>:<counter>``), and
        the Organizer index records the PID and stable Atlas slot. We only learn
        a name when that PID matches exactly one indexed client.
        """

        pid = self._session_pid(session_id)
        label = str(character_name or "").strip()
        stable_id = self._positive_int(character_id)
        if not label:
            return None

        if stable_id is None:
            direct = self.resolve(character_name)
            if direct is not None:
                return direct
            # A name/PID/Organizer position is not a stable progression
            # identity. Wait for the correlated numeric character id.
            return None

        # A concrete Dofus character id is the only progression boundary.
        with _BINDING_LOCK:
            payload = self._read_binding_payload_unlocked()
            characters = payload["characters"]
            character_key = self.character_key(stable_id)
            row = characters.get(str(stable_id))
            organizer_slot = self._slot_for_pid(pid) if pid > 0 else None

            legacy_slot = None
            if isinstance(row, dict):
                legacy_slot = self._positive_int(row.get("legacy_slot"))
                if organizer_slot is None:
                    organizer_slot = self._positive_int(row.get("organizer_slot"))
            else:
                legacy_slot = self._legacy_slot_for_identity_unlocked(
                    payload["legacy_slots"],
                    label,
                    stable_id,
                )
                if organizer_slot is None:
                    organizer_slot = legacy_slot

            self._remember_identity_unlocked(
                payload,
                stable_id,
                label,
                pid,
                organizer_slot,
                legacy_slot,
            )
            if legacy_slot is not None:
                self._migrate_legacy_progress_unlocked(legacy_slot, character_key)
                payload["legacy_slots"].pop(str(legacy_slot), None)
                saved = payload["characters"].get(str(stable_id))
                if isinstance(saved, dict):
                    saved.pop("legacy_slot", None)
                self._write_binding_payload_unlocked(payload)
            return CharacterResolution(character_key, label, organizer_slot or 0)

    @staticmethod
    def character_key(character_id: int) -> str:
        return canonical_character_key(character_id)

    @staticmethod
    def _session_pid(session_id: str) -> int:
        match = _TCP_SESSION_RE.fullmatch(str(session_id or "").strip())
        return int(match.group(1)) if match is not None else 0

    def _slot_for_pid(self, pid: int) -> int | None:
        try:
            payload = json.loads(self.client_index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        clients = payload.get("clients", []) if isinstance(payload, dict) else []
        matches: list[int] = []
        for client in clients if isinstance(clients, list) else []:
            if not isinstance(client, dict):
                continue
            try:
                client_pid = int(client.get("pid") or 0)
                slot = int(client.get("slot") or client.get("index") or 0)
            except (TypeError, ValueError):
                continue
            if client_pid == pid and 1 <= slot <= self.slot_count:
                matches.append(slot)
        unique = tuple(dict.fromkeys(matches))
        return unique[0] if len(unique) == 1 else None

    def _read_binding_payload_unlocked(self) -> dict:
        try:
            payload = json.loads(self.binding_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        characters = payload.get("characters")
        if not isinstance(characters, dict):
            characters = {}
        legacy_slots = payload.get("legacy_slots")
        if not isinstance(legacy_slots, dict):
            legacy_slots = {}

        # Read and normalize the previous slot-based schema. Rows with a proven
        # numeric id become identity bindings; rows without one remain explicit
        # migration hints and never become active progression profiles.
        old_slots = payload.get("slots")
        for raw_slot, row in old_slots.items() if isinstance(old_slots, dict) else ():
            if not str(raw_slot).isdigit() or not isinstance(row, dict):
                continue
            stable_id = self._positive_int(row.get("character_id"))
            if stable_id is None:
                legacy_slots.setdefault(str(raw_slot), dict(row))
                continue
            migrated = dict(row)
            migrated.pop("character_id", None)
            migrated.setdefault("legacy_slot", int(raw_slot))
            migrated.setdefault("organizer_slot", int(raw_slot))
            characters.setdefault(str(stable_id), migrated)

        payload.pop("slots", None)
        payload["characters"] = characters
        payload["legacy_slots"] = legacy_slots
        return payload

    def _remember_identity_unlocked(
        self,
        payload: dict,
        character_id: int,
        label: str,
        pid: int,
        organizer_slot: int | None,
        legacy_slot: int | None,
    ) -> None:
        characters = payload["characters"]
        identity_key = str(character_id)
        previous = characters.get(identity_key)
        class_key = ""
        if (
            isinstance(previous, dict)
            and str(previous.get("source") or "") == "verified_network_identity"
            and normalize_text(previous.get("name")) == normalize_text(label)
        ):
            class_key = str(previous.get("class_key") or "").strip().casefold()

        # A live Windows PID identifies one client process at this instant, not
        # a persistent character. When a verified network identity is observed
        # on that process, older characters that previously used the same PID
        # must stop claiming it. Otherwise a character switch leaves several
        # identities looking "connected" and generic Unity window titles become
        # ambiguous even though the current character id is verified.
        if pid > 0:
            for other_key, other_row in list(characters.items()):
                if str(other_key) == identity_key or not isinstance(other_row, dict):
                    continue
                if self._positive_int(other_row.get("pid")) != pid:
                    continue
                detached = dict(other_row)
                detached.pop("pid", None)
                characters[str(other_key)] = detached

        updated = {
            "name": label,
            "pid": int(pid),
            "source": "verified_network_identity",
        }
        if organizer_slot is not None:
            updated["organizer_slot"] = int(organizer_slot)
        if legacy_slot is not None:
            updated["legacy_slot"] = int(legacy_slot)
        if class_key:
            updated["class_key"] = class_key
        characters[identity_key] = updated
        self._write_binding_payload_unlocked(payload)

    def _write_binding_payload_unlocked(self, payload: dict) -> None:
        self.binding_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.binding_path.with_suffix(self.binding_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.binding_path)

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    def _legacy_slot_for_identity_unlocked(
        self,
        legacy_slots: dict,
        label: str,
        character_id: int,
    ) -> int | None:
        needle = normalize_text(label)
        matches = [
            int(raw_slot)
            for raw_slot, row in legacy_slots.items()
            if str(raw_slot).isdigit()
            and isinstance(row, dict)
            and normalize_text(row.get("name")) == needle
            and self._positive_int(row.get("character_id")) in (None, character_id)
        ]
        return matches[0] if len(matches) == 1 else None

    def _migrate_legacy_progress_unlocked(self, slot: int, character_key: str) -> None:
        legacy_key = f"slot:{int(slot)}"
        for path in self.progress_paths:
            progress_path = Path(path)
            # Publish the migration through the same path-scoped coordinator as
            # the live services. Their cached snapshots then refresh before a
            # following network sync can write anything.
            from app.modules.encyclopedia.services.progress_coordinator import coordinator_for

            coordinator = coordinator_for(progress_path)
            with coordinator.lock:
                try:
                    payload = json.loads(progress_path.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError, TypeError):
                    continue
                characters = payload.get("characters", {}) if isinstance(payload, dict) else {}
                legacy = payload.get("legacy_characters", {}) if isinstance(payload, dict) else {}
                if not isinstance(characters, dict):
                    continue
                source = characters.pop(legacy_key, None)
                if source is None and isinstance(legacy, dict):
                    source = legacy.pop(legacy_key, None)
                if source is None:
                    continue
                existing = characters.get(character_key)
                characters[character_key] = self._merge_progress(existing, source)
                payload["characters"] = characters
                if isinstance(legacy, dict):
                    payload["legacy_characters"] = legacy
                temporary = progress_path.with_suffix(progress_path.suffix + ".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(progress_path)
                coordinator.mark_changed()

    @classmethod
    def _merge_progress(cls, current: object, incoming: object) -> object:
        if isinstance(current, dict) and isinstance(incoming, dict):
            merged = dict(current)
            for key, value in incoming.items():
                merged[key] = cls._merge_progress(merged.get(key), value)
            return merged
        if isinstance(current, list) and isinstance(incoming, list):
            return list(dict.fromkeys([*current, *incoming]))
        if isinstance(current, bool) and isinstance(incoming, bool):
            return current or incoming
        return incoming if current is None else current

    @staticmethod
    def _is_named_match(character: QuestCharacter, needle: str) -> bool:
        label = str(character.label or "").strip()
        if not label or normalize_text(label) != needle:
            return False
        # Default empty slots are UI placeholders, never network identities.
        return normalize_text(label) != f"slot_{int(character.slot)}"

    @staticmethod
    def _resolution(character: QuestCharacter) -> CharacterResolution:
        return CharacterResolution(
            character_key=str(character.key),
            label=str(character.label),
            slot=int(character.slot),
        )


__all__ = [
    "CharacterResolution",
    "CharacterSlotResolver",
    "merge_verified_binding_classes",
]
