from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap


CacheKey = tuple[str, int, int, int, int]

_LOCK = RLock()
_CACHE: OrderedDict[CacheKey, tuple[QPixmap, int]] = OrderedDict()
_CACHE_BYTES = 0
# A decoded RGBA pixmap is roughly width * height * 4 bytes. Keep the Guide
# thumbnail cache deliberately modest: it is an optimisation, never a reason to
# retain an unbounded fraction of the image catalogue in RAM.
_MAX_CACHE_BYTES = 32 * 1024 * 1024
# Secondary guard for pathological collections of tiny pixmaps.
_MAX_ITEMS = 96


def _stamp(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _cache_key(path: Path, size: QSize) -> CacheKey | None:
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


def _pixmap_bytes(pixmap: QPixmap) -> int:
    if pixmap.isNull():
        return 0
    return max(1, int(pixmap.width())) * max(1, int(pixmap.height())) * 4


def get_cached_scaled_pixmap(path: Path, size: QSize) -> QPixmap:
    """Return only an existing cache hit; never decode from disk.

    Hits become most-recently-used so a frequently visible Guide card survives
    eviction while stale thumbnails are released first.
    """

    key = _cache_key(Path(path), size)
    if key is None:
        return QPixmap()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            return QPixmap()
        _CACHE.move_to_end(key)
        return cached[0]


def store_scaled_pixmap(path: Path, size: QSize, pixmap: QPixmap) -> QPixmap:
    """Store a Qt-thread pixmap in the bounded Guide thumbnail LRU cache."""

    global _CACHE_BYTES

    if pixmap.isNull():
        return QPixmap()
    key = _cache_key(Path(path), size)
    if key is None:
        return pixmap
    cost = _pixmap_bytes(pixmap)
    with _LOCK:
        existing = _CACHE.get(key)
        if existing is not None:
            _CACHE.move_to_end(key)
            return existing[0]

        # An individual image larger than the whole budget remains usable by the
        # caller but must not evict the complete cache just to keep itself.
        if cost <= 0 or _MAX_CACHE_BYTES <= 0 or cost > _MAX_CACHE_BYTES:
            return pixmap

        _CACHE[key] = (pixmap, cost)
        _CACHE_BYTES += cost
        while _CACHE and (
            _CACHE_BYTES > _MAX_CACHE_BYTES or len(_CACHE) > _MAX_ITEMS
        ):
            _old_key, (_old_pixmap, old_cost) = _CACHE.popitem(last=False)
            _CACHE_BYTES -= old_cost
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


def guide_home_image_cache_info() -> dict[str, int]:
    """Expose bounded-cache counters for diagnostics and performance tests."""

    with _LOCK:
        return {
            "items": len(_CACHE),
            "bytes": int(_CACHE_BYTES),
            "max_bytes": int(_MAX_CACHE_BYTES),
            "max_items": int(_MAX_ITEMS),
        }


def clear_guide_home_image_cache() -> None:
    global _CACHE_BYTES

    with _LOCK:
        _CACHE.clear()
        _CACHE_BYTES = 0


__all__ = [
    "cached_scaled_pixmap",
    "clear_guide_home_image_cache",
    "get_cached_scaled_pixmap",
    "guide_home_image_cache_info",
    "store_scaled_pixmap",
]
