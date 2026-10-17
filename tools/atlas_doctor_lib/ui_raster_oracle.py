"""Bounded stdlib pixel oracle for repeated hollow-square fallback glyphs.

Consumes the REAL Qt screenshot (8-bit grayscale pixels) instead of trusting
QFontMetrics, DOM/widget text or a successful PNG save. No Qt dependency:
positive and negative tests run under the ordinary focused stdlib CI.
"""
from __future__ import annotations

from collections import Counter

_MIN_BOX_SIZE = 7
_MAX_BOX_SIZE = 18
_FAILURE_THRESHOLD = 16
_MAX_PIXELS = 4_000_000


def detect_replacement_squares(
    grayscale: bytes, width: int, height: int, stride: int,
    *, threshold: int = 125,
) -> dict:
    """Count hollow white/yellow glyphs with rectangular outlines.

    This deliberately detects the *raster* of repeated square glyphs. It does
    not infer legibility from Qt's loaded fonts, a text string or image hashes.
    Min 16 repeated squares prevents incidental checkbox/border false alarms.
    """
    if (not isinstance(width, int) or not isinstance(height, int)
            or not isinstance(stride, int) or width < 40 or height < 40
            or stride < width or width * height > _MAX_PIXELS
            or len(grayscale) < stride * height or not 1 <= threshold <= 254):
        return {
            "status": "BLOCKED", "reason": "INVALID_OR_OVERSIZED_RASTER",
            "box_count": 0, "threshold": _FAILURE_THRESHOLD,
        }

    # Each row is thresholded independently because Qt pads scan lines.
    pixels = [bytes(1 if color >= threshold else 0
                    for color in grayscale[y * stride:y * stride + width])
              for y in range(height)]
    sizes: Counter[int] = Counter()
    examples = []
    for y in range(height - _MIN_BOX_SIZE + 1):
        top = pixels[y]
        for side in range(_MIN_BOX_SIZE, _MAX_BOX_SIZE + 1):
            if y + side > height:
                break
            horizontal = b"\x01" * side
            x = top.find(horizontal)
            while x != -1:
                # Don't reinterpret the middle of a longer widget border as
                # a glyph, or a subrect within a bigger fallback character.
                if (x > 0 and top[x - 1]) or (x + side < width and top[x + side]):
                    x = top.find(horizontal, x + 1)
                    continue
                if pixels[y + side - 1][x:x + side] == horizontal and all(
                    row[x] and row[x + side - 1]
                    and not any(row[x + 1:x + side - 1])
                    for row in pixels[y + 1:y + side - 1]
                ):
                    sizes[side] += 1
                    if len(examples) < 12:
                        examples.append({"x": x, "y": y, "side": side})
                x = top.find(horizontal, x + 1)

    count = sum(sizes.values())
    detected = count >= _FAILURE_THRESHOLD
    return {
        "status": "FAIL" if detected else "PASS",
        "reason": "REPEATED_HOLLOW_SQUARE_GLYPHS" if detected else "NO_MASS_TOFU_PATTERN",
        "box_count": count, "failure_threshold": _FAILURE_THRESHOLD,
        "sizes": dict(sorted(sizes.items())), "examples": examples,
        "raster": {"width": width, "height": height, "stride": stride},
        "limits": "Detects mass square-fallback glyphs; not OCR, all icons, or full visual accessibility.",
    }
