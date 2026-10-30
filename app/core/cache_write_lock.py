"""Lightweight, crash-safe interprocess lock for shared rebuildable caches.

Use the same OS lock for compact Success caches and name indexes; a thread-only
mutex cannot protect eight independent Atlas processes. Never delete lock files:
a late process could otherwise lock a different inode.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep


@contextmanager
def exclusive_cache_write_lock(path: Path, *, timeout_seconds: float = 90.0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    deadline = monotonic() + timeout_seconds
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(bytes([0]))
            lock_file.flush()
        while True:
            try:
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError) as exc:
                if monotonic() >= deadline:
                    raise TimeoutError(
                        f"Cache write lock timed out: {lock_path}"
                    ) from exc
                sleep(0.05)
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
