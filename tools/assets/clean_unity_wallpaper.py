"""Create a local-only, non-destructive DOFUS Unity background without 3 HUD icons.

On the SHA-256 verified 1919x1079 original, --corner-toolbar removes the
continuous three-button HUD strip at the top-right image edges. Otherwise
select one edge-aligned toolbar box or three interior icon boxes. An interior
box interpolates four edges; a corner box extrapolates left/bottom sky.
Always inspect the local result; it is never approved for redistribution.

This tool never modifies the source and never grants publication rights.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

_ASSETS = Path(__file__).resolve().parents[2] / "app/assets/themes/dofus_unity"
SOURCE_SHA256 = "3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb"
SOURCE_SIZE = (1919, 1079)
# Measured on the SHA-256 verified original; includes all three buttons AND
# the continuous dark backing strip flush with the top/right PNG edges.
SOURCE_CORNER_TOOLBAR = (1818, 0, 101, 39)


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
    # The original's three buttons share ONE backing strip at the top-right
    # corner. Three separate interior masks leave that backing strip behind.
    if len(boxes) == 1:
        x, y, w, h = boxes[0]
        if not (x >= round(width * 0.7) and y == 0 and x > 0
                and x + w == width and 1 <= w <= width // 4
                and 1 <= h <= height // 8 and h < height):
            raise ValueError("single toolbar box must cover the top-right edge")
        return
    if len(boxes) != 3:
        raise ValueError("use three interior boxes or one complete corner toolbar")
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
        if y == 0 and x + w == original.width:
            # At the image's top/right borders there are NO pixels above or
            # to the right to sample. A two-edge Coons extrapolation uses the
            # uninterrupted sky just left/below the *whole* HUD strip.
            corner = src[x - 1, h]
            for iy in range(h):
                left = src[x - 1, iy]
                for ix in range(w):
                    below = src[x + ix, h]
                    rgb = tuple(max(0, min(255, left[c] + below[c] - corner[c]))
                                for c in range(3))
                    dst[x + ix, iy] = (*rgb, src[x + ix, iy][3])
            continue
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


def canvas_box(start: tuple[int, int], end: tuple[int, int],
               offset: tuple[int, int], viewport: tuple[int, int]) -> tuple[int, int, int, int]:
    """Convert a dragged crop rectangle to original-image coordinates."""
    w, h = viewport
    x0, y0 = (max(0, min(v, limit)) for v, limit in zip(start, viewport))
    x1, y1 = (max(0, min(v, limit)) for v, limit in zip(end, viewport))
    return (min(x0, x1) + offset[0], min(y0, y1) + offset[1],
            abs(x1 - x0), abs(y1 - y0))


def select_boxes_interactively(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Windows desktop picker: show upper-right sky at native pixel resolution."""
    import tkinter as tk
    from tkinter import messagebox
    from PIL import ImageTk

    width, height = image.size
    xoff = round(width * 0.55)
    yoff = 0
    crop = image.crop((xoff, yoff, width, round(height * 0.40))).convert("RGB")
    cw, ch = crop.size
    window = tk.Tk()
    window.title("DOFUS Unity - sélectionner le bandeau en coin (local uniquement)")
    window.resizable(False, False)
    info = tk.Label(window, text="Encadrer le bandeau entier en coin (1 zone), ou choisir 3 zones intérieures.")
    info.pack(padx=12, pady=(12, 4))
    canvas = tk.Canvas(window, width=cw, height=ch, highlightthickness=1, highlightbackground="#555")
    canvas.pack(padx=12, pady=4)
    backing = ImageTk.PhotoImage(crop)
    canvas.create_image(0, 0, anchor="nw", image=backing)
    canvas.image_reference = backing
    status = tk.StringVar(value="0/3 zones sélectionnées")
    tk.Label(window, textvariable=status).pack(pady=3)
    selected: list[tuple[int, int, int, int]] = []
    outline_ids: list[int] = []
    result: list[tuple[int, int, int, int]] = []
    start_point: tuple[int, int] | None = None
    preview_id: int | None = None

    def press(event) -> None:
        nonlocal start_point, preview_id
        if len(selected) >= 3:
            return
        start_point = (event.x, event.y)
        if preview_id is not None:
            canvas.delete(preview_id)
        preview_id = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="yellow", width=2)

    def drag(event) -> None:
        if start_point is not None and preview_id is not None:
            canvas.coords(preview_id, *start_point, event.x, event.y)

    def release(event) -> None:
        nonlocal start_point, preview_id
        if start_point is None:
            return
        box = canvas_box(start_point, (event.x, event.y), (xoff, yoff), (cw, ch))
        start_point = None
        if preview_id is not None:
            canvas.delete(preview_id)
            preview_id = None
        if box[2] < 2 or box[3] < 2:
            return
        selected.append(box)
        x, y, w, h = box
        outline_ids.append(canvas.create_rectangle(x - xoff, y - yoff, x + w - xoff, y + h - yoff,
                                                   outline="red", width=2))
        status.set(f"{len(selected)}/3 zones sélectionnées")

    def undo() -> None:
        if selected:
            selected.pop()
            canvas.delete(outline_ids.pop())
            status.set(f"{len(selected)}/3 zones sélectionnées")

    def finish() -> None:
        try:
            validate_boxes(image.size, selected)
        except ValueError as exc:
            messagebox.showerror("Sélection invalide", str(exc), parent=window)
            return
        result.extend(selected)
        window.destroy()

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    buttons = tk.Frame(window)
    buttons.pack(pady=(5, 12))
    tk.Button(buttons, text="Annuler la dernière zone", command=undo).pack(side="left", padx=6)
    tk.Button(buttons, text="Valider 1 bandeau / 3 zones", command=finish).pack(side="left", padx=6)
    tk.Button(buttons, text="Quitter sans enregistrer", command=window.destroy).pack(side="left", padx=6)
    window.mainloop()
    if len(result) not in (1, 3):
        raise ValueError("sélection annulée ; aucun PNG produit")
    return result


