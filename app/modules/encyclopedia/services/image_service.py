from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImageReader, QPixmap


CacheKey = tuple[str, int, int, int, int]
DEFAULT_IMAGE_CACHE_BYTES = 8 * 1024 * 1024
DEFAULT_IMAGE_CACHE_ITEMS = 64


class ImageService:
    """Byte-bounded shared cache for decoded Encyclopedia thumbnails.

    Catalogue objects remain metadata-only. Cached pixmaps are already scaled to
    their visible size so Bestiary/Guide/Equipment cannot silently turn this into
    a full-resolution image warehouse as the application grows.
    """

    def __init__(
        self,
        *,
        max_bytes: int = DEFAULT_IMAGE_CACHE_BYTES,
        max_items: int = DEFAULT_IMAGE_CACHE_ITEMS,
    ) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self.max_items = max(0, int(max_items))
        self._lock = RLock()
        self._cache: OrderedDict[CacheKey, tuple[QPixmap, int]] = OrderedDict()
        self._cache_bytes = 0

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int]:
        try:
            stat = path.stat()
        except OSError:
            return (0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _cache_key(self, path: Path, size: QSize) -> CacheKey | None:
        path = Path(path)
        mtime_ns, file_size = self._stamp(path)
        if mtime_ns <= 0 or file_size <= 0:
            return None
        return (
            str(path),
            mtime_ns,
            file_size,
            int(size.width()),
            int(size.height()),
        )

    @staticmethod
    def _pixmap_bytes(pixmap: QPixmap) -> int:
        if pixmap.isNull():
            return 0
        return max(1, int(pixmap.width())) * max(1, int(pixmap.height())) * 4

    def get_scaled(self, path: Path, size: QSize) -> QPixmap:
        """Return only an existing cache hit; never decode from disk."""

        key = self._cache_key(Path(path), size)
        if key is None:
            return QPixmap()
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                return QPixmap()
            self._cache.move_to_end(key)
            return cached[0]

    def store_scaled(self, path: Path, size: QSize, pixmap: QPixmap) -> QPixmap:
        """Store a Qt-thread pixmap in the byte-bounded true-LRU cache."""

        if pixmap.isNull():
            return QPixmap()
        key = self._cache_key(Path(path), size)
        if key is None:
            return pixmap
        cost = self._pixmap_bytes(pixmap)
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                return existing[0]

            if cost <= 0 or self.max_bytes <= 0 or self.max_items <= 0 or cost > self.max_bytes:
                return pixmap

            self._cache[key] = (pixmap, cost)
            self._cache_bytes += cost
            while self._cache and (
                self._cache_bytes > self.max_bytes or len(self._cache) > self.max_items
            ):
                _old_key, (_old_pixmap, old_cost) = self._cache.popitem(last=False)
                self._cache_bytes -= old_cost
        return pixmap

    @staticmethod
    def _decode_scaled(path: Path, size: QSize) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        reader.setDecideFormatFromContent(True)
        original = reader.size()
        requested = QSize(size)
        if (
            original.isValid()
            and requested.isValid()
            and original.width() > 0
            and original.height() > 0
            and requested.width() > 0
            and requested.height() > 0
        ):
            target = QSize(original)
            target.scale(requested, Qt.KeepAspectRatio)
            if target.width() < original.width() or target.height() < original.height():
                reader.setScaledSize(target)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        pixmap = QPixmap.fromImage(image)
        if pixmap.width() > requested.width() or pixmap.height() > requested.height():
            pixmap = pixmap.scaled(requested, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return pixmap

    def load_scaled(self, path: Path, size: QSize) -> QPixmap:
        """Decode one visible image close to its requested raster size."""

        path = Path(path)
        cached = self.get_scaled(path, size)
        if not cached.isNull():
            return cached
        scaled = self._decode_scaled(path, size)
        if scaled.isNull():
            return QPixmap()
        return self.store_scaled(path, size, scaled)

    def info(self) -> dict[str, int]:
        with self._lock:
            return {
                "items": len(self._cache),
                "bytes": int(self._cache_bytes),
                "max_bytes": int(self.max_bytes),
                "max_items": int(self.max_items),
            }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_bytes = 0


ENCYCLOPEDIA_IMAGE_SERVICE = ImageService()


__all__ = [
    "DEFAULT_IMAGE_CACHE_BYTES",
    "DEFAULT_IMAGE_CACHE_ITEMS",
    "ENCYCLOPEDIA_IMAGE_SERVICE",
    "ImageService",
]
