from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import os
import re
import shutil
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
UNITYPY_VENDOR = ROOT_DIR / ".codex_deps" / "unitypy"
if UNITYPY_VENDOR.exists():
    sys.path.insert(0, str(UNITYPY_VENDOR))

try:
    import UnityPy  # type: ignore
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat
    from UnityPy import config as unitypy_config  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install it with:\n"
        "  py -m pip install UnityPy pillow\n"
        "or vendor it in .codex_deps/unitypy."
    ) from exc


LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
DEFAULT_STREAMING_ASSETS = LOCAL_APP_DATA / "Ankama" / "Dofus-dofus3" / "Dofus_Data" / "StreamingAssets"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "reports" / "dofus_worldmap_scan"
EXPORT_DIR_NAME = "exports"
PREVIEW_DIR_NAME = "previews"
CATALOG_CSV_NAME = "catalog_worldmap_hits.csv"
TEXT_BUNDLE_REFS_NAME = "catalog_bundle_refs.txt"
TEXTURE_CSV_NAME = "worldmap_texture_candidates.csv"
SHEET_BASENAME = "worldmap_candidates_sheet"

DEFAULT_FALLBACK_UNITY_VERSION = "6000.0.0f1"
IMAGE_TYPES = {"Texture2D", "Sprite"}

DEFAULT_EXCLUDE_DIRS = (
    Path("Content") / "Map",
)

TEXT_EXTENSIONS = {
    "",
    ".json",
    ".txt",
    ".xml",
    ".csv",
    ".hash",
    ".manifest",
    ".config",
    ".ini",
}

TEXT_NAME_HINTS = (
    "catalog",
    "addressable",
    "settings",
    "resource",
)

SEARCH_TERMS = (
    "amakna",
    "incarnam",
    "enutrosor",
    "enurado",
    "srambad",
    "xelorium",
    "ecaflipus",
    "worldmaps",
    "worldmap",
    "world_map",
    "world-map",
    "cartography",
    "picto/worldmaps",
    "picto\\worldmaps",
    "breachworldmap",
    "worldmapsdata",
)

KEYWORD_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("picto/worldmaps", 340),
    ("picto\\worldmaps", 340),
    ("worldmaps", 260),
    ("worldmap", 250),
    ("world_map", 250),
    ("world-map", 250),
    ("breachworldmap", 190),
    ("worldmapsdata", 180),
    ("cartography", 170),
    ("amakna", 360),
    ("incarnam", 340),
    ("enutrosor", 380),
    ("enurado", 320),
    ("srambad", 340),
    ("xelorium", 340),
    ("ecaflipus", 340),
    ("world_16", 130),
    ("world-16", 130),
    ("world 16", 130),
    ("world_15", 130),
    ("world-15", 130),
    ("world 15", 130),
    ("world_14", 130),
    ("world-14", 130),
    ("world 14", 130),
    ("world_13", 120),
    ("world-13", 120),
    ("world 13", 120),
    ("world_2", 110),
    ("world-2", 110),
    ("world 2", 110),
    ("world_1", 100),
    ("world-1", 100),
    ("world 1", 100),
    ("world", 55),
)

REJECT_NAME_HINTS = (
    "achievement",
    "button",
    "cursor",
    "emote",
    "frame",
    "icon",
    "marker",
    "mask",
    "monster",
    "ornament",
    "particle",
    "pin",
    "scroll",
    "shadow",
    "spell",
    "tooltip",
)

PROMOTION_TARGETS = {
    "amakna": ROOT_DIR / "data" / "cartography" / "assets" / "world" / "amakna" / "world.png",
    "incarnam": ROOT_DIR / "data" / "cartography" / "assets" / "world" / "incarnam" / "world.png",
    "enutrosor": ROOT_DIR / "data" / "cartography" / "assets" / "world" / "enutrosor" / "world.png",
    "srambad": ROOT_DIR / "data" / "cartography" / "assets" / "world" / "srambad" / "world.png",
    "xelorium": ROOT_DIR / "data" / "cartography" / "assets" / "world" / "xelorium" / "world.png",
    "ecaflipus": ROOT_DIR / "data" / "cartography" / "assets" / "world" / "ecaflipus" / "world.png",
}

