from __future__ import annotations

import json
from logging import Logger
from typing import Any, Callable

from app.core.numbers import coerce_positive_int as _positive_int
from app.core.logger import get_runtime_logger
from app.network.character_runtime_decoder import (
    _CHARACTER_CHARACTERISTICS_TYPE_URL,
    _candidate_character_stats,
)
from app.network.character_resolver import CharacterResolution, CharacterSlotResolver
from app.network.character_runtime_state import CharacterRuntimeStateStore, character_runtime_state
from app.network.events import CharacterIdentifiedEvent, SessionClosedEvent
from app.quest_catalog import is_generic_dofus_client_name, normalize_text


_VERIFIED_SOURCE = "verified_network_identity"
def _trusted_client_label(row: dict[str, Any]) -> str:
    # Organizer's exported ``label`` is synthetic ("Personnage N") and must
    # never participate in identity recovery. ``character_name`` is the cleaned
    # window identity; ``name``/``nom`` cover older exported formats.
    for key in ("character_name", "name", "nom"):
        value = str(row.get(key) or "").strip()
        if value and not is_generic_dofus_client_name(value):
            return value
    return ""


class VerifiedKnownSessionRecovery:
    """Recover a live Npcap session from an identity Atlas verified earlier.

    Passive capture cannot replay kvi/kva packets emitted before Atlas started.
    Recovery therefore never invents a new identity: it only reuses an existing
    ``verified_network_identity`` binding when the current Npcap session PID is
    also present in the current client index. Organizer slots are merely a
    consistency check and are never used as a progression identity.
    """

    def __init__(
        self,
        resolver: CharacterSlotResolver,
        *,
        logger: Logger | None = None,
    ) -> None:
        self.resolver = resolver
        self.logger = logger or get_runtime_logger()

    def resolve(self, session_id: str) -> CharacterResolution | None:
        session = str(session_id or "").strip()
        pid = self.resolver._session_pid(session)
        if pid <= 0:
            return None

        client = self._current_client_for_pid(pid)
        if client is None:
            return None
        current_slot = _positive_int(client.get("slot") or client.get("index"))
        current_label = _trusted_client_label(client)

        verified = self._verified_bindings()
        if not verified:
            return None

        pid_matches = [
            row
            for row in verified
            if _positive_int(row[1].get("pid")) == pid
            and self._binding_consistent_with_client(row[1], current_label, current_slot)
        ]
        if len(pid_matches) == 1:
            return self._resolution(pid_matches[0], current_slot)
        if len(pid_matches) > 1:
            return None

        # PID may legitimately change after a Dofus restart. A current window
        # label can recover the same already-verified identity, but only when it
        # names exactly one verified character. No label => no fallback.
        label_key = normalize_text(current_label)
        if not label_key:
            return None
        name_matches = [
            row
            for row in verified
            if normalize_text(row[1].get("name")) == label_key
            and self._binding_slot_consistent(row[1], current_slot)
        ]
        return self._resolution(name_matches[0], current_slot) if len(name_matches) == 1 else None

    def _current_client_for_pid(self, pid: int) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.resolver.client_index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        clients = payload.get("clients", []) if isinstance(payload, dict) else []
        matches = []
        for row in clients if isinstance(clients, list) else ():
            if not isinstance(row, dict) or _positive_int(row.get("pid")) != pid:
                continue
            matches.append(row)
        return matches[0] if len(matches) == 1 else None

    def _verified_bindings(self) -> list[tuple[int, dict[str, Any]]]:
        try:
            payload = json.loads(self.resolver.binding_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        characters = payload.get("characters", {}) if isinstance(payload, dict) else {}
        if not isinstance(characters, dict):
            return []

        rows: list[tuple[int, dict[str, Any]]] = []
        for raw_id, row in characters.items():
            stable_id = _positive_int(raw_id)
            if (
                stable_id is None
                or not isinstance(row, dict)
                or str(row.get("source") or "") != _VERIFIED_SOURCE
                or not str(row.get("name") or "").strip()
            ):
                continue
            rows.append((stable_id, row))
        return rows

    @staticmethod
    def _binding_slot_consistent(binding: dict[str, Any], current_slot: int | None) -> bool:
        binding_slot = _positive_int(binding.get("organizer_slot"))
        return current_slot is None or binding_slot is None or binding_slot == current_slot

    @classmethod
    def _binding_consistent_with_client(
        cls,
        binding: dict[str, Any],
        current_label: str,
        current_slot: int | None,
    ) -> bool:
        if not cls._binding_slot_consistent(binding, current_slot):
            return False
        # A recycled PID with a generic Unity title is not evidence that the
        # previous character is still selected. Wait for a verified selection.
        return bool(current_label) and (
            normalize_text(binding.get("name")) == normalize_text(current_label)
        )

    def _resolution(
        self,
        row: tuple[int, dict[str, Any]],
        current_slot: int | None,
    ) -> CharacterResolution:
        stable_id, binding = row
        slot = current_slot or _positive_int(binding.get("organizer_slot")) or 0
        return CharacterResolution(
            character_key=self.resolver.character_key(stable_id),
            label=str(binding.get("name") or "").strip(),
            slot=slot,
        )


class KnownSessionProtocolMessageDecoder:
    """Seed the volatile character read model before later Npcap profile packets."""

    def __init__(
        self,
        delegate,
        recovery: VerifiedKnownSessionRecovery,
        *,
        active_profile_matches: Callable[[], bool],
        state: CharacterRuntimeStateStore | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.delegate = delegate
        self.recovery = recovery
        self.active_profile_matches = active_profile_matches
        self.state = state or character_runtime_state()
        self.logger = logger or get_runtime_logger()

    def decode(self, message):
        # A PID may own non-game connections. Require evidence of the
        # reviewed game profile before attaching an already-open character.
        if (
            message.type_url == _CHARACTER_CHARACTERISTICS_TYPE_URL
            and message.direction == "server_to_client"
            and self.state.snapshot_for_session(message.session_id) is None
            and self.active_profile_matches()
            and _candidate_character_stats(message.payload) is not None
        ):
            self._recover(message.session_id)
        return self.delegate.decode(message)

    def session_closed(self, session_id: str) -> None:
        hook = getattr(self.delegate, "session_closed", None)
        if callable(hook):
            hook(session_id)

    def reset(self) -> None:
        hook = getattr(self.delegate, "reset", None)
        if callable(hook):
            hook()

    def _recover(self, session_id: str) -> None:
        session = str(session_id or "").strip()
        if not session:
            return
        resolution = self.recovery.resolve(session)
        if resolution is None:
            return
        stable_id = _positive_int(str(resolution.character_key).removeprefix("character:"))
        if stable_id is None:
            return
        if self.state.identify(
            session_id=session,
            character_key=resolution.character_key,
            character_id=stable_id,
            name=resolution.label,
        ):
            self.logger.info(
                "Recovered verified character for already-open Npcap session: session=%s character=%s key=%s",
                session,
                resolution.label,
                resolution.character_key,
            )


class KnownSessionProgressBridge:
    """Route later progression through the existing bridge after safe recovery."""

    def __init__(
        self, delegate, recovery: VerifiedKnownSessionRecovery, *,
        state: CharacterRuntimeStateStore | None = None,
    ) -> None:
        self.delegate = delegate
        self.recovery = recovery
        self.state = state or character_runtime_state()

    def handle(self, event):
        if event.reliable and not isinstance(event, (CharacterIdentifiedEvent, SessionClosedEvent)):
            session = str(getattr(event, "session_id", "") or "").strip()
            if session and not self.delegate.session_character_key(session):
                resolution = self.recovery.resolve(session)
                if resolution is not None:
                    stable_id = _positive_int(
                        str(resolution.character_key).removeprefix("character:")
                    )
                    if stable_id is not None:
                        identified = self.delegate.handle(
                            CharacterIdentifiedEvent(
                                session_id=session,
                                event_id="known-session-recovery",
                                reliable=True,
                                character_name=resolution.label,
                                character_id=stable_id,
                            )
                        )
                        if identified.accepted and identified.character_key == resolution.character_key:
                            self.state.identify(
                                session_id=session, character_key=resolution.character_key,
                                character_id=stable_id, name=resolution.label,
                            )
        return self.delegate.handle(event)

    def reset_sessions(self) -> None:
        self.delegate.reset_sessions()

    def session_character_key(self, session_id: str) -> str:
        return self.delegate.session_character_key(session_id)


__all__ = [
    "KnownSessionProgressBridge",
    "KnownSessionProtocolMessageDecoder",
    "VerifiedKnownSessionRecovery",
]
