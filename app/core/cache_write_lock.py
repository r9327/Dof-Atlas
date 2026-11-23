"""Crash-safe cache writer lock using the shared Atlas file-lock backend.

The same OS byte lock protects rebuilt Success caches and persistent progress.
Keep the cache caller's public timeout and contextmanager interface; never
delete an active lock file and never duplicate Windows/POSIX locking code.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from app.core.progress_coordinator import InterProcessResourceLock, ProgressLockTimeoutError


@contextmanager
def exclusive_cache_write_lock(path: Path, *, timeout_seconds: float = 90.0):
    """Use the shared process/thread-safe lock without changing cache errors."""
    lock = InterProcessResourceLock(Path(path), timeout=timeout_seconds)
    try:
        lock.acquire()
    except ProgressLockTimeoutError as exc:
        raise TimeoutError(f"Cache write lock timed out: {lock.lock_path}") from exc
    try:
        yield
    finally:
        lock.release()
