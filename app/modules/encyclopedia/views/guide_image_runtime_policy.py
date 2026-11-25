from __future__ import annotations

from pathlib import Path

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


__all__ = ["SOLUTION_DECODE_MAX_SIZE", "decode_scaled_image"]
