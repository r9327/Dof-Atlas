from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Callable

from app.network.normalizer import DecodedClientMessage
from app.network.protobuf_fields import ProtobufDecodeError, parse_protobuf_fields, resolve_field_path
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder


_MAX_ROSTER_CHARACTERS = 64
_MAX_TRACKED_SESSIONS = 64


@dataclass(frozen=True, slots=True)
class CorrelatedCharacterIdentityRule:
    """Describe an exact-build roster -> selected-character correlation.

    Dofus 3.6.10.10 does not put the character name directly in the selection
    success message. The server first sends a roster containing id/name pairs,
    then a selection success containing the active character id. This rule lets
    Atlas join only those two messages from the same transport session.
    """

    roster_type_url: str
    selected_type_url: str
    roster_entry_field: int
    roster_character_id_path: tuple[int, ...]
    roster_character_name_path: tuple[int, ...]
    selected_character_id_path: tuple[int, ...]
    selected_character_name_path: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.roster_type_url or "").strip():
            raise ValueError("roster_type_url cannot be empty")
        if not str(self.selected_type_url or "").strip():
            raise ValueError("selected_type_url cannot be empty")
        if self.roster_type_url == self.selected_type_url:
            raise ValueError("roster and selected type URLs must differ")
        if int(self.roster_entry_field) <= 0:
            raise ValueError("roster_entry_field must be positive")
        for path in (
            self.roster_character_id_path,
            self.roster_character_name_path,
            self.selected_character_id_path,
        ):
            if not path or any(int(field_number) <= 0 for field_number in path):
                raise ValueError("correlated identity paths must contain positive field numbers")
        if self.selected_character_name_path and any(
            int(field_number) <= 0 for field_number in self.selected_character_name_path
        ):
            raise ValueError("selected character name path must contain positive field numbers")


class CorrelatedCharacterIdentityDecoder:
    """Add exact same-session character correlation around a mapped decoder.

    The delegate remains responsible for ordinary semantic messages. Roster
    data is volatile only: it is never persisted and is cleared on disconnect,
    source restart, malformed replacement roster, or explicit reset.
    """

    def __init__(
        self,
        delegate: ProtocolMessageDecoder,
        rule: CorrelatedCharacterIdentityRule,
        *,
        mapping_version: str,
        mapping_fingerprint: str,
        active_fingerprint_provider: Callable[[], str | None],
    ) -> None:
        version = str(mapping_version or "").strip()
        fingerprint = str(mapping_fingerprint or "").strip().casefold()
        if not version:
            raise ValueError("mapping_version cannot be empty")
        if not _is_sha256(fingerprint):
            raise ValueError("mapping_fingerprint must be a SHA-256 digest")
        if active_fingerprint_provider is None:
            raise ValueError("active_fingerprint_provider is required")
        self.delegate = delegate
        self.rule = rule
        self.mapping_version = version
        self.mapping_fingerprint = fingerprint
        self.active_fingerprint_provider = active_fingerprint_provider
        self._lock = threading.RLock()
        self._rosters: dict[str, dict[int, str]] = {}

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        delegated = self.delegate.decode(message)
        if delegated is not None:
            return delegated

        type_url = str(message.type_url or "")
        if type_url not in {self.rule.roster_type_url, self.rule.selected_type_url}:
            # Most Dofus messages have nothing to do with character identity.
            # Do not resolve processes/stat build files for unrelated traffic.
            return None
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return None
        if not self._build_matches():
            return None

        if type_url == self.rule.roster_type_url:
            self._observe_roster(message)
            return None

        character_id = self._selected_character_id(message.payload)
        if character_id is None:
            return None
        direct_character_name = self._selected_character_name(message.payload)
        with self._lock:
            roster_character_name = self._rosters.get(message.session_id, {}).get(character_id)
        if (
            direct_character_name
            and roster_character_name
            and direct_character_name != roster_character_name
        ):
            return None
        character_name = direct_character_name or roster_character_name
        if not character_name:
            return None

        digest = hashlib.sha256()
        digest.update(self.mapping_version.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.mapping_fingerprint.encode("ascii"))
        digest.update(b"\0character_identified\0")
        digest.update(type_url.encode("utf-8", errors="strict"))
        digest.update(b"\0")
        digest.update(message.payload)
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="character_identified",
            fields={"character_name": character_name, "character_id": character_id},
            event_id=f"proto:{digest.hexdigest()[:32]}",
            verified=True,
        )

    def session_closed(self, session_id: str) -> None:
        session = str(session_id or "")
        if not session:
            return
        with self._lock:
            self._rosters.pop(session, None)
        hook = getattr(self.delegate, "session_closed", None)
        if callable(hook):
            hook(session)

    def reset(self) -> None:
        with self._lock:
            self._rosters.clear()
        hook = getattr(self.delegate, "reset", None)
        if callable(hook):
            hook()

    def _observe_roster(self, message: CapturedProtocolMessage) -> None:
        session = str(message.session_id or "")
        if not session:
            return
        replacement: dict[int, str] | None = None
        try:
            fields = parse_protobuf_fields(message.payload)
            entries = fields.get(int(self.rule.roster_entry_field), ())
            if not entries or len(entries) > _MAX_ROSTER_CHARACTERS:
                replacement = None
            elif any(not isinstance(entry, bytes) for entry in entries):
                replacement = None
            else:
                parsed: dict[int, str] = {}
                for entry in entries:
                    character_id = resolve_field_path(
                        entry,
                        self.rule.roster_character_id_path,
                        expected_kind="positive_int",
                    )
                    character_name = resolve_field_path(
                        entry,
                        self.rule.roster_character_name_path,
                        expected_kind="string",
                    )
                    if not isinstance(character_id, int) or not character_name:
                        parsed = {}
                        break
                    previous = parsed.get(character_id)
                    if previous is not None and previous != character_name:
                        parsed = {}
                        break
                    parsed[character_id] = character_name
                replacement = parsed or None
        except ProtobufDecodeError:
            replacement = None

        with self._lock:
            # A malformed/new roster must never leave an older roster active for
            # the same connection: that could route a later selection wrongly.
            self._rosters.pop(session, None)
            if replacement is None:
                return
            if session not in self._rosters and len(self._rosters) >= _MAX_TRACKED_SESSIONS:
                self._rosters.clear()
            self._rosters[session] = replacement

    def _selected_character_id(self, payload: bytes) -> int | None:
        try:
            value = resolve_field_path(
                payload,
                self.rule.selected_character_id_path,
                expected_kind="positive_int",
            )
        except ProtobufDecodeError:
            return None
        return int(value) if isinstance(value, int) and value > 0 else None

    def _selected_character_name(self, payload: bytes) -> str:
        if not self.rule.selected_character_name_path:
            return ""
        try:
            value = resolve_field_path(
                payload,
                self.rule.selected_character_name_path,
                expected_kind="string",
            )
        except ProtobufDecodeError:
            return ""
        return str(value or "").strip()

    def _build_matches(self) -> bool:
        try:
            active = str(self.active_fingerprint_provider() or "").strip().casefold()
        except Exception:
            return False
        return active == self.mapping_fingerprint


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = [
    "CorrelatedCharacterIdentityDecoder",
    "CorrelatedCharacterIdentityRule",
]
