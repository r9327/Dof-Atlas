from __future__ import annotations

import csv
import json
import math
import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "data" / "reports" / "dofus_worldmap_scan"
TARGET_IDS = {1, 2, 3, 10, 12, 13, 14, 15, 16, 18, 21, 28, 33, 34, 35, 37, 38, 40, 41}


@dataclass(slots=True)
class Candidate:
    path: Path
    exported_path: str
    path_id: str
    asset_name: str
    width: int
    height: int
    black_ratio: float
    score: float = 0.0
    rmse: float = 0.0
    aspect_delta: float = 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-ids", default=",".join(str(item) for item in sorted(TARGET_IDS)))
    parser.add_argument("--include-doduda", action="store_true")
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    target_ids = {int(item.strip()) for item in args.target_ids.split(",") if item.strip()}

    manifest = json.loads((ROOT_DIR / "data" / "cartography" / "map_views.json").read_text(encoding="utf-8"))
    world_data = {
        int(row["id"]): row
        for row in json.loads((REPORT_DIR / "worldmap_data_root.json").read_text(encoding="utf-8"))
    }
    views = {
        int(view["worldmap_id"]): view
        for view in manifest["views"]
        if int(view.get("worldmap_id") or 0) in target_ids
    }
    candidates = load_candidates(include_doduda=args.include_doduda)
    results: list[dict[str, object]] = []
    sheet_rows: list[tuple[dict[str, object], list[Candidate]]] = []
    for worldmap_id in sorted(target_ids):
        view = views.get(worldmap_id)
        data = world_data.get(worldmap_id)
        if not view or not data:
            continue
        current_path = ROOT_DIR / view["asset_path"]
        ratio = float(data["totalWidth"]) / float(data["totalHeight"])
        current = Image.open(current_path).convert("RGBA")
        current_norm = normalize_to_ratio(current, ratio, size=160)
        current_mask = make_mask(current_norm)
        ranked: list[Candidate] = []
        for cand in candidates:
            cand_ratio = cand.width / max(1, cand.height)
            cand.aspect_delta = abs(math.log(max(cand_ratio, 0.001) / ratio))
            if cand.aspect_delta > 0.55:
                continue
            image = Image.open(cand.path).convert("RGBA")
            cand_norm = normalize_to_ratio(image, ratio, size=160)
            cand.rmse = masked_rmse(current_norm, cand_norm, current_mask)
            area_bonus = min(80.0, math.log(max(1, cand.width * cand.height), 2) * 3.0)
            cand.score = 1000.0 - cand.rmse * 4.0 - cand.aspect_delta * 180.0 - cand.black_ratio * 80.0 + area_bonus
            ranked.append(cand)
        ranked.sort(key=lambda item: item.score, reverse=True)
        top = ranked[:8]
        record = {
            "worldmap_id": worldmap_id,
            "view_key": view["view_key"],
            "name": view["name"],
            "asset_path": view["asset_path"],
            "expected_size": [data["totalWidth"], data["totalHeight"]],
            "current_size": list(current.size),
            "top_candidates": [
                {
                    "exported_path": cand.exported_path,
                    "path_id": cand.path_id,
                    "asset_name": cand.asset_name,
                    "size": [cand.width, cand.height],
                    "score": round(cand.score, 2),
                    "rmse": round(cand.rmse, 2),
                    "aspect_delta": round(cand.aspect_delta, 4),
                    "black_ratio": round(cand.black_ratio, 4),
                }
                for cand in top
            ],
        }
        results.append(record)
        sheet_rows.append((record, top[:4]))

    suffix = f"_{args.suffix}" if args.suffix else ""
    out_json = REPORT_DIR / f"repair_candidate_matches{suffix}.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    sheet_path = REPORT_DIR / f"repair_candidates_sheet{suffix}.jpg"
    render_sheet(sheet_rows, sheet_path)
    print(f"matches={out_json}")
    print(f"sheet={sheet_path}")
    return 0


