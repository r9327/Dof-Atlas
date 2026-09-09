from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import os
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
UNITYPY_VENDOR = ROOT_DIR / ".codex_deps" / "unitypy"
if UNITYPY_VENDOR.exists():
    sys.path.insert(0, str(UNITYPY_VENDOR))

import UnityPy  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat  # noqa: E402
from UnityPy import config as unitypy_config  # noqa: E402


LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
DOFUS_INSTALL_DIR = LOCAL_APP_DATA / "Ankama" / "Dofus-dofus3"
REQUESTED_MAP_DIR = DOFUS_INSTALL_DIR / "Map"
CLIENT_CONTENT_MAP_DIR = DOFUS_INSTALL_DIR / "Dofus_Data" / "StreamingAssets" / "Content" / "Map"
OUTPUT_DIR = ROOT_DIR / "data" / "reports" / "cartography_bundle_scan"
EXPORT_DIR = OUTPUT_DIR / "exports"
CSV_PATH = OUTPUT_DIR / "bundle_textures.csv"
SHEET_PATH = OUTPUT_DIR / "bundle_candidates_sheet.jpg"

IMAGE_TYPES = {"Texture2D", "Sprite"}
UNITY_FALLBACK_VERSION = "6000.0.0f1"

KEYWORD_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("amakna", 140),
    ("enutrosor", 140),
    ("enurado", 120),
    ("worldmap", 95),
    ("world_map", 95),
    ("cartography", 80),
    ("world_13", 70),
    ("world-13", 70),
    ("world 13", 70),
    ("world_1", 50),
    ("world-1", 50),
    ("world 1", 50),
    ("world", 35),
    ("subarea", 35),
    ("area", 30),
    ("mapdata", 20),
    ("mapgfx", 18),
    ("map", 10),
)

REJECT_NAME_HINTS = (
    "mapeffects",
    "effect",
    "mask",
    "shadow",
    "overlay",
    "border",
    "frame",
    "cloud",
    "sky",
    "parchment",
    "illustration",
    "background",
)


