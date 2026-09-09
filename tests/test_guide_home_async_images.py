from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import app.modules.encyclopedia.views.guides_view as guides_module
from app.modules.encyclopedia.models import DofusItem, Guide
from app.modules.encyclopedia.views.guide_home_image_cache import (
    clear_guide_home_image_cache,
    get_cached_scaled_pixmap,
)
from app.modules.encyclopedia.views.guides_view import GuideHomeCard, SolutionImageLabel


class _FakeExecutor:
    def __init__(self) -> None:
        self.jobs: list[tuple[object, tuple[object, ...]]] = []
        self.futures: list[_FakeFuture] = []

    def submit(self, callback, *args):
        self.jobs.append((callback, args))
        future = _FakeFuture()
        self.futures.append(future)
        return future


class _FakeFuture:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class GuideHomeAsyncImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        clear_guide_home_image_cache()

    def tearDown(self) -> None:
        clear_guide_home_image_cache()

    @staticmethod
    def _png(path: Path) -> None:
        image = QImage(48, 32, QImage.Format_ARGB32)
        image.fill(0xFF336699)
        if not image.save(str(path), "PNG"):
            raise AssertionError("temporary guide image could not be saved")

    @staticmethod
    def _item(path: Path) -> DofusItem:
        return DofusItem(
            id=1,
            original_id=1,
            name="Illustration",
            level=1,
            type_id=1,
            type_name="Test",
            image_path=str(path),
        )

    def test_card_owns_its_async_loader_canonically(self) -> None:
        self.assertTrue(GuideHomeCard._atlas_async_image_loader)
        self.assertEqual(GuideHomeCard._load_image.__module__, guides_module.__name__)

    def test_image_workers_transport_bytes_without_using_qimage_plugins(self) -> None:
        class SignalCapture:
            def __init__(self) -> None:
                self.calls = []

            def emit(self, *args) -> None:
                self.calls.append(args)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "raw-image.bin"
            path.write_bytes(b"image payload")
            guide_signal = SignalCapture()
            solution_signal = SignalCapture()
            delivery = SimpleNamespace(
                guideImageBytesRead=guide_signal,
                solutionImageBytesRead=solution_signal,
            )

            with (
                patch.object(guides_module, "_ASYNC_IMAGE_DELIVERY", delivery),
                patch.object(
                    guides_module,
                    "QImage",
                    side_effect=AssertionError("QImage decoding must stay on the Qt thread"),
                ),
            ):
                guides_module._decode_guide_image(None, (str(path),), QSize(30, 30))
                guides_module._decode_solution_image(None, str(path))

            self.assertEqual(guide_signal.calls[0][1], [(str(path), b"image payload")])
            self.assertEqual(solution_signal.calls[0][1], b"image payload")

    def test_hidden_images_do_not_queue_decode_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "guide.png"
            self._png(path)
            executor = _FakeExecutor()
            guide = Guide(
                id="hidden-image",
                title="Guide masqué",
                category="dofus",
                image_path=str(path),
            )

            with patch.object(guides_module, "SOLUTION_IMAGE_EXECUTOR", executor):
                card = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                solution = SolutionImageLabel(str(path))
                try:
                    self.assertEqual(executor.jobs, [])
                    self.assertFalse(solution._image_load_timer.isActive())
                finally:
                    card.deleteLater()
                    solution.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_first_card_decodes_in_executor_then_second_card_hits_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "guide.png"
            self._png(path)
            guide = Guide(
                id="async-image",
                title="Guide async",
                category="dofus",
                image_path=str(path),
            )
            executor = _FakeExecutor()

            with patch.object(guides_module, "SOLUTION_IMAGE_EXECUTOR", executor):
                first = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                try:
                    first.show()
                    self.app.processEvents()
                    first_label = first.findChild(QLabel, "GuideDofusImage")
                    self.assertIsNotNone(first_label)
                    self.assertEqual(len(executor.jobs), 1)
                    self.assertTrue(first_label.pixmap() is None or first_label.pixmap().isNull())

                    callback, args = executor.jobs[0]
                    callback(*args)
                    self.app.processEvents()

                    self.assertIsNotNone(first_label.pixmap())
                    self.assertFalse(first_label.pixmap().isNull())
                    cached = get_cached_scaled_pixmap(path, QSize(30, 30))
                    self.assertFalse(cached.isNull())

                    second = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                    try:
                        second_label = second.findChild(QLabel, "GuideDofusImage")
                        self.assertIsNotNone(second_label)
                        self.assertEqual(len(executor.jobs), 1)
                        self.assertIsNotNone(second_label.pixmap())
                        self.assertFalse(second_label.pixmap().isNull())
                    finally:
                        second.deleteLater()
                finally:
                    first.deleteLater()
                    self.app.processEvents()

    def test_worker_preserves_candidate_priority_and_falls_through_corrupt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corrupt = root / "corrupt.png"
            valid = root / "valid.png"
            corrupt.write_bytes(b"not-an-image")
            self._png(valid)
            guide = Guide(
                id="fallback-image",
                title="Guide fallback",
                category="dofus",
                image_path=str(corrupt),
                illustration_item=self._item(valid),
            )
            executor = _FakeExecutor()

            with patch.object(guides_module, "SOLUTION_IMAGE_EXECUTOR", executor):
                card = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                try:
                    card.show()
                    self.app.processEvents()
                    self.assertEqual(len(executor.jobs), 1)
                    callback, args = executor.jobs[0]
                    self.assertEqual(tuple(args[1]), (str(corrupt), str(valid)))
                    callback(*args)
                    self.app.processEvents()

                    label = card.findChild(QLabel, "GuideDofusImage")
                    self.assertIsNotNone(label)
                    self.assertIsNotNone(label.pixmap())
                    self.assertFalse(label.pixmap().isNull())
                    self.assertTrue(get_cached_scaled_pixmap(corrupt, QSize(30, 30)).isNull())
                    self.assertFalse(get_cached_scaled_pixmap(valid, QSize(30, 30)).isNull())
                finally:
                    card.deleteLater()
                    self.app.processEvents()

    def test_worker_result_is_ignored_after_card_is_destroyed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "guide.png"
            self._png(path)
            guide = Guide(
                id="destroyed-image",
                title="Guide détruit",
                category="dofus",
                image_path=str(path),
            )
            executor = _FakeExecutor()

            with patch.object(guides_module, "SOLUTION_IMAGE_EXECUTOR", executor):
                card = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                card.show()
                self.app.processEvents()
                self.assertEqual(len(executor.jobs), 1)
                callback, args = executor.jobs[0]
                card.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                self.assertTrue(executor.futures[0].cancelled)

                callback(*args)
                self.app.processEvents()

    def test_solution_worker_result_is_ignored_after_label_is_destroyed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "solution.png"
            self._png(path)
            executor = _FakeExecutor()

            with patch.object(guides_module, "SOLUTION_IMAGE_EXECUTOR", executor):
                label = SolutionImageLabel(str(path))
                label._image_load_timer.stop()
                label.start_image_load()
                self.assertEqual(len(executor.jobs), 1)
                callback, args = executor.jobs[0]
                label.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                self.assertTrue(executor.futures[0].cancelled)

                callback(*args)
                self.app.processEvents()

    def test_deferred_widget_callback_is_cancelled_with_its_owner(self) -> None:
        owner = QWidget()
        calls: list[str] = []
        guides_module._single_shot(owner, 0, lambda: calls.append("called"))

        owner.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
