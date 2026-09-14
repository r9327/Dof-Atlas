from __future__ import annotations

import errno
import os
import threading
from pathlib import Path
from time import monotonic, sleep
from typing import BinaryIO


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
            self._depth = 1
        except BaseException:
            if handle is not None:
                handle.close()
            self._thread_lock.release()
            raise

    def release(self) -> None:
        if self._depth <= 0:
            raise RuntimeError("cannot release an un-acquired persistence lock")
        self._depth -= 1
        try:
            if self._depth == 0:
                handle = self._handle
                self._handle = None
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


__all__ = [
    "InterProcessResourceLock",
    "ProgressFileCoordinator",
    "ProgressLockTimeoutError",
    "coordinator_for",
]