def source_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_ASSETS / "background_selection_original.png")
    parser.add_argument("--output", type=Path, default=_ASSETS / "background_selection_clean.png")
    parser.add_argument("--interactive", action="store_true", help="select complete corner strip on original image")
    parser.add_argument("--corner-toolbar", action="store_true", help="use reviewed HUD strip bounds for verified original")
    parser.add_argument("--box", dest="boxes", type=parse_box, action="append", default=[],
                        help="one entire top-right strip or three interior icon boxes")
    parser.add_argument("--preview", type=Path, help="optional separate PNG with red outlines before repair")
    args = parser.parse_args()
    if sum(bool(value) for value in (args.interactive, args.corner_toolbar, args.boxes)) != 1:
        parser.error("choose --corner-toolbar, --interactive or --box")
    if args.corner_toolbar:
        args.boxes = [SOURCE_CORNER_TOOLBAR]
    if not args.interactive and len(args.boxes) not in (1, 3):
        parser.error("use one full-edge toolbar --box or three icon --box values")
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
        if args.interactive:
            try:
                args.boxes = select_boxes_interactively(raw)
            except (ValueError, RuntimeError, ImportError) as exc:
                parser.error(str(exc))
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
    # A failed save must never replace a previously approved wallpaper with
    # a truncated PNG (which Qt would then try to display on next launch).
    fd, staging_name = tempfile.mkstemp(
        prefix=".atlas-unity-background-", suffix=".png", dir=args.output.parent
    )
    os.close(fd)
    staging = Path(staging_name)
    try:
        result.save(staging, format="PNG")
        if source_sha(args.source) != SOURCE_SHA256:
            raise RuntimeError("original unexpectedly changed")
        os.replace(staging, args.output)
    finally:
        staging.unlink(missing_ok=True)
    print(f"Local derived wallpaper created: {args.output}; inspect visually before enabling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
