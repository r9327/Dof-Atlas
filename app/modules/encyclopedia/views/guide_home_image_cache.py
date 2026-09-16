from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap

from app.modules.encyclopedia.services.image_service import (
    DEFAULT_IMAGE_CACHE_BYTES,
    DEFAULT_IMAGE_CACHE_ITEMS,
    ENCYCLOPEDIA_IMAGE_SERVICE,
    ImageService,
)


def get_cached_scaled_pixmap(path: Path, size: QSize) -> QPixmap:
    """Compatibility wrapper for existing Guide async callers."""

    return ENCYCLOPEDIA_IMAGE_SERVICE.get_scaled(path, size)


def store_scaled_pixmap(path: Path, size: QSize, pixmap: QPixmap) -> QPixmap:
    """Compatibility wrapper for existing Guide async callers."""

    return ENCYCLOPEDIA_IMAGE_SERVICE.store_scaled(path, size, pixmap)


def cached_scaled_pixmap(path: Path, size: QSize) -> QPixmap:
    """Compatibility wrapper for visible-only synchronous callers."""

    return ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(path, size)


def guide_home_image_cache_info() -> dict[str, int]:
    """Backward-compatible diagnostics for the shared Encyclopedia image cache."""

    return ENCYCLOPEDIA_IMAGE_SERVICE.info()


def clear_guide_home_image_cache() -> None:
    """Backward-compatible cache reset used by tests and lifecycle cleanup."""

    ENCYCLOPEDIA_IMAGE_SERVICE.clear()


__all__ = [
    "DEFAULT_IMAGE_CACHE_BYTES",
    "DEFAULT_IMAGE_CACHE_ITEMS",
    "ENCYCLOPEDIA_IMAGE_SERVICE",
    "ImageService",
    "cached_scaled_pixmap",
    "clear_guide_home_image_cache",
    "get_cached_scaled_pixmap",
    "guide_home_image_cache_info",
    "store_scaled_pixmap",
]
