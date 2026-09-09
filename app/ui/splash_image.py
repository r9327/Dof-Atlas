from __future__ import annotations

from collections import deque

from PySide6.QtGui import QImage


_BACKGROUND_BRIGHTNESS_MAX = 42
_BACKGROUND_COLOR_SPREAD_MAX = 18


def _is_background_rgb(red: int, green: int, blue: int) -> bool:
    brightness = max(red, green, blue)
    color_spread = brightness - min(red, green, blue)
    return (
        brightness <= _BACKGROUND_BRIGHTNESS_MAX
        and color_spread <= _BACKGROUND_COLOR_SPREAD_MAX
    )


def _clear_connected_background_qrgb(image: QImage) -> QImage:
    """Portable fallback avoiding QColor allocation while keeping exact semantics."""

    width = image.width()
    height = image.height()
    visited = bytearray(width * height)
    queue: deque[int] = deque()

    for x in range(width):
        queue.append(x)
        if height > 1:
            queue.append((height - 1) * width + x)
    for y in range(1, max(1, height - 1)):
        queue.append(y * width)
        if width > 1:
            queue.append(y * width + width - 1)

    while queue:
        index = queue.popleft()
        if visited[index]:
            continue
        visited[index] = 1
        x = index % width
        y = index // width
        pixel = int(image.pixel(x, y))
        red = (pixel >> 16) & 0xFF
        green = (pixel >> 8) & 0xFF
        blue = pixel & 0xFF
        if not _is_background_rgb(red, green, blue):
            continue

        image.setPixel(x, y, pixel & 0x00FFFFFF)
        if x > 0:
            queue.append(index - 1)
        if x + 1 < width:
            queue.append(index + 1)
        if y > 0:
            queue.append(index - width)
        if y + 1 < height:
            queue.append(index + width)
    return image


def clear_connected_dark_background(image: QImage) -> QImage:
    """Make only edge-connected near-black neutral pixels transparent.

    The visual rule is intentionally identical to the historical splash flood
    fill. The fast path works directly on RGBA8888 bytes, uses one byte per
    visited pixel, and queues flat integer indexes instead of allocating QColor
    objects and coordinate tuples for every pixel. A QRgb fallback preserves the
    exact behavior if a PySide build does not expose a writable image buffer.
    """

    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return image

    rgba = image.convertToFormat(QImage.Format_RGBA8888)
    width = rgba.width()
    height = rgba.height()
    bytes_per_line = rgba.bytesPerLine()

    try:
        raw = rgba.bits()
        if hasattr(raw, "setsize"):
            raw.setsize(rgba.sizeInBytes())
        pixels = memoryview(raw).cast("B")
        if len(pixels) < rgba.sizeInBytes():
            raise BufferError("QImage buffer view is shorter than sizeInBytes")
    except (BufferError, TypeError, ValueError, AttributeError):
        return _clear_connected_background_qrgb(rgba)

    visited = bytearray(width * height)
    queue: deque[int] = deque()
    for x in range(width):
        queue.append(x)
        if height > 1:
            queue.append((height - 1) * width + x)
    for y in range(1, max(1, height - 1)):
        queue.append(y * width)
        if width > 1:
            queue.append(y * width + width - 1)

    while queue:
        index = queue.popleft()
        if visited[index]:
            continue
        visited[index] = 1
        x = index % width
        y = index // width
        offset = y * bytes_per_line + x * 4
        red = int(pixels[offset])
        green = int(pixels[offset + 1])
        blue = int(pixels[offset + 2])
        if not _is_background_rgb(red, green, blue):
            continue

        pixels[offset + 3] = 0
        if x > 0:
            queue.append(index - 1)
        if x + 1 < width:
            queue.append(index + 1)
        if y > 0:
            queue.append(index - width)
        if y + 1 < height:
            queue.append(index + width)

    return rgba


__all__ = ["clear_connected_dark_background"]
