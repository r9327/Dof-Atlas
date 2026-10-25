"""Create a local-only, non-destructive DOFUS Unity background without 3 HUD icons.

Identify and enter THREE bounding boxes (x,y,width,height) covering the icons
in the top-right of the 1919x1079 original. The algorithm reconstructs the
sky from all four edges of each box; review the result visually before using.

This tool never modifies the source and never grants publication rights.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

_ASSETS = Path(__file__).resolve().parents[2] / "app/assets/themes/dofus_unity"
SOURCE_SHA256 = "3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb"
SOURCE_SIZE = (1919, 1079)


def parse_box(value: str) -> tuple[int, int, int, int]:
    try:
        values = tuple(int(v.strip()) for v in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("box must be x,y,width,height") from exc
    if len(values) != 4 or any(v < 0 for v in values[:2]) or min(values[2:]) < 1:
        raise argparse.ArgumentTypeError("box must be x,y,width,height with positive dimensions")
    return values


def validate_boxes(size: tuple[int, int], boxes: list[tuple[int, int, int, int]]) -> None:
    width, height = size
    if len(boxes) != 3:
        raise ValueError("exactly three icon boxes required")
    for i, (x, y, w, h) in enumerate(boxes):
        if not (x >= round(width * 0.60) and y <= round(height * 0.35)):
            raise ValueError(f"box {i + 1} is not in the upper-right area")
        if x < 1 or y < 1 or x + w >= width - 1 or y + h >= height - 1:
            raise ValueError(f"box {i + 1} touches an image edge")
        if w > width // 8 or h > height // 5:
            raise ValueError(f"box {i + 1} is too large to repair safely")
        for x2, y2, w2, h2 in boxes[:i]:
            if x < x2 + w2 and x + w > x2 and y < y2 + h2 and y + h > y2:
                raise ValueError("icon boxes overlap")


def repair_sky(source: Image.Image, boxes: list[tuple[int, int, int, int]]) -> Image.Image:
    """Interpolate RGB from all four borders, modifying only the given boxes."""
    validate_boxes(source.size, boxes)
    original = source.convert("RGBA")
    edited = original.copy()
    src = original.load()
    dst = edited.load()
    for x, y, w, h in boxes:
        corners = (
            src[x - 1, y - 1], src[x + w, y - 1],
            src[x - 1, y + h], src[x + w, y + h],
        )
        for iy in range(h):
            v = (iy + 1) / (h + 1)
            left, right = src[x - 1, y + iy], src[x + w, y + iy]
            for ix in range(w):
                u = (ix + 1) / (w + 1)
                top, bottom = src[x + ix, y - 1], src[x + ix, y + h]
                repaired = []
                for channel in range(3):
                    horizontal = (1 - u) * left[channel] + u * right[channel]
                    vertical = (1 - v) * top[channel] + v * bottom[channel]
                    corner_blend = (
                        (1 - u) * (1 - v) * corners[0][channel]
                        + u * (1 - v) * corners[1][channel]
                        + (1 - u) * v * corners[2][channel]
                        + u * v * corners[3][channel]
                    )
                    repaired.append(round(max(0, min(255, horizontal + vertical - corner_blend))))
                dst[x + ix, y + iy] = (*repaired, src[x + ix, y + iy][3])
    return edited


def source_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_ASSETS / "background_selection_original.png")
    parser.add_argument("--output", type=Path, default=_ASSETS / "background_selection_clean.png")
    parser.add_argument("--box", dest="boxes", type=parse_box, action="append", required=True,
                        help="bounding box x,y,width,height; repeat exactly 3 times")
    parser.add_argument("--preview", type=Path, help="optional separate PNG with red outlines before repair")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("output must not overwrite the original")
    if args.preview and args.preview.resolve() in {args.source.resolve(), args.output.resolve()}:
        parser.error("preview must be separate from both the source and repaired output")
    if not args.source.is_file() or source_sha(args.source) != SOURCE_SHA256:
        parser.error("source SHA-256 mismatch or image missing; no output written")
    with Image.open(args.source) as raw:
        raw.load()
        if raw.size != SOURCE_SIZE:
            parser.error("unexpected original dimensions")
        try:
            validate_boxes(raw.size, args.boxes)
        except ValueError as exc:
            parser.error(str(exc))
        if args.preview:
            preview = raw.convert("RGB")
            drawing = ImageDraw.Draw(preview)
            for x, y, w, h in args.boxes:
                drawing.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 15, 15), width=3)
            args.preview.parent.mkdir(parents=True, exist_ok=True)
            preview.save(args.preview)
        result = repair_sky(raw, args.boxes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output, format="PNG")
    if source_sha(args.source) != SOURCE_SHA256:
        raise RuntimeError("original unexpectedly changed")
    print(f"Local derived wallpaper created: {args.output}; inspect visually before enabling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
