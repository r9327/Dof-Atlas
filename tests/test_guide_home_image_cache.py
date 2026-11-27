from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE


def test_scaled_guide_pixmap_is_reused_without_second_decode() -> None:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "guide.png"
        source = QPixmap(64, 64)
        source.fill(QColor("#ffffff"))
        assert source.save(str(path), "PNG")

        ENCYCLOPEDIA_IMAGE_SERVICE.clear()
        first = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(path, QSize(32, 32))
        assert not first.isNull()

        with patch.object(
            ENCYCLOPEDIA_IMAGE_SERVICE,
            "_decode_scaled",
            side_effect=AssertionError("cached guide image decoded again"),
        ):
            second = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(path, QSize(32, 32))

        assert not second.isNull()
        assert second.cacheKey() == first.cacheKey()
        ENCYCLOPEDIA_IMAGE_SERVICE.clear()
        app.processEvents()


def test_different_requested_size_uses_distinct_scaled_cache_entry() -> None:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "guide.png"
        source = QPixmap(80, 40)
        source.fill(QColor("#ffffff"))
        assert source.save(str(path), "PNG")

        ENCYCLOPEDIA_IMAGE_SERVICE.clear()
        small = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(path, QSize(20, 20))
        large = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(path, QSize(60, 60))

        assert small.width() <= 20 and small.height() <= 20
        assert large.width() <= 60 and large.height() <= 60
        assert large.width() > small.width()
        ENCYCLOPEDIA_IMAGE_SERVICE.clear()
        app.processEvents()
