from __future__ import annotations

import time
from pathlib import Path
from types import ModuleType

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader


SOLUTION_DECODE_MAX_SIZE = QSize(1180, 860)


def decode_scaled_image(path: str | Path, target_size: QSize, *, kind: str = "image") -> QImage:
    """Decode directly near the required display size.

    QImage.fromData() decodes the complete source bitmap first. A 4K screenshot
    can therefore consume tens of megabytes even when Atlas displays it at a few
    hundred pixels. QImageReader can request the scaled raster from the decoder,
    avoiding the full-resolution intermediate allocation in the long-lived app.
    """

    source = Path(path)
    reader = QImageReader(str(source))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)

    requested = QSize(target_size)
    original = reader.size()
    if (
        requested.isValid()
        and requested.width() > 0
        and requested.height() > 0
        and original.isValid()
        and original.width() > 0
        and original.height() > 0
    ):
        scaled = QSize(original)
        scaled.scale(requested, Qt.KeepAspectRatio)
        if scaled.width() < original.width() or scaled.height() < original.height():
            reader.setScaledSize(scaled)

    return reader.read()


def install_guide_image_runtime_policy(module: ModuleType) -> None:
    """Bind bounded decoders to the existing Guide async delivery contract.

    Keeping the decode policy isolated avoids coupling the large Guide UI module
    to image-cache internals and gives Bestiary/native equipment a reusable
    foundation later.
    """

    def decode_guide_image(target_ref, paths: tuple[str, ...], size: QSize) -> None:
        started = time.perf_counter()
        image = QImage()
        used_path = ""
        for path in paths:
            candidate = decode_scaled_image(path, size, kind="guide")
            if candidate.isNull():
                continue
            image = candidate
            used_path = path
            break
        logger = getattr(module, "LOGGER", None)
        if logger is not None:
            logger.debug(
                "scaled image decode kind=guide width=%d height=%d worker_ms=%.3f",
                image.width(),
                image.height(),
                (time.perf_counter() - started) * 1000.0,
            )
        delivery = getattr(module, "_ASYNC_IMAGE_DELIVERY", None)
        if delivery is not None:
            delivery.guideImageDecoded.emit(target_ref, image, size, used_path)

    def decode_solution_image(target_ref, image_path: str) -> None:
        started = time.perf_counter()
        image = decode_scaled_image(
            image_path,
            SOLUTION_DECODE_MAX_SIZE,
            kind="solution",
        )
        logger = getattr(module, "LOGGER", None)
        if logger is not None:
            logger.debug(
                "scaled image decode kind=solution width=%d height=%d worker_ms=%.3f",
                image.width(),
                image.height(),
                (time.perf_counter() - started) * 1000.0,
            )
        delivery = getattr(module, "_ASYNC_IMAGE_DELIVERY", None)
        if delivery is not None:
            delivery.solutionImageDecoded.emit(target_ref, image)

    module._decode_guide_image = decode_guide_image
    module._decode_solution_image = decode_solution_image


__all__ = [
    "SOLUTION_DECODE_MAX_SIZE",
    "decode_scaled_image",
    "install_guide_image_runtime_policy",
]
