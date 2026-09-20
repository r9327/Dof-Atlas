from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.views import guide_home_image_cache as image_cache


class GuideHomeImageCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        service = image_cache.ENCYCLOPEDIA_IMAGE_SERVICE
        self._old_max_bytes = service.max_bytes
        self._old_max_items = service.max_items
        service.clear()

    def tearDown(self) -> None:
        service = image_cache.ENCYCLOPEDIA_IMAGE_SERVICE
        service.max_bytes = self._old_max_bytes
        service.max_items = self._old_max_items
        service.clear()

    @staticmethod
    def _pixmap(size: int = 10) -> QPixmap:
        return QPixmap(size, size)

    def test_cache_is_byte_bounded_and_true_lru(self) -> None:
        service = image_cache.ENCYCLOPEDIA_IMAGE_SERVICE
        service.max_bytes = 800
        service.max_items = 96
        size = QSize(10, 10)

        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"image-{index}.png" for index in range(3)]
            for path in paths:
                path.write_bytes(b"cache-key")

            image_cache.store_scaled_pixmap(paths[0], size, self._pixmap())
            image_cache.store_scaled_pixmap(paths[1], size, self._pixmap())
            self.assertEqual(image_cache.guide_home_image_cache_info()["bytes"], 800)

            # A hit makes image 0 most-recently-used. Inserting image 2 must
            # therefore evict image 1 rather than behaving like FIFO.
            self.assertFalse(image_cache.get_cached_scaled_pixmap(paths[0], size).isNull())
            image_cache.store_scaled_pixmap(paths[2], size, self._pixmap())

            self.assertFalse(image_cache.get_cached_scaled_pixmap(paths[0], size).isNull())
            self.assertTrue(image_cache.get_cached_scaled_pixmap(paths[1], size).isNull())
            self.assertFalse(image_cache.get_cached_scaled_pixmap(paths[2], size).isNull())
            info = image_cache.guide_home_image_cache_info()
            self.assertEqual(info["items"], 2)
            self.assertLessEqual(info["bytes"], info["max_bytes"])

    def test_oversized_pixmap_is_returned_but_not_cached(self) -> None:
        service = image_cache.ENCYCLOPEDIA_IMAGE_SERVICE
        service.max_bytes = 100
        service.max_items = 96
        size = QSize(10, 10)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            path.write_bytes(b"cache-key")
            pixmap = self._pixmap()

            returned = image_cache.store_scaled_pixmap(path, size, pixmap)

            self.assertFalse(returned.isNull())
            self.assertTrue(image_cache.get_cached_scaled_pixmap(path, size).isNull())
            self.assertEqual(image_cache.guide_home_image_cache_info()["items"], 0)
            self.assertEqual(image_cache.guide_home_image_cache_info()["bytes"], 0)

    def test_compatibility_wrappers_use_canonical_service(self) -> None:
        service = image_cache.ENCYCLOPEDIA_IMAGE_SERVICE
        size = QSize(10, 10)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.png"
            path.write_bytes(b"cache-key")
            stored = image_cache.store_scaled_pixmap(path, size, self._pixmap())

            self.assertFalse(stored.isNull())
            self.assertFalse(service.get_scaled(path, size).isNull())
            self.assertEqual(service.info(), image_cache.guide_home_image_cache_info())


if __name__ == "__main__":
    unittest.main()