BUNDLE_REF_RE = re.compile(rb"([A-Za-z0-9_./\\ -]{1,220}\.bundle)", re.IGNORECASE)


@dataclass(slots=True)
class CatalogHit:
    file: str
    file_path: str
    file_bytes: int
    matched_terms: str
    bundle_refs: str
    snippet: str
    error: str = ""

    def to_csv_row(self) -> dict[str, object]:
        return {
            "file": self.file,
            "file_path": self.file_path,
            "file_bytes": self.file_bytes,
            "matched_terms": self.matched_terms,
            "bundle_refs": self.bundle_refs,
            "snippet": self.snippet,
            "error": self.error,
        }


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
    parser = argparse.ArgumentParser(
        description="Find Dofus 3 / Unity worldmap image candidates outside Content/Map."
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan catalogs and Unity bundles for worldmap candidates.")
    add_scan_args(scan_parser)

    promote_parser = subparsers.add_parser("promote", help="Manually promote a visually validated PNG candidate.")
    promote_parser.add_argument("--world", choices=sorted(PROMOTION_TARGETS), required=True)
    promote_parser.add_argument("--candidate", type=Path, required=True, help="Validated PNG candidate to copy.")
    promote_parser.add_argument("--confirm", action="store_true", help="Required to actually copy the file.")
    promote_parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing world.png.")

    args = parser.parse_args()
    if args.command == "promote":
        return promote_candidate(args)
    if args.command in {None, "scan"}:
        return scan(args)
    parser.error("Unknown command")
    return 2


def add_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--streaming-assets", type=Path, default=DEFAULT_STREAMING_ASSETS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--include-map", action="store_true", help="Do not exclude Content/Map.")
    parser.add_argument("--catalog-only", action="store_true", help="Only scan catalogs/text files.")
    parser.add_argument("--bundle-only", action="store_true", help="Only scan Unity bundles.")
    parser.add_argument("--bundle-name-filter", default="", help="Case-insensitive substring filter for bundles.")
    parser.add_argument("--limit-bundles", type=int, default=0, help="Diagnostic bundle limit after filtering.")
    parser.add_argument("--text-max-mb", type=int, default=25, help="Max text/catalog file size to inspect.")
    parser.add_argument("--min-width", type=int, default=1024)
    parser.add_argument("--min-height", type=int, default=768)
    parser.add_argument("--min-area", type=int, default=1_000_000)
    parser.add_argument("--min-score", type=int, default=90)
    parser.add_argument("--max-exports", type=int, default=240, help="Max top-ranked PNG candidates to export.")
    parser.add_argument("--preview-limit", type=int, default=120)
    parser.add_argument("--preview-per-sheet", type=int, default=24)
    parser.add_argument("--max-decode-bundle-mb", type=int, default=900, help="0 means decode all bundle sizes.")
    parser.add_argument("--fallback-unity-version", default=DEFAULT_FALLBACK_UNITY_VERSION)
    parser.add_argument("--clean", action="store_true", help="Remove old exports/previews before scanning.")