def load_candidates(*, include_doduda: bool) -> list[Candidate]:
    rows: list[Candidate] = []
    csv_path = REPORT_DIR / "worldmap_texture_candidates.csv"
    seen: set[Path] = set()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            exported = row.get("exported_path", "").strip()
            if not exported:
                continue
            path = ROOT_DIR / exported
            if path in seen or not path.exists():
                continue
            seen.add(path)
            width = int(float(row.get("width") or 0))
            height = int(float(row.get("height") or 0))
            if width < 300 or height < 220:
                continue
            black_ratio = compute_black_ratio(path)
            rows.append(
                Candidate(
                    path=path,
                    exported_path=exported.replace("\\", "/"),
                    path_id=row.get("path_id", ""),
                    asset_name=row.get("asset_name", ""),
                    width=width,
                    height=height,
                    black_ratio=black_ratio,
                )
            )
    if include_doduda:
        doduda_dir = ROOT_DIR / "data" / "cache" / "dofus_maps" / "raw" / "doduda_cli" / "img" / "worldmap"
        for path in sorted(doduda_dir.glob("*.png"), key=lambda item: item.name.casefold()):
            if path in seen or not path.exists():
                continue
            try:
                with Image.open(path) as image:
                    width, height = image.size
            except OSError:
                continue
            if width < 300 or height < 220:
                continue
            seen.add(path)
            rows.append(
                Candidate(
                    path=path,
                    exported_path=str(path.relative_to(ROOT_DIR)).replace("\\", "/"),
                    path_id="",
                    asset_name=path.stem,
                    width=width,
                    height=height,
                    black_ratio=compute_black_ratio(path),
                )
            )
    return rows


def compute_black_ratio(path: Path) -> float:
    image = Image.open(path).convert("RGBA")
    image.thumbnail((220, 220), Image.Resampling.LANCZOS)
    pixels = image.getdata()
    visible = 0
    black = 0
    for r, g, b, a in pixels:
        if a <= 8:
            continue
        visible += 1
        if max(r, g, b) < 22:
            black += 1
    if visible == 0:
        return 1.0
    return black / visible


def normalize_to_ratio(image: Image.Image, ratio: float, *, size: int) -> Image.Image:
    image = image.convert("RGBA")
    w, h = image.size
    current_ratio = w / max(1, h)
    if current_ratio > ratio:
        target_w = w
        target_h = max(h, int(round(w / ratio)))
    else:
        target_h = h
        target_w = max(w, int(round(h * ratio)))
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.alpha_composite(image, (0, 0))
    canvas.thumbnail((size, size), Image.Resampling.LANCZOS)
    final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    final.alpha_composite(canvas, (0, 0))
    return final


def make_mask(image: Image.Image) -> list[int]:
    mask: list[int] = []
    for r, g, b, a in image.getdata():
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        mask.append(1 if a > 8 and luma > 18 else 0)
    return mask


def masked_rmse(a: Image.Image, b: Image.Image, mask: list[int]) -> float:
    total = 0.0
    count = 0
    for idx, (pa, pb) in enumerate(zip(a.getdata(), b.getdata())):
        if not mask[idx]:
            continue
        dr = pa[0] - pb[0]
        dg = pa[1] - pb[1]
        db = pa[2] - pb[2]
        total += dr * dr + dg * dg + db * db
        count += 3
    if count == 0:
        return 999.0
    return math.sqrt(total / count)


def render_sheet(rows: list[tuple[dict[str, object], list[Candidate]]], path: Path) -> None:
    card_w, card_h = 310, 310
    cols = 5
    sheet_w = cols * card_w
    sheet_h = max(1, len(rows)) * card_h
    sheet = Image.new("RGB", (sheet_w, sheet_h), (244, 244, 240))
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(13, bold=True)
    font = load_font(11)
    for row_idx, (record, candidates) in enumerate(rows):
        y = row_idx * card_h
        current_path = ROOT_DIR / str(record["asset_path"])
        draw_cell(draw, sheet, 0, y, card_w, card_h, current_path, f"{record['worldmap_id']} CURRENT", font, title_font)
        for idx, cand in enumerate(candidates, start=1):
            label = f"{idx} score {cand.score:.0f} {cand.width}x{cand.height}"
            draw_cell(draw, sheet, idx, y, card_w, card_h, cand.path, label, font, title_font)
        draw.text((8, y + card_h - 20), str(record["name"])[:45], fill=(20, 20, 20), font=font)
    sheet.save(path, "JPEG", quality=91, optimize=True)


def draw_cell(
    draw: ImageDraw.ImageDraw,
    sheet: Image.Image,
    col: int,
    y: int,
    card_w: int,
    card_h: int,
    image_path: Path,
    label: str,
    font: ImageFont.ImageFont,
    title_font: ImageFont.ImageFont,
) -> None:
    x = col * card_w
    draw.rectangle((x + 5, y + 5, x + card_w - 5, y + card_h - 5), fill=(255, 255, 255), outline=(198, 198, 192))
    try:
        image = Image.open(image_path).convert("RGB")
        image.thumbnail((card_w - 18, 220), Image.Resampling.LANCZOS)
        sheet.paste(image, (x + (card_w - image.width) // 2, y + 12))
    except OSError:
        draw.text((x + 12, y + 24), "image unavailable", fill=(180, 20, 20), font=font)
    draw.text((x + 10, y + 238), label, fill=(10, 10, 10), font=title_font)
    draw.text((x + 10, y + 256), image_path.name[:42], fill=(40, 40, 40), font=font)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size)
        except OSError:
            pass
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())
