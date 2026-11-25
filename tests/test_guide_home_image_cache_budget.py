from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.modules.encyclopedia.services.image_service import ImageService


class GuideHomeImageCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.service = ImageService(max_bytes=800, max_items=96)

    @staticmethod
    def _pixmap(size: int = 10) -> QPixmap:
        return QPixmap(size, size)

    def test_cache_is_byte_bounded_and_true_lru(self) -> None:
        service = self.service
        size = QSize(10, 10)

        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"image-{index}.png" for index in range(3)]
            for path in paths:
                path.write_bytes(b"cache-key")

            service.store_scaled(paths[0], size, self._pixmap())
            service.store_scaled(paths[1], size, self._pixmap())
            self.assertEqual(service.info()["bytes"], 800)

            # A hit makes image 0 most-recently-used. Inserting image 2 must
            # therefore evict image 1 rather than behaving like FIFO.
            self.assertFalse(service.get_scaled(paths[0], size).isNull())
            service.store_scaled(paths[2], size, self._pixmap())

            self.assertFalse(service.get_scaled(paths[0], size).isNull())
            self.assertTrue(service.get_scaled(paths[1], size).isNull())
            self.assertFalse(service.get_scaled(paths[2], size).isNull())
            info = service.info()
            self.assertEqual(info["items"], 2)
            self.assertLessEqual(info["bytes"], info["max_bytes"])

    def test_oversized_pixmap_is_returned_but_not_cached(self) -> None:
        service = self.service
        service.max_bytes = 100
        size = QSize(10, 10)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            path.write_bytes(b"cache-key")
            pixmap = self._pixmap()

            returned = service.store_scaled(path, size, pixmap)

            self.assertFalse(returned.isNull())
            self.assertTrue(service.get_scaled(path, size).isNull())
            self.assertEqual(service.info()["items"], 0)
            self.assertEqual(service.info()["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