@dataclass(slots=True)
class ImageRow:
    bundle: str
    bundle_path: str
    bundle_bytes: int
    object_type: str
    path_id: str
    asset_name: str
    width: int = 0
    height: int = 0
    mode: str = ""
    score: int = 0
    mean_luma: float = 0.0
    luma_stddev: float = 0.0
    visible_ratio: float = 1.0
    reject_reason: str = ""
    exported_path: str = ""
    error: str = ""

    def to_csv_row(self) -> dict[str, object]:
        return {
            "bundle": self.bundle,
            "bundle_path": self.bundle_path,
            "bundle_bytes": self.bundle_bytes,
            "object_type": self.object_type,
            "path_id": self.path_id,
            "asset_name": self.asset_name,
            "width": self.width,
            "height": self.height,
            "mode": self.mode,
            "score": self.score,
            "mean_luma": f"{self.mean_luma:.2f}",
            "luma_stddev": f"{self.luma_stddev:.2f}",
            "visible_ratio": f"{self.visible_ratio:.4f}",
            "reject_reason": self.reject_reason,
            "exported_path": self.exported_path,
            "error": self.error,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Dofus 3 Unity map bundles for cartography image candidates.")
    parser.add_argument("--map-dir", type=Path, default=None, help="Map bundle directory to scan recursively.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Report output directory.")
    parser.add_argument("--min-export-score", type=int, default=45, help="Minimum candidate score required for PNG export.")
    parser.add_argument("--min-size", type=int, default=256, help="Reject images with either side below this size.")
    parser.add_argument("--preview-limit", type=int, default=80, help="Maximum candidates shown in the preview sheet.")
    parser.add_argument("--max-exports", type=int, default=500, help="Maximum top-ranked PNG candidates to export. Use 0 for all.")
    parser.add_argument("--clean-exports", action="store_true", help="Remove old PNG exports from the output export directory first.")
    parser.add_argument(
        "--max-decode-bundle-mb",
        type=int,
        default=0,
        help="If set, bundles larger than this are scanned as image metadata only and are not PNG-decoded.",
    )
    parser.add_argument("--fallback-unity-version", default=UNITY_FALLBACK_VERSION)
    parser.add_argument("--bundle-filter", default="", help="Case-insensitive substring filter for diagnostic runs.")
    parser.add_argument("--limit-bundles", type=int, default=0, help="Limit bundle count for diagnostic runs.")
    args = parser.parse_args()

    map_dir = resolve_map_dir(args.map_dir)
    output_dir = args.output_dir
    export_dir = output_dir / "exports"
    csv_path = output_dir / "bundle_textures.csv"
    sheet_path = output_dir / "bundle_candidates_sheet.jpg"
    output_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    if args.clean_exports:
        clean_export_dir(export_dir, output_dir)

    unitypy_config.FALLBACK_UNITY_VERSION = args.fallback_unity_version
    warnings.filterwarnings("ignore", message="No valid Unity version found.*")

    bundles = sorted(map_dir.rglob("*.bundle"), key=lambda path: str(path).casefold())
    if args.bundle_filter:
        needle = args.bundle_filter.casefold()
        bundles = [path for path in bundles if needle in str(path).casefold()]
    if args.limit_bundles > 0:
        bundles = bundles[: args.limit_bundles]
    if not bundles:
        raise SystemExit(f"No .bundle files found under {map_dir}")

    print(f"Map dir: {map_dir}")
    print(f"Bundles: {len(bundles)}")
    print(f"CSV: {csv_path}")
    print(f"Exports: {export_dir}")

    fieldnames = list(ImageRow("", "", 0, "", "", "").to_csv_row().keys())
    candidate_rows: list[ImageRow] = []
    image_count = 0
    error_count = 0
    bundle_error_count = 0

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, bundle_path in enumerate(bundles, start=1):
            rel_bundle = relative_to_root(bundle_path, map_dir)
            if index == 1 or index % 25 == 0 or rel_bundle.startswith("Textures"):
                print(f"[{index}/{len(bundles)}] {rel_bundle}", flush=True)
            metadata_only = (
                args.max_decode_bundle_mb > 0
                and safe_size(bundle_path) > args.max_decode_bundle_mb * 1024 * 1024
            )
            if metadata_only:
                print(f"  metadata-only: bundle exceeds {args.max_decode_bundle_mb} MB", flush=True)
            try:
                rows = scan_bundle(bundle_path, map_dir, min_size=args.min_size, metadata_only=metadata_only)
            except Exception as exc:
                bundle_error_count += 1
                rows = [
                    ImageRow(
                        bundle=rel_bundle,
                        bundle_path=str(bundle_path),
                        bundle_bytes=safe_size(bundle_path),
                        object_type="",
                        path_id="",
                        asset_name="",
                        error=f"bundle_error: {type(exc).__name__}: {exc}",
                    )
                ]
            for row in rows:
                image_count += 1
                if row.error:
                    error_count += 1
                if should_export(row, args.min_export_score):
                    candidate_rows.append(row)
                writer.writerow(row.to_csv_row())
            if index % 25 == 0:
                handle.flush()
            del rows
            gc.collect()

    exported_rows = select_export_rows(candidate_rows, max_exports=args.max_exports)
    export_selected_images(exported_rows, export_dir)
    rewrite_csv_export_results(csv_path, fieldnames, exported_rows)

    make_preview_sheet(exported_rows, sheet_path, limit=args.preview_limit)
    print(f"Images seen: {image_count}")
    print(f"Candidate rows: {len(candidate_rows)}")
    print(f"Exported candidates: {sum(1 for row in exported_rows if row.exported_path)}")
    print(f"Image errors: {error_count}")
    print(f"Bundle errors: {bundle_error_count}")
    print(f"Preview: {sheet_path}")
    return 0


def resolve_map_dir(provided: Path | None) -> Path:
    candidates = [provided] if provided is not None else [REQUESTED_MAP_DIR, CLIENT_CONTENT_MAP_DIR]
    for candidate in candidates:
        if candidate is not None and candidate.exists() and candidate.is_dir():
            return candidate
    checked = ", ".join(str(path) for path in candidates if path is not None)
    raise SystemExit(f"Map directory not found. Checked: {checked}")


def scan_bundle(
    bundle_path: Path,
    map_dir: Path,
    *,
    min_size: int,
    metadata_only: bool,
) -> list[ImageRow]:
    bundle_name = relative_to_root(bundle_path, map_dir)
    bundle_bytes = safe_size(bundle_path)
    env = UnityPy.load(str(bundle_path))
    rows: list[ImageRow] = []
    seen_texture_assets: set[str] = set()
    for obj in env.objects:
        object_type = getattr(obj.type, "name", str(obj.type))
        if object_type not in IMAGE_TYPES:
            continue
        path_id = str(getattr(obj, "path_id", ""))
        try:
            data = obj.read()
            asset_name = str(getattr(data, "name", "") or getattr(data, "m_Name", "") or path_id)
            width, height = image_dimensions(data, object_type)
            if object_type == "Texture2D":
                seen_texture_assets.add(asset_name)
            if metadata_only:
                rows.append(
                    build_row_from_values(
                        bundle_path=bundle_path,
                        bundle_name=bundle_name,
                        bundle_bytes=bundle_bytes,
                        object_type=object_type,
                        path_id=path_id,
                        asset_name=asset_name,
                        width=width,
                        height=height,
                        mode="",
                        mean_luma=0.0,
                        luma_stddev=0.0,
                        visible_ratio=1.0,
                        min_size=min_size,
                        reject_reason_override="metadata_only_large_bundle",
                    )
                )
                continue
            elif asset_name in seen_texture_assets:
                rows.append(
                    build_row_from_values(
                        bundle_path=bundle_path,
                        bundle_name=bundle_name,
                        bundle_bytes=bundle_bytes,
                        object_type=object_type,
                        path_id=path_id,
                        asset_name=asset_name,
                        width=width,
                        height=height,
                        mode="",
                        mean_luma=0.0,
                        luma_stddev=0.0,
                        visible_ratio=1.0,
                        min_size=min_size,
                        reject_reason_override="duplicate_texture_asset",
                    )
                )
                continue
            if width > 0 and height > 0 and (width < min_size or height < min_size):
                rows.append(
                    build_row_from_values(
                        bundle_path=bundle_path,
                        bundle_name=bundle_name,
                        bundle_bytes=bundle_bytes,
                        object_type=object_type,
                        path_id=path_id,
                        asset_name=asset_name,
                        width=width,
                        height=height,
                        mode="",
                        mean_luma=0.0,
                        luma_stddev=0.0,
                        visible_ratio=1.0,
                        min_size=min_size,
                    )
                )
                continue
            image = getattr(data, "image", None)
            if image is None:
                raise ValueError("UnityPy returned no image")
            image = normalize_image(image)
            row = build_row(
                bundle_path=bundle_path,
                bundle_name=bundle_name,
                bundle_bytes=bundle_bytes,
                object_type=object_type,
                path_id=path_id,
                asset_name=asset_name,
                image=image,
                min_size=min_size,
            )
            rows.append(row)
        except Exception as exc:
            rows.append(
                ImageRow(
                    bundle=bundle_name,
                    bundle_path=str(bundle_path),
                    bundle_bytes=bundle_bytes,
                    object_type=object_type,
                    path_id=path_id,
                    asset_name="",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return rows


def normalize_image(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "RGB"}:
        return image.copy()
    if "A" in image.getbands():
        return image.convert("RGBA")
    return image.convert("RGB")


def image_dimensions(data: object, object_type: str) -> tuple[int, int]:
    if object_type == "Texture2D":
        return int(getattr(data, "m_Width", 0) or 0), int(getattr(data, "m_Height", 0) or 0)
    rect = getattr(data, "m_Rect", None)
    if rect is not None:
        width = int(round(float(getattr(rect, "width", 0) or getattr(rect, "m_Width", 0) or 0)))
        height = int(round(float(getattr(rect, "height", 0) or getattr(rect, "m_Height", 0) or 0)))
        if width > 0 and height > 0:
            return width, height
    render_data = getattr(data, "m_RD", None)
    texture_rect = getattr(render_data, "textureRect", None) if render_data is not None else None
    if texture_rect is not None:
        width = int(round(float(getattr(texture_rect, "width", 0) or getattr(texture_rect, "m_Width", 0) or 0)))
        height = int(round(float(getattr(texture_rect, "height", 0) or getattr(texture_rect, "m_Height", 0) or 0)))
        if width > 0 and height > 0:
            return width, height
    return 0, 0


def build_row(
    *,
    bundle_path: Path,
    bundle_name: str,
    bundle_bytes: int,
    object_type: str,
    path_id: str,
    asset_name: str,
    image: Image.Image,
    min_size: int,
) -> ImageRow:
    width, height = image.size
    mean_luma, luma_stddev, visible_ratio = image_stats(image)
    return build_row_from_values(
        bundle_path=bundle_path,
        bundle_name=bundle_name,
        bundle_bytes=bundle_bytes,
        object_type=object_type,
        path_id=path_id,
        asset_name=asset_name,
        width=width,
        height=height,
        mode=image.mode,
        mean_luma=mean_luma,
        luma_stddev=luma_stddev,
        visible_ratio=visible_ratio,
        min_size=min_size,
    )


def build_row_from_values(
    *,
    bundle_path: Path,
    bundle_name: str,
    bundle_bytes: int,
    object_type: str,
    path_id: str,
    asset_name: str,
    width: int,
    height: int,
    mode: str,
    mean_luma: float,
    luma_stddev: float,
    visible_ratio: float,
    min_size: int,
    reject_reason_override: str = "",
) -> ImageRow:
    reject_reason = reject_reason_override or rejection_reason(
        asset_name=asset_name,
        bundle_name=bundle_name,
        width=width,
        height=height,
        mean_luma=mean_luma,
        luma_stddev=luma_stddev,
        visible_ratio=visible_ratio,
        min_size=min_size,
    )
    score = candidate_score(
        asset_name=asset_name,
        bundle_name=bundle_name,
        width=width,
        height=height,
        mean_luma=mean_luma,
        luma_stddev=luma_stddev,
        visible_ratio=visible_ratio,
        reject_reason=reject_reason,
    )
    return ImageRow(
        bundle=bundle_name,
        bundle_path=str(bundle_path),
        bundle_bytes=bundle_bytes,
        object_type=object_type,
        path_id=path_id,
        asset_name=asset_name,
        width=width,
        height=height,
        mode=mode,
        score=score,
        mean_luma=mean_luma,
        luma_stddev=luma_stddev,
        visible_ratio=visible_ratio,
        reject_reason=reject_reason,
    )


def image_stats(image: Image.Image) -> tuple[float, float, float]:
    sample = ImageOps.contain(image, (256, 256))
    alpha = None
    if "A" in sample.getbands():
        alpha = sample.getchannel("A")
        alpha_histogram = alpha.histogram()
        visible_ratio = sum(alpha_histogram[9:]) / float(alpha.width * alpha.height)
    else:
        visible_ratio = 1.0
    rgb = sample.convert("RGB")
    if alpha is not None:
        background = Image.new("RGB", sample.size, (0, 0, 0))
        background.paste(rgb, mask=alpha)
        rgb = background
    luma = rgb.convert("L")
    stat = ImageStat.Stat(luma)
    mean_luma = float(stat.mean[0])
    luma_stddev = float(stat.stddev[0])
    return mean_luma, luma_stddev, visible_ratio


def rejection_reason(
    *,
    asset_name: str,
    bundle_name: str,
    width: int,
    height: int,
    mean_luma: float,
    luma_stddev: float,
    visible_ratio: float,
    min_size: int,
) -> str:
    haystack = normalize_text(f"{asset_name} {Path(bundle_name).name}")
    if width < min_size or height < min_size:
        return "too_small"
    if visible_ratio < 0.08:
        return "mostly_transparent"
    if mean_luma < 12:
        return "quasi_black"
    if luma_stddev < 3:
        return "empty_or_flat"
    if "mapeffects" in haystack:
        return "effect_texture"
    if any(hint in haystack for hint in REJECT_NAME_HINTS):
        return "decorative_or_layer_hint"
    if visible_ratio < 0.35 and max(width, height) < 1024:
        return "isolated_layer"
    return ""


def candidate_score(
    *,
    asset_name: str,
    bundle_name: str,
    width: int,
    height: int,
    mean_luma: float,
    luma_stddev: float,
    visible_ratio: float,
    reject_reason: str,
) -> int:
    haystack = normalize_text(f"{asset_name} {bundle_name}")
    score = 0
    for keyword, weight in KEYWORD_WEIGHTS:
        if keyword in haystack:
            score += weight
    short_side = min(width, height)
    long_side = max(width, height)
    if short_side >= 1024:
        score += 28
    elif short_side >= 512:
        score += 18
    elif short_side >= 256:
        score += 8
    if long_side >= 2048:
        score += 18
    elif long_side >= 1024:
        score += 12
    ratio = long_side / max(1, short_side)
    if 0.85 <= ratio <= 1.25:
        score += 12
    elif ratio <= 4.0:
        score += 5
    if mean_luma >= 35 and luma_stddev >= 10:
        score += 8
    if visible_ratio >= 0.8:
        score += 5
    if reject_reason:
        score -= 60
    return score


def should_export(row: ImageRow, min_export_score: int) -> bool:
    return not row.reject_reason and not row.error and row.score >= min_export_score


def select_export_rows(rows: list[ImageRow], *, max_exports: int) -> list[ImageRow]:
    best_by_asset: dict[tuple[str, str], ImageRow] = {}
    for row in rows:
        key = (row.bundle, row.asset_name)
        current = best_by_asset.get(key)
        if current is None or export_rank(row) > export_rank(current):
            best_by_asset[key] = row
    selected = sorted(best_by_asset.values(), key=lambda row: export_rank(row), reverse=True)
    if max_exports > 0:
        selected = selected[:max_exports]
    return selected


def export_rank(row: ImageRow) -> tuple[int, int, int]:
    type_rank = 1 if row.object_type == "Texture2D" else 0
    return row.score, row.width * row.height, type_rank


def export_selected_images(rows: list[ImageRow], export_dir: Path) -> None:
    rows_by_bundle: dict[str, dict[str, ImageRow]] = {}
    for row in rows:
        rows_by_bundle.setdefault(row.bundle_path, {})[row.path_id] = row
    for bundle_path_text, rows_by_path_id in sorted(rows_by_bundle.items()):
        env = UnityPy.load(bundle_path_text)
        remaining = set(rows_by_path_id)
        for obj in env.objects:
            path_id = str(getattr(obj, "path_id", ""))
            row = rows_by_path_id.get(path_id)
            if row is None:
                continue
            try:
                data = obj.read()
                image = getattr(data, "image", None)
                if image is None:
                    raise ValueError("UnityPy returned no image")
                export_path = export_image(normalize_image(image), export_dir, row)
                row.exported_path = relative_to_root(export_path, ROOT_DIR)
            except Exception as exc:
                row.error = f"export_error: {type(exc).__name__}: {exc}"
            remaining.discard(path_id)
            if not remaining:
                break


def rewrite_csv_export_results(csv_path: Path, fieldnames: list[str], exported_rows: list[ImageRow]) -> None:
    updates = {
        (row.bundle, row.path_id): {"exported_path": row.exported_path, "error": row.error}
        for row in exported_rows
        if row.exported_path or row.error
    }
    if not updates:
        return
    temp_path = csv_path.with_name(f"{csv_path.stem}.tmp{csv_path.suffix}")
    with csv_path.open("r", newline="", encoding="utf-8") as source, temp_path.open(
        "w", newline="", encoding="utf-8"
    ) as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            update = updates.get((row.get("bundle", ""), row.get("path_id", "")))
            if update is not None:
                row.update(update)
            writer.writerow(row)
    temp_path.replace(csv_path)


def export_image(image: Image.Image, export_dir: Path, row: ImageRow) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{row.bundle}|{row.object_type}|{row.path_id}|{row.asset_name}".encode("utf-8")).hexdigest()[:10]
    filename = (
        f"{row.score:04d}_{safe_filename(Path(row.bundle).stem)}_"
        f"{safe_filename(row.object_type)}_{safe_filename(row.asset_name)}_{digest}.png"
    )
    path = export_dir / filename
    image.save(path, "PNG", compress_level=1)
    return path


def clean_export_dir(export_dir: Path, output_dir: Path) -> None:
    resolved_export = export_dir.resolve()
    resolved_output = output_dir.resolve()
    if resolved_output not in resolved_export.parents and resolved_export != resolved_output:
        raise SystemExit(f"Refusing to clean exports outside output dir: {resolved_export}")
    for path in export_dir.glob("*.png"):
        path.unlink()


def make_preview_sheet(rows: list[ImageRow], sheet_path: Path, *, limit: int) -> None:
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda row: (-row.score, -row.width * row.height, row.bundle, row.asset_name))[:limit]
    card_w, card_h = 420, 290
    thumb_h = 185
    cols = 3
    rows_count = max(1, (len(rows) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * card_w, rows_count * card_h), (245, 245, 242))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    if not rows:
        draw.text((18, 18), "No exported bundle candidates matched the scan filters.", fill=(20, 20, 20), font=font)
        sheet.save(sheet_path, "JPEG", quality=90)
        return

    for index, row in enumerate(rows):
        x = (index % cols) * card_w
        y = (index // cols) * card_h
        draw.rectangle((x + 6, y + 6, x + card_w - 6, y + card_h - 6), fill=(255, 255, 255), outline=(205, 205, 200))
        image_path = ROOT_DIR / row.exported_path
        try:
            thumb = Image.open(image_path).convert("RGB")
            thumb.thumbnail((card_w - 24, thumb_h), Image.Resampling.LANCZOS)
            tx = x + (card_w - thumb.width) // 2
            ty = y + 14 + (thumb_h - thumb.height) // 2
            sheet.paste(thumb, (tx, ty))
        except OSError:
            draw.text((x + 14, y + 24), "preview unavailable", fill=(160, 20, 20), font=font)
        label_y = y + thumb_h + 22
        label_lines = [
            f"asset: {row.asset_name}",
            f"bundle: {Path(row.bundle).name}",
            f"size: {row.width}x{row.height}",
            f"score: {row.score}",
        ]
        for line in label_lines:
            for wrapped in wrap_ascii(line, 58):
                draw.text((x + 14, label_y), wrapped, fill=(20, 20, 20), font=font)
                label_y += 14
    sheet.save(sheet_path, "JPEG", quality=90, optimize=True)


def safe_filename(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[^a-z0-9._-]+", "_", value).strip("._-")
    return value[:80] or "asset"


def normalize_text(value: str) -> str:
    return value.replace("\\", "/").casefold()


def wrap_ascii(text: str, width: int) -> Iterable[str]:
    text = text.encode("ascii", "replace").decode("ascii")
    while len(text) > width:
        split_at = text.rfind(" ", 0, width)
        if split_at <= 0:
            split_at = width
        yield text[:split_at]
        text = text[split_at:].lstrip()
    yield text


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
