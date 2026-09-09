from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "data" / "reports" / "dofus_worldmap_scan"
PROMOTE_MAIN = {10, 12, 13, 14, 15, 18, 21, 28, 35, 38, 41}
PROMOTE_DODUDA = {2, 40}
VISUAL_COMPLETE_CURRENT = {3, 33}
STILL_INCOMPLETE = {1, 16, 34, 37}


def main() -> int:
    manifest_path = ROOT_DIR / "data" / "cartography" / "map_views.json"
    catalog_path = ROOT_DIR / "data" / "cartography" / "worldmap_catalog.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_id = {int(view.get("worldmap_id") or 0): view for view in manifest["views"]}
    catalog_by_id = {int(row.get("worldmap_id") or 0): row for row in catalog}

    matches_main = load_matches(REPORT_DIR / "repair_candidate_matches.json")
    matches_doduda = load_matches(REPORT_DIR / "repair_candidate_matches_doduda_unresolved.json")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = REPORT_DIR / "promoted_backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    promotions: list[dict[str, object]] = []

    for worldmap_id in sorted(PROMOTE_MAIN | PROMOTE_DODUDA):
        view = by_id[worldmap_id]
        source_record = (matches_doduda if worldmap_id in PROMOTE_DODUDA else matches_main)[worldmap_id]
        candidate = source_record["top_candidates"][0]
        source = ROOT_DIR / str(candidate["exported_path"])
        target = ROOT_DIR / view["asset_path"]
        backup = backup_dir / f"{worldmap_id:02d}_{target.parent.name}_world.png"
        if target.exists():
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        width, height = image_size(target)
        entry = {
            "worldmap_id": worldmap_id,
            "view_key": view["view_key"],
            "name": view["name"],
            "source": relative(source),
            "target": relative(target),
            "backup": relative(backup),
            "promoted_size": [width, height],
            "match_score": candidate.get("score"),
        }
        promotions.append(entry)
        mark_view(view, "client_overview_complete", entry)
        mark_catalog(catalog_by_id.get(worldmap_id), "client_overview_complete", entry)

    for worldmap_id in sorted(VISUAL_COMPLETE_CURRENT):
        view = by_id.get(worldmap_id)
        if not view:
            continue
        entry = {
            "worldmap_id": worldmap_id,
            "view_key": view["view_key"],
            "name": view["name"],
            "source": view["asset_path"],
            "target": view["asset_path"],
            "backup": "",
            "promoted_size": list(image_size(ROOT_DIR / view["asset_path"])),
            "match_score": None,
            "note": "Current asset visually usable; no better replacement promoted.",
        }
        mark_view(view, "client_visual_complete", entry)
        mark_catalog(catalog_by_id.get(worldmap_id), "client_visual_complete", entry)

    for worldmap_id in sorted(STILL_INCOMPLETE):
        view = by_id.get(worldmap_id)
        if not view:
            continue
        entry = {
            "worldmap_id": worldmap_id,
            "view_key": view["view_key"],
            "name": view["name"],
            "source": view["asset_path"],
            "target": view["asset_path"],
            "backup": "",
            "promoted_size": list(image_size(ROOT_DIR / view["asset_path"])),
            "match_score": None,
            "note": "No valid complete Dofus 3 worldmap found in StreamingAssets Worldmaps bundle or doduda cache; available candidates are fragments/background/layers.",
        }
        mark_view(view, "incomplete_no_valid_replacement", entry)
        mark_catalog(catalog_by_id.get(worldmap_id), "incomplete_no_valid_replacement", entry)

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = REPORT_DIR / "promoted_verified_worldmaps.json"
    report_path.write_text(json.dumps(promotions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_final_sheet(manifest, REPORT_DIR / "promoted_verified_worldmaps_sheet.jpg")
    print(f"promoted={len(promotions)}")
    print(f"report={report_path}")
    print(f"sheet={REPORT_DIR / 'promoted_verified_worldmaps_sheet.jpg'}")
    print(f"backup_dir={backup_dir}")
    return 0


def load_matches(path: Path) -> dict[int, dict[str, object]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {int(row["worldmap_id"]): row for row in rows}


def mark_view(view: dict[str, object], status: str, entry: dict[str, object]) -> None:
    view["asset_status"] = status
    source_tiles = dict(view.get("source_tiles") or {})
    source_tiles.update(
        {
            "source": "Dofus 3 client worldmap assets",
            "client_status_note": status_note(status),
            "visual_validation": "validated_by_preview_sheet_2026-07-09",
            "promoted_source": entry["source"],
            "promoted_size": entry["promoted_size"],
            "previous_asset_backup": entry.get("backup", ""),
        }
    )
    view["source_tiles"] = source_tiles


def mark_catalog(row: dict[str, object] | None, status: str, entry: dict[str, object]) -> None:
    if row is None:
        return
    row["status"] = status
    row["source_note"] = status_note(status)
    row["promoted_source"] = entry["source"]
    row["promoted_size"] = entry["promoted_size"]
    row["previous_asset_backup"] = entry.get("backup", "")
    row["final_size"] = entry["promoted_size"]
    target = ROOT_DIR / str(entry["target"])
    if target.exists():
        row["bytes"] = target.stat().st_size


def status_note(status: str) -> str:
    if status == "client_overview_complete":
        return "visually validated complete Dofus 3 overview promoted; replaces partial tile mosaic"
    if status == "client_visual_complete":
        return "current Dofus 3 asset visually usable; no better replacement promoted"
    if status == "incomplete_no_valid_replacement":
        return "incomplete: no valid complete Dofus 3 worldmap replacement found; only fragments/background/layers available"
    return status


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)


def render_final_sheet(manifest: dict[str, object], path: Path) -> None:
    target_ids = sorted(PROMOTE_MAIN | PROMOTE_DODUDA | VISUAL_COMPLETE_CURRENT | STILL_INCOMPLETE)
    views = {
        int(view.get("worldmap_id") or 0): view
        for view in manifest["views"]
        if int(view.get("worldmap_id") or 0) in target_ids
    }
    card_w, card_h = 360, 290
    cols = 3
    rows = (len(target_ids) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * card_w, rows * card_h), (244, 244, 240))
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(13, bold=True)
    font = load_font(11)
    for index, worldmap_id in enumerate(target_ids):
        view = views[worldmap_id]
        x = (index % cols) * card_w
        y = (index // cols) * card_h
        draw.rectangle((x + 6, y + 6, x + card_w - 6, y + card_h - 6), fill=(255, 255, 255), outline=(198, 198, 192))
        image_path = ROOT_DIR / str(view["asset_path"])
        image = Image.open(image_path).convert("RGB")
        image.thumbnail((card_w - 22, 195), Image.Resampling.LANCZOS)
        sheet.paste(image, (x + (card_w - image.width) // 2, y + 12))
        draw.text((x + 12, y + 214), f"{worldmap_id:02d} {view['name']}"[:48], fill=(10, 10, 10), font=title_font)
        draw.text((x + 12, y + 232), str(view.get("asset_status", ""))[:48], fill=(40, 40, 40), font=font)
        draw.text((x + 12, y + 248), Path(str(view["asset_path"])).parent.name[:48], fill=(70, 70, 70), font=font)
    sheet.save(path, "JPEG", quality=91, optimize=True)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for path in (
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ):
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())