def scan(args: argparse.Namespace) -> int:
    streaming_assets = args.streaming_assets
    if not streaming_assets.exists() or not streaming_assets.is_dir():
        raise SystemExit(f"StreamingAssets directory not found: {streaming_assets}")

    output_dir = args.output_dir
    export_dir = output_dir / EXPORT_DIR_NAME
    preview_dir = output_dir / PREVIEW_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    if args.clean:
        clean_generated_outputs(export_dir, preview_dir)

    unitypy_config.FALLBACK_UNITY_VERSION = args.fallback_unity_version
    warnings.filterwarnings("ignore", message="No valid Unity version found.*")

    excluded_dirs = () if args.include_map else DEFAULT_EXCLUDE_DIRS
    catalog_bundle_refs: set[str] = set()
    if not args.bundle_only:
        catalog_hits = scan_catalogs(
            streaming_assets=streaming_assets,
            output_dir=output_dir,
            excluded_dirs=excluded_dirs,
            text_max_mb=args.text_max_mb,
        )
        for hit in catalog_hits:
            for ref in hit.bundle_refs.split(";"):
                ref = ref.strip()
                if ref:
                    catalog_bundle_refs.add(normalize_text(ref))
        write_bundle_refs(output_dir / TEXT_BUNDLE_REFS_NAME, catalog_bundle_refs)
    else:
        catalog_hits = []

    if args.catalog_only:
        print(f"catalog_hits={len(catalog_hits)}")
        print(f"catalog_csv={output_dir / CATALOG_CSV_NAME}")
        return 0

    stats = scan_bundles(
        streaming_assets=streaming_assets,
        output_dir=output_dir,
        export_dir=export_dir,
        preview_dir=preview_dir,
        excluded_dirs=excluded_dirs,
        catalog_bundle_refs=catalog_bundle_refs,
        args=args,
    )
    print(f"catalog_hits={len(catalog_hits)}")
    print(f"bundles_seen={stats['bundles_seen']}")
    print(f"images_seen={stats['images_seen']}")
    print(f"candidate_rows={stats['candidate_rows']}")
    print(f"exported_candidates={stats['exported_candidates']}")
    print(f"image_errors={stats['image_errors']}")
    print(f"bundle_errors={stats['bundle_errors']}")
    print(f"catalog_csv={output_dir / CATALOG_CSV_NAME}")
    print(f"texture_csv={output_dir / TEXTURE_CSV_NAME}")
    print(f"exports={export_dir}")
    print(f"previews={preview_dir}")
    return 0


def scan_catalogs(
    *,
    streaming_assets: Path,
    output_dir: Path,
    excluded_dirs: tuple[Path, ...],
    text_max_mb: int,
) -> list[CatalogHit]:
    csv_path = output_dir / CATALOG_CSV_NAME
    fieldnames = list(CatalogHit("", "", 0, "", "", "").to_csv_row().keys())
    hits: list[CatalogHit] = []
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for path in sorted(streaming_assets.rglob("*"), key=lambda item: str(item).casefold()):
            if not path.is_file() or is_excluded(path, streaming_assets, excluded_dirs):
                continue
            if not is_catalog_or_text_file(path):
                continue
            if safe_size(path) > text_max_mb * 1024 * 1024:
                continue
            hit = inspect_text_file(path, streaming_assets)
            if hit is None:
                continue
            hits.append(hit)
            writer.writerow(hit.to_csv_row())
    return hits


def is_catalog_or_text_file(path: Path) -> bool:
    name = path.name.casefold()
    if path.suffix.casefold() in TEXT_EXTENSIONS:
        return True
    return any(hint in name for hint in TEXT_NAME_HINTS)


def inspect_text_file(path: Path, root: Path) -> CatalogHit | None:
    rel = relative_to(path, root)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return CatalogHit(rel, str(path), safe_size(path), "", "", "", error=f"{type(exc).__name__}: {exc}")
    lowered = raw.casefold() if isinstance(raw, str) else raw.lower()
    matched = [term for term in SEARCH_TERMS if term.encode("utf-8", "ignore").lower() in lowered]
    bundle_refs = sorted(set(extract_bundle_refs(raw)))
    if not matched and not any("worldmap" in ref.casefold() for ref in bundle_refs):
        return None
    snippet = make_snippet(raw, matched)
    return CatalogHit(
        file=rel,
        file_path=str(path),
        file_bytes=len(raw),
        matched_terms=";".join(matched),
        bundle_refs=";".join(bundle_refs[:80]),
        snippet=snippet,
    )


def extract_bundle_refs(raw: bytes) -> list[str]:
    refs: list[str] = []
    for match in BUNDLE_REF_RE.finditer(raw):
        value = match.group(1).decode("utf-8", "ignore").strip("\x00 \t\r\n")
        if value:
            refs.append(value.replace("\\", "/"))
    return refs


