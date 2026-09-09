from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

import app.pages.home_banner_cache as banner_module
from app.pages.home_banner_cache import HomeBannerLabel


class _CapturedThread:
    instances: list["_CapturedThread"] = []

    def __init__(self, *, target, name: str, daemon: bool) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.started = True


class HomeBannerAsyncDecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        _CapturedThread.instances.clear()

    @staticmethod
    def _make_png(path: Path) -> None:
        image = QImage(16, 10, QImage.Format_ARGB32)
        image.fill(0xFF335577)
        if not image.save(str(path), "PNG"):
            raise RuntimeError("temporary PNG save failed")

    def test_constructor_schedules_decode_without_loading_pixmap_synchronously(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "banner.png"
            self._make_png(path)
            with patch.object(banner_module, "Thread", _CapturedThread):
                label = HomeBannerLabel(path)
            try:
                self.assertEqual(label.objectName(), "HomeGuideBanner")
                self.assertEqual(label.minimumHeight(), 145)
                self.assertEqual(label.maximumHeight(), 205)
                self.assertTrue(label._source.isNull())
                self.assertEqual(len(_CapturedThread.instances), 1)
                worker = _CapturedThread.instances[0]
                self.assertTrue(worker.started)
                self.assertTrue(worker.daemon)
                self.assertEqual(worker.name, "DofusAtlasHomeBanner")
            finally:
                label.deleteLater()
                self.app.processEvents()

    def test_worker_delivery_populates_source_then_scaling_remains_deferred(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "banner.png"
            self._make_png(path)
            with patch.object(banner_module, "Thread", _CapturedThread):
                label = HomeBannerLabel(path)
            try:
                label.resize(320, 170)
                worker = _CapturedThread.instances[0]
                worker.target()
                self.app.processEvents()

                self.assertFalse(label._source.isNull())
                self.assertTrue(label._resize_timer.isActive())
                self.assertTrue(label.pixmap() is None or label.pixmap().isNull())

                label._resize_timer.stop()
                label._flush_pending_pixmap()
                self.assertIsNotNone(label.pixmap())
                self.assertFalse(label.pixmap().isNull())
            finally:
                label.deleteLater()
                self.app.processEvents()

    def test_missing_banner_does_not_start_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.png"
            with patch.object(banner_module, "Thread", _CapturedThread):
                label = HomeBannerLabel(path)
            try:
                self.assertEqual(_CapturedThread.instances, [])
                self.assertTrue(label._source.isNull())
                self.assertTrue(label.isHidden())
            finally:
                label.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
