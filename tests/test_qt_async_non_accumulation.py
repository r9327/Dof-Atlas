from __future__ import annotations

import os
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import app.modules.encyclopedia.views.guides_view as guides_module
from app.pages import organizer_page
from app.modules.encyclopedia.models import Guide
from app.modules.encyclopedia.views.guides_view import GuideHomeCard, SolutionImageLabel
from tools.atlas_performance_budget import evaluate_metric


ROOT = Path(__file__).resolve().parents[1]
BUDGETS = json.loads(
    (ROOT / "tools/atlas_performance_budgets.json").read_text(encoding="utf-8")
)["metrics"]


class _PendingFuture:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> bool:
        self.cancelled = True
        return True


class _CountingExecutor:
    def __init__(self) -> None:
        self.jobs: list[tuple[object, tuple[object, ...]]] = []
        self.futures: list[_PendingFuture] = []

    def submit(self, callback, *args) -> _PendingFuture:
        self.jobs.append((callback, args))
        future = _PendingFuture()
        self.futures.append(future)
        return future

    @property
    def pending(self) -> int:
        return sum(not future.cancelled for future in self.futures)


class QtAsyncNonAccumulationTests(unittest.TestCase):
    CYCLES = 50
    ALLOWED_THREAD_GROWTH = 0

    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _png(path: Path) -> None:
        image = QImage(24, 24, QImage.Format_ARGB32)
        image.fill(0xFF336699)
        if not image.save(str(path), "PNG"):
            raise AssertionError("temporary image could not be saved")

    @staticmethod
    def _destroy(widget) -> None:
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def test_guide_navigation_x50_does_not_accumulate_pending_image_futures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.png"
            self._png(path)
            executor = _CountingExecutor()
            guide = Guide(id="stress", title="Stress", category="dofus", image_path=str(path))
            before = executor.pending
            peak = before

            with patch.object(guides_module, "SOLUTION_IMAGE_EXECUTOR", executor):
                for _ in range(self.CYCLES):
                    card = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                    card.show()
                    self.app.processEvents()
                    peak = max(peak, executor.pending)
                    self._destroy(card)

                after = executor.pending
                reusable = GuideHomeCard(guide, variant="dofus", progress=(0, 1, "todo"))
                reusable.show()
                self.app.processEvents()
                self.assertEqual(len(executor.jobs), self.CYCLES + 1)
                self._destroy(reusable)

            self.assertEqual(before, 0)
            self.assertLessEqual(peak, 1)
            result = evaluate_metric(after, BUDGETS["pending_image_futures_after_x50"])
            self.assertEqual(result["status"], "PASS", result)

    def test_offscreen_organizer_does_not_install_native_window_hooks(self) -> None:
        profiles = organizer_page.default_profiles()
        with (
            patch.object(organizer_page, "read_json", return_value=profiles),
            patch.object(organizer_page, "write_json", return_value=None),
            patch.object(organizer_page, "write_text_atomic", return_value=None),
            patch.object(
                organizer_page.OrganizerPage,
                "auto_scan_sessions_on_startup",
                return_value=None,
            ),
            patch.object(organizer_page.UnityWindowEventWatcher, "start") as start_watcher,
        ):
            page = organizer_page.OrganizerPage(
                lambda _text: None,
                lambda *_args: None,
                lambda: None,
                lambda _entries: None,
                lambda _text: None,
                lambda *_args: None,
            )
            try:
                start_watcher.assert_not_called()
            finally:
                self._destroy(page)

    def test_destroying_solution_images_during_timer_x50_does_not_accumulate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solution.png"
            self._png(path)
            tracked_timers: list[QTimer] = []
            active_at_owner_destroy: list[bool] = []
            before_timers = 0
            before_threads = threading.active_count()
            peak_timers = before_timers

            for _ in range(self.CYCLES):
                label = SolutionImageLabel(str(path))
                timer = label._image_load_timer
                tracked_timers.append(timer)
                label.destroyed.connect(
                    lambda _obj=None, owned_timer=timer: active_at_owner_destroy.append(
                        isValid(owned_timer) and owned_timer.isActive()
                    )
                )
                label.show()
                peak_timers = max(
                    peak_timers,
                    sum(isValid(timer) and timer.isActive() for timer in tracked_timers),
                )
                self._destroy(label)

            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            after_timers = sum(isValid(timer) for timer in tracked_timers)
            after_threads = threading.active_count()

            timer_result = evaluate_metric(after_timers, BUDGETS["active_image_timers_after_x50"])
            self.assertEqual(timer_result["status"], "PASS", timer_result)
            self.assertEqual(active_at_owner_destroy, [False] * self.CYCLES)
            self.assertLessEqual(after_threads, before_threads + self.ALLOWED_THREAD_GROWTH)
            self.assertLessEqual(peak_timers, before_timers + 1)


if __name__ == "__main__":
    unittest.main()