def make_snippet(raw: bytes, matched_terms: list[str]) -> str:
    lowered = raw.lower()
    first = -1
    for term in matched_terms:
        idx = lowered.find(term.encode("utf-8", "ignore").lower())
        if idx >= 0 and (first < 0 or idx < first):
            first = idx
    if first < 0:
        first = 0
    start = max(0, first - 120)
    end = min(len(raw), first + 280)
    text = raw[start:end].decode("utf-8", "replace")
    text = re.sub(r"\s+", " ", text)
    return text[:500]


def scan_bundles(
    *,
    streaming_assets: Path,
    output_dir: Path,
    export_dir: Path,
    preview_dir: Path,
    excluded_dirs: tuple[Path, ...],
    catalog_bundle_refs: set[str],
    args: argparse.Namespace,
) -> dict[str, int]:
    csv_path = output_dir / TEXTURE_CSV_NAME
    fieldnames = list(ImageRow("", "", 0, "", "", "").to_csv_row().keys())
    bundle_paths = sorted(streaming_assets.rglob("*.bundle"), key=lambda item: str(item).casefold())
    bundle_paths = [path for path in bundle_paths if not is_excluded(path, streaming_assets, excluded_dirs)]
    if args.bundle_name_filter:
        needle = args.bundle_name_filter.casefold()
        bundle_paths = [path for path in bundle_paths if needle in str(path).casefold()]
    if args.limit_bundles > 0:
        bundle_paths = bundle_paths[: args.limit_bundles]

    candidate_rows: list[ImageRow] = []
    images_seen = 0
    image_errors = 0
    bundle_errors = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, bundle_path in enumerate(bundle_paths, start=1):
            rel_bundle = relative_to(bundle_path, streaming_assets)
            if index == 1 or index % 100 == 0 or is_priority_bundle(rel_bundle):
                print(f"[{index}/{len(bundle_paths)}] {rel_bundle}", flush=True)
            metadata_only = (
                args.max_decode_bundle_mb > 0
                and safe_size(bundle_path) > args.max_decode_bundle_mb * 1024 * 1024
            )
            try:
                rows = scan_bundle(
                    bundle_path=bundle_path,
                    streaming_assets=streaming_assets,
                    catalog_bundle_refs=catalog_bundle_refs,
                    min_width=args.min_width,
                    min_height=args.min_height,
                    min_area=args.min_area,
                    metadata_only=metadata_only,
                )
            except Exception as exc:
                bundle_errors += 1
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
                images_seen += 1
                if row.error:
                    image_errors += 1
                if should_export(row, args.min_score):
                    candidate_rows.append(row)
                writer.writerow(row.to_csv_row())
            if index % 25 == 0:
                handle.flush()
            del rows
            gc.collect()

    selected_rows = select_export_rows(candidate_rows, max_exports=args.max_exports)
    export_selected_images(selected_rows, export_dir)
    rewrite_csv_export_results(csv_path, fieldnames, selected_rows)
    make_preview_sheets(selected_rows, preview_dir, limit=args.preview_limit, per_sheet=args.preview_per_sheet)
    return {
        "bundles_seen": len(bundle_paths),
        "images_seen": images_seen,
        "candidate_rows": len(candidate_rows),
        "exported_candidates": sum(1 for row in selected_rows if row.exported_path),
        "image_errors": image_errors,
        "bundle_errors": bundle_errors,
    }


