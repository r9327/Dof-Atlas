"""Conservative pixel-derived contrast check for bounded, plain-text Qt label crops.

The caller must supply pixels from the ACTUAL rendered screenshot at the label's
screen rectangle. This is not an OCR system nor a guarantee of full WCAG
compliance across every widget, state or pixel.
"""
from __future__ import annotations

from collections import Counter
from math import ceil

MAX_PIXELS = 150_000


def _luminance(rgb: tuple[int, int, int]) -> float:
    values = [c / 255 for c in rgb]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
              for v in values]
    return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    one, two = _luminance(a), _luminance(b)
    return (max(one, two) + 0.05) / (min(one, two) + 0.05)


def inspect_label_pixels(pixels: list[tuple[int, int, int]], *,
                         minimum_ratio: float = 4.5) -> dict:
    """Estimate foreground contrast from real glyph pixels vs dominant background.

    Enforce a meaningful number of bright/dark ink pixels. Fully uniform
    images are BLOCKED, not passed. A crop with mixed backgrounds, tiny text,
    or unverifiable glyph location must not be used as evidence of legibility.
    """
    if (not pixels or len(pixels) > MAX_PIXELS
            or not 1.0 <= minimum_ratio <= 21.0
            or any(len(c) != 3 or any(not isinstance(v, int) or not 0 <= v <= 255
                                      for v in c) for c in pixels)):
        return {"status": "BLOCKED", "reason": "INVALID_LABEL_RASTER"}
    # Bucket only for background classification; calculate WCAG using actual
    # RGB values, without treating antialiasing as the text foreground.
    bucket = lambda rgb: tuple((v // 8) * 8 for v in rgb)
    dominant, count = Counter(map(bucket, pixels)).most_common(1)[0]
    background_share = count / len(pixels)
    if background_share < 0.55:
        return {"status": "BLOCKED", "reason": "AMBIGUOUS_BACKGROUND",
                "background_share": round(background_share, 3)}
    distinct = sorted((_contrast(dominant, rgb) for rgb in pixels))
    ink_minimum = max(12, ceil(len(pixels) * 0.025))
    if len(distinct) < ink_minimum:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_PIXELS"}
    q95 = distinct[int(0.95 * (len(distinct) - 1))]
    q97 = distinct[int(0.97 * (len(distinct) - 1))]
    ink_at_least_1_4 = sum(c >= 1.4 for c in distinct)
    good_ink = sum(c >= minimum_ratio for c in distinct)
    if ink_at_least_1_4 < ink_minimum:
        status, reason = "FAIL", "TEXT_INVISIBLE_OR_TOO_FAINT"
    elif good_ink < ink_minimum:
        status, reason = "FAIL", "INSUFFICIENT_PIXEL_CONTRAST"
    else:
        status, reason = "PASS", "SCREENSHOT_TEXT_CONTRAST"
    return {
        "status": status, "reason": reason,
        "wcag_minimum_ratio": minimum_ratio,
        "background_rgb_approx": list(dominant),
        "background_share": round(background_share, 3),
        "contrast_ratio_q95": round(q95, 2),
        "contrast_ratio_q97": round(q97, 2),
        "pixels": len(pixels), "ink_pixels": ink_at_least_1_4,
        "above_minimum_ratio_pixels": good_ink,
        "required_ink_pixels": ink_minimum,
        "limits": "Pixel foreground/background contrast in a known plain QLabel crop only; not full WCAG or rich text.",
    }
