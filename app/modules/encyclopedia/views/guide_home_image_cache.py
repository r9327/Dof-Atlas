from __future__ import annotations

from pathlib import Path
from threading import RLock
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap


_LOCK = RLock()
_CACHE: dict[tuple[str, int, int, int, int], QPixmap] = {}
_ORDER: list[tuple[str, int, int, int, int]] = []
_MAX_ITEMS = 96


def _stamp(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _cache_key(path: Path, size: QSize) -> tuple[str, int, int, int, int] | None:
    path = Path(path)
    mtime_ns, file_size = _stamp(path)
    if mtime_ns <= 0 or file_size <= 0:
        return None
    return (
        str(path),
        mtime_ns,
        file_size,
        int(size.width()),
        int(size.height()),
    )


def get_cached_scaled_pixmap(path: Path, size: QSize) -> QPixmap:
    """Return only an existing Qt pixmap cache hit; never decode from disk."""

    key = _cache_key(Path(path), size)
    if key is None:
        return QPixmap()
    with _LOCK:
        cached = _CACHE.get(key)
        return cached if cached is not None else QPixmap()


def store_scaled_pixmap(path: Path, size: QSize, pixmap: QPixmap) -> QPixmap:
    """Store a pixmap produced on the Qt thread under the current file stamp."""

    if pixmap.isNull():
        return QPixmap()
    key = _cache_key(Path(path), size)
    if key is None:
        return pixmap
    with _LOCK:
        existing = _CACHE.get(key)
        if existing is not None:
            return existing
        _CACHE[key] = pixmap
        _ORDER.append(key)
        while len(_ORDER) > _MAX_ITEMS:
            oldest = _ORDER.pop(0)
            _CACHE.pop(oldest, None)
    return pixmap


def cached_scaled_pixmap(path: Path, size: QSize) -> QPixmap:
    """Backward-compatible synchronous path used by legacy/non-async callers."""

    path = Path(path)
    cached = get_cached_scaled_pixmap(path, size)
    if not cached.isNull():
        return cached
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return QPixmap()
    scaled = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return store_scaled_pixmap(path, size, scaled)


def clear_guide_home_image_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _ORDER.clear()


__all__ = [
    "cached_scaled_pixmap",
    "clear_guide_home_image_cache",
    "get_cached_scaled_pixmap",
    "store_scaled_pixmap",
]