def scan_bundle(
    *,
    bundle_path: Path,
    streaming_assets: Path,
    catalog_bundle_refs: set[str],
    min_width: int,
    min_height: int,
    min_area: int,
    metadata_only: bool,
) -> list[ImageRow]:
    rel_bundle = relative_to(bundle_path, streaming_assets)
    bundle_bytes = safe_size(bundle_path)
    env = UnityPy.load(str(bundle_path))
    rows: list[ImageRow] = []
    for obj in env.objects:
        object_type = getattr(obj.type, "name", str(obj.type))
        if object_type not in IMAGE_TYPES:
            continue
        path_id = str(getattr(obj, "path_id", ""))
        try:
            data = obj.read()
            asset_name = str(getattr(data, "name", "") or getattr(data, "m_Name", "") or path_id)
            width, height = image_dimensions(data, object_type)
            if metadata_only:
                rows.append(
                    build_row_from_values(
                        bundle_path=bundle_path,
                        bundle_name=rel_bundle,
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
                        min_width=min_width,
                        min_height=min_height,
                        min_area=min_area,
                        catalog_bundle_refs=catalog_bundle_refs,
                        reject_reason_override="metadata_only_large_bundle",
                    )
                )
                continue
            if width > 0 and height > 0 and (width < min_width or height < min_height or width * height < min_area):
                rows.append(
                    build_row_from_values(
                        bundle_path=bundle_path,
                        bundle_name=rel_bundle,
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
                        min_width=min_width,
                        min_height=min_height,
                        min_area=min_area,
                        catalog_bundle_refs=catalog_bundle_refs,
                    )
                )
                continue
            image = getattr(data, "image", None)
            if image is None:
                raise ValueError("UnityPy returned no image")
            image = normalize_image(image)
            rows.append(
                build_row(
                    bundle_path=bundle_path,
                    bundle_name=rel_bundle,
                    bundle_bytes=bundle_bytes,
                    object_type=object_type,
                    path_id=path_id,
                    asset_name=asset_name,
                    image=image,
                    min_width=min_width,
                    min_height=min_height,
                    min_area=min_area,
                    catalog_bundle_refs=catalog_bundle_refs,
                )
            )
        except Exception as exc:
            rows.append(
                ImageRow(
                    bundle=rel_bundle,
                    bundle_path=str(bundle_path),
                    bundle_bytes=bundle_bytes,
                    object_type=object_type,
                    path_id=path_id,
                    asset_name="",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return rows


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


def normalize_image(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "RGB"}:
        return image.copy()
    if "A" in image.getbands():
        return image.convert("RGBA")
    return image.convert("RGB")


def build_row(
    *,
    bundle_path: Path,
    bundle_name: str,
    bundle_bytes: int,
    object_type: str,
    path_id: str,
    asset_name: str,
    image: Image.Image,
    min_width: int,
    min_height: int,
    min_area: int,
    catalog_bundle_refs: set[str],
) -> ImageRow:
    mean_luma, luma_stddev, visible_ratio = image_stats(image)
    return build_row_from_values(
        bundle_path=bundle_path,
        bundle_name=bundle_name,
        bundle_bytes=bundle_bytes,
        object_type=object_type,
        path_id=path_id,
        asset_name=asset_name,
        width=image.width,
        height=image.height,
        mode=image.mode,
        mean_luma=mean_luma,
        luma_stddev=luma_stddev,
        visible_ratio=visible_ratio,
        min_width=min_width,
        min_height=min_height,
        min_area=min_area,
        catalog_bundle_refs=catalog_bundle_refs,
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
    min_width: int,
    min_height: int,
    min_area: int,
    catalog_bundle_refs: set[str],
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
        min_width=min_width,
        min_height=min_height,
        min_area=min_area,
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
        catalog_bundle_refs=catalog_bundle_refs,
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
    sample = ImageOps.contain(image, (320, 320))
    alpha = None
    if "A" in sample.getbands():
        alpha = sample.getchannel("A")
        hist = alpha.histogram()
        visible_ratio = sum(hist[9:]) / float(alpha.width * alpha.height)
    else:
        visible_ratio = 1.0
    rgb = sample.convert("RGB")
    if alpha is not None:
        background = Image.new("RGB", sample.size, (0, 0, 0))
        background.paste(rgb, mask=alpha)
        rgb = background
    stat = ImageStat.Stat(rgb.convert("L"))
    return float(stat.mean[0]), float(stat.stddev[0]), visible_ratio


def rejection_reason(
    *,
    asset_name: str,
    bundle_name: str,
    width: int,
    height: int,
    mean_luma: float,
    luma_stddev: float,
    visible_ratio: float,
    min_width: int,
    min_height: int,
    min_area: int,
) -> str:
    haystack = normalize_text(f"{asset_name} {bundle_name}")
    worldish = any(term in haystack for term in ("worldmap", "worldmaps", "world_map", "cartography", "picto/worldmaps"))
    if width < min_width or height < min_height:
        return "too_small"
    if width * height < min_area:
        return "area_too_small"
    if visible_ratio < 0.06:
        return "mostly_transparent"
    if mean_luma < 10:
        return "quasi_black"
    if luma_stddev < 3:
        return "empty_or_flat"
    if any(hint in haystack for hint in REJECT_NAME_HINTS) and not worldish:
        return "ui_or_decorative_hint"
    if visible_ratio < 0.25 and not worldish:
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
    catalog_bundle_refs: set[str],
) -> int:
    haystack = normalize_text(f"{asset_name} {bundle_name}")
    score = 0
    for keyword, weight in KEYWORD_WEIGHTS:
        if keyword in haystack:
            score += weight
    bundle_leaf = normalize_text(Path(bundle_name).name)
    if bundle_leaf in catalog_bundle_refs or any(bundle_leaf in ref for ref in catalog_bundle_refs):
        score += 120
    if asset_name.strip().casefold() in {"1", "13"}:
        score += 80
    area = width * height
    short_side = min(width, height)
    long_side = max(width, height)
    if short_side >= 4096:
        score += 90
    elif short_side >= 2048:
        score += 70
    elif short_side >= 1024:
        score += 40
    if area >= 30_000_000:
        score += 70
    elif area >= 10_000_000:
        score += 55
    elif area >= 3_000_000:
        score += 35
    ratio = long_side / max(1, short_side)
    if 0.75 <= ratio <= 2.4:
        score += 25
    elif ratio <= 4.0:
        score += 10
    if 25 <= mean_luma <= 235 and luma_stddev >= 10:
        score += 15
    if visible_ratio >= 0.75:
        score += 20
    elif visible_ratio >= 0.35:
        score += 10
    if reject_reason:
        score -= 100
    return score


def should_export(row: ImageRow, min_score: int) -> bool:
    return not row.reject_reason and not row.error and row.score >= min_score


def select_export_rows(rows: list[ImageRow], *, max_exports: int) -> list[ImageRow]:
    best_by_key: dict[tuple[str, str, int, int], ImageRow] = {}
    for row in rows:
        key = (row.bundle, row.asset_name, row.width, row.height)
        current = best_by_key.get(key)
        if current is None or export_rank(row) > export_rank(current):
            best_by_key[key] = row
    selected = sorted(best_by_key.values(), key=export_rank, reverse=True)
    if max_exports > 0:
        selected = selected[:max_exports]
    return selected


def export_rank(row: ImageRow) -> tuple[int, int, int]:
    sprite_bonus = 1 if row.object_type == "Sprite" else 0
    return row.score, row.width * row.height, sprite_bonus


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
                row.exported_path = relative_to(export_path, ROOT_DIR)
            except Exception as exc:
                row.error = f"export_error: {type(exc).__name__}: {exc}"
            remaining.discard(path_id)
            if not remaining:
                break
        gc.collect()


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


def make_preview_sheets(rows: list[ImageRow], preview_dir: Path, *, limit: int, per_sheet: int) -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    rows = [row for row in rows if row.exported_path]
    rows = sorted(rows, key=export_rank, reverse=True)[:limit]
    for old in preview_dir.glob(f"{SHEET_BASENAME}_*.jpg"):
        old.unlink()
    alias_path = preview_dir / f"{SHEET_BASENAME}.jpg"
    if alias_path.exists():
        alias_path.unlink()
    if not rows:
        sheet = Image.new("RGB", (900, 240), (245, 245, 242))
        draw = ImageDraw.Draw(sheet)
        draw.text((20, 20), "No exported worldmap candidates.", fill=(20, 20, 20), font=load_font(16))
        sheet.save(alias_path, "JPEG", quality=90)
        return
    for sheet_index, start in enumerate(range(0, len(rows), per_sheet), start=1):
        chunk = rows[start : start + per_sheet]
        sheet_path = preview_dir / f"{SHEET_BASENAME}_{sheet_index:03d}.jpg"
        render_preview_sheet(chunk, sheet_path)
        if sheet_index == 1:
            shutil.copy2(sheet_path, alias_path)


def render_preview_sheet(rows: list[ImageRow], sheet_path: Path) -> None:
    card_w, card_h = 460, 330
    thumb_h = 205
    cols = 3
    sheet_rows = max(1, (len(rows) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * card_w, sheet_rows * card_h), (244, 244, 241))
    draw = ImageDraw.Draw(sheet)
    font = load_font(13)
    title_font = load_font(14, bold=True)
    for index, row in enumerate(rows):
        x = (index % cols) * card_w
        y = (index // cols) * card_h
        draw.rectangle((x + 8, y + 8, x + card_w - 8, y + card_h - 8), fill=(255, 255, 255), outline=(198, 198, 192))
        image_path = ROOT_DIR / row.exported_path
        try:
            thumb = Image.open(image_path).convert("RGB")
            thumb.thumbnail((card_w - 26, thumb_h), Image.Resampling.LANCZOS)
            tx = x + (card_w - thumb.width) // 2
            ty = y + 14 + (thumb_h - thumb.height) // 2
            sheet.paste(thumb, (tx, ty))
        except OSError:
            draw.text((x + 18, y + 28), "preview unavailable", fill=(160, 20, 20), font=font)
        label_y = y + thumb_h + 24
        label_lines = [
            f"score {row.score} | {row.width}x{row.height} | {row.object_type}",
            f"asset: {row.asset_name}",
            f"bundle: {Path(row.bundle).name}",
        ]
        for line_index, line in enumerate(label_lines):
            current_font = title_font if line_index == 0 else font
            for wrapped in wrap_ascii(line, 62):
                draw.text((x + 16, label_y), wrapped, fill=(18, 18, 18), font=current_font)
                label_y += 17
    sheet.save(sheet_path, "JPEG", quality=90, optimize=True)


def promote_candidate(args: argparse.Namespace) -> int:
    source = args.candidate
    if not source.is_absolute():
        source = ROOT_DIR / source
    source = source.resolve()
    target = PROMOTION_TARGETS[args.world]
    if not source.exists() or not source.is_file():
        raise SystemExit(f"Candidate PNG not found: {source}")
    try:
        with Image.open(source) as image:
            width, height = image.size
            mode = image.mode
    except OSError as exc:
        raise SystemExit(f"Candidate is not a readable image: {source} ({exc})") from exc
    if target.exists() and not args.overwrite:
        raise SystemExit(f"Target already exists. Add --overwrite if this is intentional: {target}")
    print(f"candidate={source}")
    print(f"image={width}x{height} {mode}")
    print(f"target={target}")
    if not args.confirm:
        print("dry_run=true")
        print("Add --confirm to copy this validated PNG.")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"promoted={target}")
    return 0


def clean_generated_outputs(export_dir: Path, preview_dir: Path) -> None:
    assert_under_root(export_dir)
    assert_under_root(preview_dir)
    for path in export_dir.glob("*.png"):
        path.unlink()
    for path in preview_dir.glob("*.jpg"):
        path.unlink()


def write_bundle_refs(path: Path, refs: set[str]) -> None:
    path.write_text("\n".join(sorted(refs)) + ("\n" if refs else ""), encoding="utf-8")


def is_priority_bundle(rel_bundle: str) -> bool:
    haystack = normalize_text(rel_bundle)
    return any(
        term in haystack
        for term in (
            "worldmap",
            "picto/worldmaps",
            "cartography",
            "amakna",
            "incarnam",
            "enutrosor",
            "srambad",
            "xelorium",
            "ecaflipus",
        )
    )


def is_excluded(path: Path, root: Path, excluded_dirs: tuple[Path, ...]) -> bool:
    rel = normalize_text(relative_to(path, root))
    for excluded in excluded_dirs:
        excluded_text = normalize_text(str(excluded))
        if rel == excluded_text or rel.startswith(excluded_text.rstrip("/") + "/"):
            return True
    return False


def safe_filename(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[^a-z0-9._-]+", "_", value).strip("._-")
    return value[:90] or "asset"


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


def relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def assert_under_root(path: Path) -> None:
    resolved = path.resolve()
    root = ROOT_DIR.resolve()
    if resolved != root and root not in resolved.parents:
        raise SystemExit(f"Refusing to clean outside workspace: {resolved}")


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())
