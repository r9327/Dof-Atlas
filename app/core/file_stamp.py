"""Tiny Qt-free cache file signatures used by UI and Guide services."""
from __future__ import annotations

from pathlib import Path


def mtime_size_stamp(path: Path | None) -> tuple[int, int]:
    """Use the same zero sentinel for absent/unreadable cache sources."""
    if path is None:
        return (0, 0)
    try:
        stat = Path(path).stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_mtime_ns), int(stat.st_size))


def resolved_mtime_size_stamp(path: Path) -> tuple[str, int, int]:
    """Include the path identity for caches spanning several source files."""
    target = Path(path)
    return (str(target.resolve()), *mtime_size_stamp(target))
