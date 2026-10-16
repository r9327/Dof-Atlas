from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage

from app.modules.encyclopedia.services.image_service import (
    DEFAULT_IMAGE_CACHE_BYTES,
    DEFAULT_IMAGE_CACHE_ITEMS,
)
from app.modules.encyclopedia.views.guide_image_runtime_policy import (
    SOLUTION_DECODE_MAX_SIZE,
    decode_scaled_image,
)


def test_guide_decode_never_keeps_full_source_raster(tmp_path: Path) -> None:
    source = QImage(2048, 1024, QImage.Format_ARGB32)
    source.fill(0xFFFFFFFF)
    path = tmp_path / "large.png"
    assert source.save(str(path), "PNG")

    decoded = decode_scaled_image(path, QSize(230, 86), kind="guide")

    assert not decoded.isNull()
    assert decoded.width() <= 230
    assert decoded.height() <= 86
    assert decoded.width() < source.width()
    assert decoded.height() < source.height()


def test_solution_decode_budget_is_display_bounded() -> None:
    assert SOLUTION_DECODE_MAX_SIZE.width() <= 1180
    assert SOLUTION_DECODE_MAX_SIZE.height() <= 860


def test_encyclopedia_pixmap_cache_has_small_explicit_budget() -> None:
    assert DEFAULT_IMAGE_CACHE_BYTES == 8 * 1024 * 1024
    assert DEFAULT_IMAGE_CACHE_ITEMS == 64
