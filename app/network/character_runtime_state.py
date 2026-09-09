from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock


_UNSET = object()
_MAX_RUNTIME_STAT_ABS_VALUE = 2_147_483_647


@dataclass(frozen=True, slots=True)
class CharacterRuntimeSnapshot:
    """Volatile, verified network facts for one stable Dofus character id."""

    character_key: str
    character_id: int
    name: str
    level: int | None = None
    achievement_points: int | None = None
    stats: tuple[tuple[str, int], ...] = ()
    connected_sessions: tuple[str, ...] = ()

    @property
    def connected(self) -> bool:
        return bool(self.connected_sessions)


class CharacterRuntimeStateStore:
    """Thread-safe read model shared by the network worker and character UI.

    The store is deliberately volatile: bindings/progression remain the existing
    persistent sources of truth. Optional profile facts are accepted only for a
    transport session that is currently routed to the same verified
    ``character:<dofus-id>`` identity, preventing stale packets from a previous
    character from leaking into the selected character.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[str, CharacterRuntimeSnapshot] = {}
        self._session_characters: dict[str, str] = {}
        self._profile_sessions: dict[str, str] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def snapshot(self, character_key: str) -> CharacterRuntimeSnapshot | None:
        key = str(character_key or "").strip()
        if not key:
            return None
        with self._lock:
            return self._snapshots.get(key)

    def snapshot_for_session(self, session_id: str) -> CharacterRuntimeSnapshot | None:
        """Return the immutable snapshot currently routed to one transport session."""

        session = str(session_id or "").strip()
        if not session:
            return None
        with self._lock:
            key = self._session_characters.get(session, "")
            return self._snapshots.get(key) if key else None

    def identify(
        self,
        *,
        session_id: str,
        character_key: str,
        character_id: int,
        name: str,
    ) -> bool:
        session = str(session_id or "").strip()
        key = str(character_key or "").strip()
        label = str(name or "").strip()
        try:
            stable_id = int(character_id)
        except (TypeError, ValueError, OverflowError):
            return False
        if not session or stable_id <= 0 or key != f"character:{stable_id}" or not label:
            return False

        with self._lock:
            previous_key = self._session_characters.get(session, "")
            changed = False
            if previous_key and previous_key != key:
                changed = self._detach_session_unlocked(session, previous_key) or changed

            previous = self._snapshots.get(key)
            sessions = set(previous.connected_sessions if previous is not None else ())
            sessions.add(session)
            updated = CharacterRuntimeSnapshot(
                character_key=key,
                character_id=stable_id,
                name=label,
                level=previous.level if previous is not None else None,
                achievement_points=(
                    previous.achievement_points if previous is not None else None
                ),
                stats=previous.stats if previous is not None else (),
                connected_sessions=tuple(sorted(sessions)),
            )
            if previous != updated or self._session_characters.get(session) != key:
                self._snapshots[key] = updated
                self._session_characters[session] = key
                self._profile_sessions[key] = session
                changed = True
            if changed:
                self._generation += 1
            return changed

    def update_verified_profile(
        self,
        session_id: str,
        *,
        level: object = _UNSET,
        achievement_points: object = _UNSET,
        stats: object = _UNSET,
    ) -> bool:
        """Apply already-verified profile facts to the session's current identity."""

        session = str(session_id or "").strip()
        if not session:
            return False
        with self._lock:
            key = self._session_characters.get(session, "")
            previous = self._snapshots.get(key) if key else None
            if previous is None or self._profile_sessions.get(key) != session:
                return False

            next_level = previous.level
            if level is not _UNSET:
                try:
                    parsed_level = int(level)
                except (TypeError, ValueError, OverflowError):
                    return False
                if not 1 <= parsed_level <= 200:
                    return False
                next_level = parsed_level

            next_points = previous.achievement_points
            if achievement_points is not _UNSET:
                try:
                    parsed_points = int(achievement_points)
                except (TypeError, ValueError, OverflowError):
                    return False
                if parsed_points < 0:
                    return False
                next_points = parsed_points

            next_stats = previous.stats
            if stats is not _UNSET:
                if not isinstance(stats, (tuple, list)):
                    return False
                parsed_stats: list[tuple[str, int]] = []
                seen_keys: set[str] = set()
                for row in stats:
                    if not isinstance(row, (tuple, list)) or len(row) != 2:
                        return False
                    stat_key = str(row[0] or "").strip()
                    if not stat_key or stat_key in seen_keys:
                        return False
                    try:
                        stat_value = int(row[1])
                    except (TypeError, ValueError, OverflowError):
                        return False
                    if abs(stat_value) > _MAX_RUNTIME_STAT_ABS_VALUE:
                        return False
                    seen_keys.add(stat_key)
                    parsed_stats.append((stat_key, stat_value))
                next_stats = tuple(parsed_stats)

            updated = replace(
                previous,
                level=next_level,
                achievement_points=next_points,
                stats=next_stats,
            )
            if updated == previous:
                return False
            self._snapshots[key] = updated
            self._generation += 1
            return True

    def close_session(self, session_id: str) -> bool:
        session = str(session_id or "").strip()
        if not session:
            return False
        with self._lock:
            key = self._session_characters.pop(session, "")
            if not key:
                return False
            changed = self._detach_session_unlocked(session, key)
            if changed:
                self._generation += 1
            return changed

    def clear_sessions(self) -> bool:
        with self._lock:
            if not self._session_characters:
                return False
            sessions = tuple(self._session_characters)
            changed = False
            for session in sessions:
                key = self._session_characters.pop(session, "")
                if key:
                    changed = self._detach_session_unlocked(session, key) or changed
            if changed:
                self._generation += 1
            return changed

    def remove_character(self, character_key: str) -> bool:
        key = str(character_key or "").strip()
        if not key:
            return False
        with self._lock:
            removed = self._snapshots.pop(key, None) is not None
            self._profile_sessions.pop(key, None)
            stale_sessions = [
                session
                for session, routed_key in self._session_characters.items()
                if routed_key == key
            ]
            for session in stale_sessions:
                self._session_characters.pop(session, None)
            changed = bool(removed or stale_sessions)
            if changed:
                self._generation += 1
            return changed

    def reset(self) -> None:
        with self._lock:
            if not self._snapshots and not self._session_characters:
                return
            self._snapshots.clear()
            self._session_characters.clear()
            self._profile_sessions.clear()
            self._generation += 1

    def _detach_session_unlocked(self, session: str, character_key: str) -> bool:
        previous = self._snapshots.get(character_key)
        if previous is None or session not in previous.connected_sessions:
            return False
        sessions = tuple(
            value for value in previous.connected_sessions if value != session
        )
        self._snapshots[character_key] = replace(
            previous,
            connected_sessions=sessions,
        )
        return True


_GLOBAL_CHARACTER_RUNTIME_STATE = CharacterRuntimeStateStore()


def character_runtime_state() -> CharacterRuntimeStateStore:
    return _GLOBAL_CHARACTER_RUNTIME_STATE


__all__ = [
    "CharacterRuntimeSnapshot",
    "CharacterRuntimeStateStore",
    "character_runtime_state",
]
