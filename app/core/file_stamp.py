"""Tiny Qt-free cache file signatures used by UI and Guide services."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def mtime_size_stamp_optional(path: Path | None, *, strict: bool = False) -> tuple[int, int] | None:
    """Return one stat result, preserving absence or a strict caller's error."""
    if path is None:
        return None
    try:
        stat = Path(path).stat()
    except OSError:
        if strict:
            raise
        return None
    return (int(stat.st_mtime_ns), int(stat.st_size))


def mtime_size_stamp(path: Path | None) -> tuple[int, int]:
    """Use the same zero sentinel for absent/unreadable cache sources."""
    return mtime_size_stamp_optional(path) or (0, 0)


def resolved_mtime_size_stamp(path: Path) -> tuple[str, int, int]:
    """Include the path identity for caches spanning several source files."""
    target = Path(path)
    return (str(target.resolve()), *mtime_size_stamp(target))


def mtime_ctime_size_stamp(path: Path) -> tuple[int, int, int] | None:
    """Preserve the stronger progress reload signature; absent file is None."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return (int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size))



def mtime_ctime_size_stamp_or_zero(path: Path) -> tuple[int, int, int]:
    """Return the canonical three-field UI cache stamp with missing-file zero."""
    return mtime_ctime_size_stamp(path) or (0, 0, 0)


def source_file_sizes(
    root: Path,
    files: Iterable[tuple[str, str]],
    *,
    allow_missing: bool = True,
) -> dict[str, int]:
    """Stable source-size manifest for portable Quest and Guide bundles.

    Strict reward builds preserve their original stat() exception; read-only
    Quest/Guide bundles use -1 so a missing source invalidates the manifest.
    """
    sizes: dict[str, int] = {}
    for _label, relative in files:
        path = Path(root) / relative
        try:
            size = path.stat().st_size
        except OSError:
            if not allow_missing:
                raise
            size = -1
        sizes[str(relative).replace("\\", "/")] = int(size)
    return sizes
