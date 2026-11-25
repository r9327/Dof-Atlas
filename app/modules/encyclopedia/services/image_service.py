from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap

from app.core.file_stamp import mtime_ctime_size_stamp_or_zero


CacheKey = tuple[str, int, int, int, int, int]
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
    def _stamp(path: Path) -> tuple[int, int, int]:
        return mtime_ctime_size_stamp_or_zero(path)

    def _cache_key(self, path: Path, size: QSize) -> CacheKey | None:
        path = Path(path)
        mtime_ns, ctime_ns, file_size = self._stamp(path)
        if mtime_ns <= 0 or file_size <= 0 or size.isEmpty():
            return None
        return (
            str(path),
            mtime_ns,
            ctime_ns,
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
        return self._get_key(key)

    def _get_key(self, key: CacheKey) -> QPixmap:
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                return QPixmap()
            self._cache.move_to_end(key)
            return QPixmap(cached[0])

    def store_scaled(
        self, path: Path, size: QSize, pixmap: QPixmap,
        *, source_stamp: tuple[int, int, int] | None = None,
    ) -> QPixmap:
        """Store a Qt-thread pixmap in the byte-bounded true-LRU cache."""

        if pixmap.isNull():
            return QPixmap()
        key = self._cache_key(Path(path), size)
        if source_stamp is not None and (key is None or key[1:4] != source_stamp):
            return QPixmap()
        if key is None:
            return pixmap
        return self._store_key(key, pixmap)

    def _store_key(self, key: CacheKey, pixmap: QPixmap) -> QPixmap:
        cost = self._pixmap_bytes(pixmap)
        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                return QPixmap(existing[0])

            # Old revisions of this path cannot be reused at any scale.
            # Purge them even when the replacement exceeds the cache budget.
            for obsolete in tuple(self._cache):
                if obsolete[0] == key[0] and obsolete[1:4] != key[1:4]:
                    _, old_cost = self._cache.pop(obsolete)
                    self._cache_bytes -= old_cost
            if cost <= 0 or self.max_bytes <= 0 or self.max_items <= 0 or cost > self.max_bytes:
                return pixmap
            self._cache[key] = (QPixmap(pixmap), cost)
            self._cache_bytes += cost
            while self._cache and (
                self._cache_bytes > self.max_bytes or len(self._cache) > self.max_items
            ):
                _old_key, (_old_pixmap, old_cost) = self._cache.popitem(last=False)
                self._cache_bytes -= old_cost
        return pixmap

    @staticmethod
    def _decode_scaled(path: Path, size: QSize) -> QPixmap:
        image = read_scaled_image(path, size)
        return QPixmap.fromImage(image) if not image.isNull() else QPixmap()

    def load_scaled(self, path: Path, size: QSize) -> QPixmap:
        """Decode one visible image close to its requested raster size."""

        path = Path(path)
        key = self._cache_key(path, size)
        if key is not None:
            cached = self._get_key(key)
            if not cached.isNull():
                return cached
        scaled = self._decode_scaled(path, size)
        if scaled.isNull():
            return QPixmap()
        # A source replaced during decoding must not seed the new revision
        # with pixels belonging to the old file.
        if key is None or self._cache_key(path, size) != key:
            return scaled
        return self._store_key(key, scaled)

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


def read_scaled_image(path: Path, size: QSize) -> QImage:
    """One size-aware decoder usable from workers without allocating QPixmap."""
    requested = QSize(size)
    if requested.isEmpty():
        return QImage()
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    original = reader.size()
    if original.isValid() and not original.isEmpty():
        target = QSize(original)
        target.scale(requested, Qt.KeepAspectRatio)
        if target.width() < original.width() or target.height() < original.height():
            reader.setScaledSize(target)
    image = reader.read()
    if not image.isNull() and (image.width() > requested.width() or image.height() > requested.height()):
        image = image.scaled(requested, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return image


ENCYCLOPEDIA_IMAGE_SERVICE = ImageService()


__all__ = [
    "DEFAULT_IMAGE_CACHE_BYTES",
    "DEFAULT_IMAGE_CACHE_ITEMS",
    "ENCYCLOPEDIA_IMAGE_SERVICE",
    "ImageService",
    "read_scaled_image",
]
