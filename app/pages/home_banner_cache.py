from __future__ import annotations

from pathlib import Path
from threading import Thread

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from app.pages.home_page import HomeBannerLabel as _BaseHomeBannerLabel
from app.startup_timing import startup_flush, startup_mark


class HomeBannerLabel(_BaseHomeBannerLabel):
    """Decode the Home banner off Qt and collapse resize scaling bursts."""

    imageDecoded = Signal(int, object)
    RESIZE_DEBOUNCE_MS = 24

    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        startup_mark("home_banner_construct")
        # Bypass the base constructor's synchronous QPixmap decode + first
        # SmoothTransformation. Reproduce its lightweight QLabel contract, then
        # deliver the local image from a short worker.
        QLabel.__init__(self, parent)
        self.setObjectName("HomeGuideBanner")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(145)
        self.setMaximumHeight(205)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._source = QPixmap()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(self.RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._flush_pending_pixmap)
        self._pending_render_size = QSize()
        self._rendered_size = QSize()
        self._image_load_generation = 0
        self._startup_tick_recorded = False
        self.imageDecoded.connect(self._finish_image_decode)

        # This callback cannot run until the shell has returned control to the
        # Qt event loop. It therefore bounds all synchronous startup construction
        # without requiring another hook in the large main.py module.
        QTimer.singleShot(0, self._record_first_ui_tick)

        path = Path(image_path)
        try:
            available = path.is_file()
        except OSError:
            available = False
        self.setVisible(available)
        if not available:
            return

        self._image_load_generation += 1
        generation = self._image_load_generation

        def worker() -> None:
            image = QImage(str(path))
            try:
                self.imageDecoded.emit(generation, image)
            except RuntimeError:
                # Home can be destroyed during application shutdown while this
                # one-shot local decode is finishing.
                pass

        Thread(target=worker, name="DofusAtlasHomeBanner", daemon=True).start()

    def _record_first_ui_tick(self) -> None:
        if self._startup_tick_recorded:
            return
        self._startup_tick_recorded = True
        startup_mark("ui_first_tick")
        startup_flush("first_ui_tick")

    def _finish_image_decode(self, generation: int, payload: object) -> None:
        if int(generation) != self._image_load_generation:
            return
        image = payload if isinstance(payload, QImage) else QImage()
        if image.isNull():
            self._source = QPixmap()
            self.setVisible(False)
            return
        startup_mark("home_banner_decoded")
        self._source = QPixmap.fromImage(image)
        self.setVisible(True)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        size = self.size()
        if size == self._rendered_size:
            return
        self._pending_render_size = QSize(size)
        # Restarting makes a continuous resize burst collapse into one expensive
        # SmoothTransformation at its final size. This also defers the first
        # scale until after the decoded image is delivered to the Qt thread.
        self._resize_timer.start()

    def _flush_pending_pixmap(self) -> None:
        size = self._pending_render_size
        if size.isEmpty():
            size = self.size()
        self._pending_render_size = QSize()
        if size != self._rendered_size:
            self._apply_scaled_pixmap(size)

    def _apply_scaled_pixmap(self, size: QSize) -> None:
        if self._source.isNull() or size.width() <= 0 or size.height() <= 0:
            return
        self.setPixmap(
            self._source.scaled(
                size,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        )
        self._rendered_size = QSize(size)


__all__ = ["HomeBannerLabel"]