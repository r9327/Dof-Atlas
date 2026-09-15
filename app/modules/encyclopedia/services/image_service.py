from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap


DEFAULT_IMAGE_CACHE_BYTES = 32 * 1024 * 1024


class ImageService:
    """Small shared pixmap cache for Encyclopedia images.

    Catalogues keep paths/metadata only. Decoded pixmaps live here, are loaded
    only on explicit demand, and are evicted by approximate decoded bytes.
    """

    def __init__(self, max_bytes: int = DEFAULT_IMAGE_CACHE_BYTES) -> None:
        self.max_bytes = max(1, int(max_bytes))
        self._lock = RLock()
        self._cache: OrderedDict[tuple[str, int, int, int, int], tuple[QPixmap, int]] = OrderedDict()
        self._bytes = 0

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int]:
        try:
            stat = Path(path).stat()
        except OSError:
            return (0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_size))

    @classmethod
    def _key(cls, path: Path, size: QSize) -> tuple[str, int, int, int, int] | None:
        path = Path(path)
        mtime_ns, file_size = cls._stamp(path)
        if mtime_ns <= 0 or file_size <= 0:
            return None
        return (
            str(path),
            mtime_ns,
            file_size,
            max(0, int(size.width())),
            max(0, int(size.height())),
        )

    @staticmethod
    def estimated_bytes(pixmap: QPixmap) -> int:
        if pixmap.isNull():
            return 0
        # Atlas images are displayed as 32-bit Qt pixmaps. Keep the estimate
        # intentionally simple and stable instead of depending on backend handles.
        return max(1, int(pixmap.width())) * max(1, int(pixmap.height())) * 4

    def get(self, path: Path, size: QSize) -> QPixmap:
        key = self._key(Path(path), size)
        if key is None:
            return QPixmap()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return QPixmap()
            self._cache.move_to_end(key)
            return entry[0]

    def store(self, path: Path, size: QSize, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return QPixmap()
        key = self._key(Path(path), size)
        if key is None:
            return pixmap
        cost = self.estimated_bytes(pixmap)
        with self._lock:
            existing = self._cache.pop(key, None)
            if existing is not None:
                self._bytes -= existing[1]
            self._cache[key] = (pixmap, cost)
            self._bytes += cost
            while self._bytes > self.max_bytes and len(self._cache) > 1:
                _old_key, (_old_pixmap, old_cost) = self._cache.popitem(last=False)
                self._bytes -= old_cost
        return pixmap

    def load_scaled(self, path: Path, size: QSize) -> QPixmap:
        path = Path(path)
        cached = self.get(path, size)
        if not cached.isNull():
            return cached
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return QPixmap()
        scaled = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return self.store(path, size, scaled)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._bytes = 0

    def info(self) -> dict[str, int]:
        with self._lock:
            return {
                "items": len(self._cache),
                "bytes": self._bytes,
                "max_bytes": self.max_bytes,
            }


ENCYCLOPEDIA_IMAGE_SERVICE = ImageService()


__all__ = [
    "DEFAULT_IMAGE_CACHE_BYTES",
    "ENCYCLOPEDIA_IMAGE_SERVICE",
    "ImageService",
]
