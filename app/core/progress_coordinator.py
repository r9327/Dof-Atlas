from __future__ import annotations

import errno
import os
import threading
from pathlib import Path
from time import monotonic, sleep
from typing import Any, BinaryIO

from app.core.character_identity import require_character_key
from app.core.file_stamp import mtime_ctime_size_stamp


DEFAULT_LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05


class ProgressLockTimeoutError(TimeoutError):
    """Raised when another process keeps a persistence resource locked."""


class InterProcessResourceLock:
    """Small re-entrant lock backed by an OS lock file.

    The thread lock preserves the previous in-process contract. The kernel lock
    serializes independent Atlas processes and is released automatically if a
    process exits or crashes. The lock file intentionally remains: unlinking it
    could let two processes lock different inodes for one resource.
    """

    def __init__(self, resource_path: Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS) -> None:
        self.resource_path = Path(resource_path)
        self.lock_path = self.resource_path.with_suffix(self.resource_path.suffix + ".lock")
        self.timeout = float(timeout)
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._owner_thread_id: int | None = None
        self._handle: BinaryIO | None = None

    def __enter__(self) -> InterProcessResourceLock:
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.release()

    def acquire(self) -> None:
        deadline = monotonic() + self.timeout
        if not self._thread_lock.acquire(timeout=max(0.0, self.timeout)):
            raise self._timeout_error()
        if self._depth:
            self._depth += 1
            return

        handle: BinaryIO | None = None
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.lock_path.open("a+b")
            self._ensure_lock_byte(handle)
            while True:
                try:
                    self._try_os_lock(handle)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if monotonic() >= deadline:
                        raise self._timeout_error() from exc
                    sleep(min(LOCK_RETRY_SECONDS, max(0.0, deadline - monotonic())))
            self._handle = handle
            self._owner_thread_id = threading.get_ident()
            self._depth = 1
        except BaseException:
            if handle is not None:
                handle.close()
            self._thread_lock.release()
            raise

    def release(self) -> None:
        if self._depth <= 0:
            raise RuntimeError("cannot release an un-acquired persistence lock")
        if self._owner_thread_id != threading.get_ident():
            raise RuntimeError("cannot release a persistence lock owned by another thread")
        self._depth -= 1
        try:
            if self._depth == 0:
                handle = self._handle
                self._handle = None
                self._owner_thread_id = None
                if handle is None:
                    raise RuntimeError("persistence lock handle is missing")
                try:
                    self._os_unlock(handle)
                finally:
                    handle.close()
        finally:
            self._thread_lock.release()

    def _timeout_error(self) -> ProgressLockTimeoutError:
        return ProgressLockTimeoutError(
            f"Persistence resource remained locked for {self.timeout:.2f}s: {self.resource_path}"
        )

    @staticmethod
    def _ensure_lock_byte(handle: BinaryIO) -> None:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

    @staticmethod
    def _try_os_lock(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _os_unlock(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ProgressFileCoordinator:
    """Cross-process transaction lock plus process-local change generation."""

    def __init__(self, resource_path: Path) -> None:
        self.lock = InterProcessResourceLock(resource_path)
        self._generation_lock = threading.RLock()
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._generation_lock:
            return self._generation

    def mark_changed(self) -> int:
        with self._generation_lock:
            self._generation += 1
            return self._generation


_REGISTRY_LOCK = threading.RLock()
_COORDINATORS: dict[str, ProgressFileCoordinator] = {}


def _path_key(path: Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve())
    except OSError:
        return str(target.absolute())


def coordinator_for(path: Path) -> ProgressFileCoordinator:
    target = Path(path)
    key = _path_key(target)
    with _REGISTRY_LOCK:
        coordinator = _COORDINATORS.get(key)
        if coordinator is None:
            coordinator = ProgressFileCoordinator(target)
            _COORDINATORS[key] = coordinator
        return coordinator


def empty_progress_payload() -> dict[str, Any]:
    """Return a fresh, versioned Quests/Guides/Achievements progress root."""
    return {"version": 1, "characters": {}}


def complete_progress_root(payload: dict[str, Any]) -> dict[str, Any]:
    """Restore absent legacy defaults in-place after domain validation.

    Keep existing version, identity and all domain-specific keys untouched.
    """
    payload.setdefault("version", 1)
    payload.setdefault("characters", {})
    return payload


def progress_characters_for_validation(payload: Any) -> tuple[dict[str, Any], str | None]:
    """Validate the shared progress envelope once; callers validate domain fields.

    Preserve the precise legacy error messages for Quest, Guide and Achievement
    readers. No identities, quantities or completion state are inferred.
    """
    if not isinstance(payload, dict):
        return {}, "la racine doit être un objet"
    if payload.get("version", 1) != 1:
        return {}, f"version inconnue: {payload.get('version')!r}"
    characters = payload.get("characters", {})
    if not isinstance(characters, dict):
        return {}, "characters doit être un objet"
    for character_key, character in characters.items():
        if not isinstance(character, dict):
            return {}, f"characters[{character_key!r}] doit être un objet"
    return characters, None


def progress_mapping_values_error(
    field: str, rows: dict[str, Any], *, value_type: type,
) -> str | None:
    """One nested progress-map validator, preserving domain field diagnostics."""
    expected = "une liste" if value_type is list else "un objet"
    for key, value in rows.items():
        if not isinstance(value, value_type):
            return f"{field}[{key!r}] doit être {expected}"
    return None


def read_progress_mapping(parent: dict[str, Any], field: str) -> dict[str, Any]:
    """Read a nested progress map without repairing or creating persistent state."""
    value = parent.get(field, {})
    return value if isinstance(value, dict) else {}


def mutable_progress_mapping(parent: dict[str, Any], field: str) -> dict[str, Any]:
    """Create or repair a nested map only on an explicit mutation path."""
    value = parent.get(field)
    if not isinstance(value, dict):
        value = {}
        parent[field] = value
    return value


def update_progress_flag(rows: dict[str, Any], key: str, completed: bool) -> bool:
    """Apply one boolean flag; preserve the legacy exact-True/no-op contract."""
    if completed:
        if rows.get(key) is True:
            return False
        rows[key] = True
    else:
        if key not in rows:
            return False
        rows.pop(key)
    return True


def read_progress_character(
    payload: dict[str, Any], character_key: object,
) -> dict[str, Any]:
    """Return a safe read-only character view without mutating progress."""
    characters = payload.get("characters", {})
    if not isinstance(characters, dict):
        return {}
    key = str(character_key or "").strip()
    if not key:
        return {}
    value = characters.get(key, {})
    return value if isinstance(value, dict) else {}


def mutable_progress_character(
    payload: dict[str, Any], character_key: str, *,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get or repair a character row while retaining domain-specific defaults."""
    characters = payload.setdefault("characters", {})
    if not isinstance(characters, dict):
        characters = {}
        payload["characters"] = characters
    key = require_character_key(character_key)
    row = characters.setdefault(key, dict(defaults or {}))
    if not isinstance(row, dict):
        row = dict(defaults or {})
        characters[key] = row
    return row


def validate_progress_character_keys(progress: dict[str, Any]) -> None:
    """Shared write boundary; reject invalid character keys before persistence."""
    characters = progress.get("characters", {})
    if not isinstance(characters, dict):
        raise ValueError("progress characters must be a mapping")
    for character_key in characters:
        require_character_key(character_key)


class CoordinatedProgressReader:
    """Shared lazy-refresh implementation for Quest, Guide and Achievement.

    Concrete services retain their own domain loader and cache invalidation.
    A hot read checks only the coordinator generation; explicit reload checks
    the disk signature as well, so external changes remain observable.
    """

    def _coordinated_load(self) -> dict[str, Any]:
        raise NotImplementedError

    def _coordinated_invalidate(self) -> None:
        raise NotImplementedError

    def _record_snapshot_identity_locked(self) -> None:
        """Record the generation and disk stamp of an already loaded snapshot."""
        self._seen_generation = self._coordinator.generation
        self._disk_signature = self._current_disk_signature()

    def _current_disk_signature(self) -> tuple[int, int, int] | None:
        return mtime_ctime_size_stamp(self.path)

    def _replace_snapshot_locked(self, generation: int) -> None:
        self.progress = self._coordinated_load()
        self._seen_generation = generation
        self._disk_signature = self._current_disk_signature()
        self._coordinated_invalidate()

    def _require_current_snapshot_locked(self, domain: str) -> None:
        """Reject a stale compatibility save before it can overwrite a peer."""
        if (
            self._seen_generation != self._coordinator.generation
            or self._disk_signature != self._current_disk_signature()
        ):
            self._replace_snapshot_locked(self._coordinator.generation)
            raise RuntimeError(
                f"{domain} progress snapshot is stale; reload and apply the mutation again."
            )

    def _accept_snapshot_locked(self, *, changed: bool) -> None:
        """Publish a durable write or accept a no-op reload, then clear domain caches."""
        self._seen_generation = (
            self._coordinator.mark_changed() if changed else self._coordinator.generation
        )
        self._disk_signature = self._current_disk_signature()
        self._coordinated_invalidate()

    def _validate_write_snapshot(self) -> None:
        validate_progress_character_keys(self.progress)

    def _persist_progress_snapshot_locked(self, writer) -> None:
        """A rejected write must never leave an uncommitted snapshot readable.

        The next read reloads under the existing coordinator. Never publish a
        generation for a failed write, including validation or disk errors.
        """
        try:
            self._validate_write_snapshot()
            writer()
        except Exception:
            self._seen_generation = -1
            self._coordinated_invalidate()
            raise

    def _ensure_fresh(self) -> None:
        if self._seen_generation == self._coordinator.generation:
            return
        with self._coordinator.lock:
            if self._seen_generation != self._coordinator.generation:
                self._replace_snapshot_locked(self._coordinator.generation)

    def _refresh_if_changed_locked(self) -> bool:
        generation = self._coordinator.generation
        disk_signature = self._current_disk_signature()
        if generation == self._seen_generation and disk_signature == self._disk_signature:
            return False
        self._replace_snapshot_locked(generation)
        return True

    def refresh_if_changed(self) -> bool:
        with self._coordinator.lock:
            return self._refresh_if_changed_locked()

    def reload(self) -> dict[str, Any]:
        with self._coordinator.lock:
            self._refresh_if_changed_locked()
            return self.progress


__all__ = [
    "CoordinatedProgressReader",
    "InterProcessResourceLock",
    "ProgressFileCoordinator",
    "ProgressLockTimeoutError",
    "coordinator_for",
    "empty_progress_payload",
    "complete_progress_root",
    "progress_characters_for_validation",
    "validate_progress_character_keys",
]
