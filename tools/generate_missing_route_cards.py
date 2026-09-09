from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "app") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "app"))

from app.session_manager_pyside import (  # noqa: E402
    JOB_RESOURCE_GROUPS,
    REPORTS_DIR,
    ROOT_DIR as APP_ROOT_DIR,
    canonical_job_name,
    display_path,
    existing_route_path,
    item_id,
    local_data_cache,
    local_image_path,
    normalize_key,
    route_path_for,
    write_json,
)


REPORT_FILE = REPORTS_DIR / "generated_route_cards.json"
ITEMS_BY_NAME: dict[str, dict[str, Any]] | None = None


def read_previous_generated_paths() -> set[str]:
    try:
        payload = REPORT_FILE.read_text(encoding="utf-8")
        import json

        rows = json.loads(payload).get("rows", [])
    except Exception:
        return set()
    paths = set()
    for row in rows if isinstance(rows, list) else []:
        raw = row.get("path") if isinstance(row, dict) else ""
        if raw:
            paths.add(str((APP_ROOT_DIR / raw).resolve()))
    return paths


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def find_item_by_name(name: str) -> dict[str, Any] | None:
    global ITEMS_BY_NAME
    if local_data_cache is None:
        return None
    if ITEMS_BY_NAME is None:
        ITEMS_BY_NAME = {}
        for loader in ("list_items", "list_craft_items"):
            if not hasattr(local_data_cache, loader):
                continue
            try:
                rows = getattr(local_data_cache, loader)()
            except Exception:
                rows = []
            for row in rows or []:
                key = normalize_key(row.get("name"))
                if key and key not in ITEMS_BY_NAME:
                    ITEMS_BY_NAME[key] = row
    key = normalize_key(name)
    if key in ITEMS_BY_NAME:
        return ITEMS_BY_NAME[key]
    try:
        rows = local_data_cache.search_items(name, limit=8)
    except Exception:
        rows = []
    for row in rows:
        if normalize_key(row.get("name")) == key:
            return row
    return rows[0] if rows else None


def find_resource_item(job_name: str, resource_name: str) -> dict[str, Any] | None:
    candidates = [resource_name]
    if normalize_key(job_name) == "bucheron":
        candidates = [f"Bois de {resource_name}", f"Bois d'{resource_name}", f"Bois d {resource_name}", resource_name]
    for candidate in candidates:
        item = find_item_by_name(candidate)
        if item:
            return item
    return None


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font, fill, width: int, line_gap: int = 4) -> int:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y


def create_route_card(path: Path, job_name: str, resource_name: str, item: dict[str, Any] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (560, 420), "#111827")
    draw = ImageDraw.Draw(image)
    title_font = load_font(30, bold=True)
    heading_font = load_font(22, bold=True)
    body_font = load_font(16)
    small_font = load_font(12)

    for x in range(0, 560, 40):
        draw.line((x, 0, x, 420), fill="#182235")
    for y in range(0, 420, 40):
        draw.line((0, y, 560, y), fill="#182235")
    draw.rounded_rectangle((18, 18, 542, 402), radius=12, outline="#334155", width=2, fill="#0f172a")
    draw.rectangle((18, 18, 542, 92), fill="#064e3b")
    draw.text((34, 32), "Dofus Atlas", font=title_font, fill="#f8fafc")
    draw.text((36, 70), "Carte route locale", font=small_font, fill="#d1fae5")

    icon_path = local_image_path(item or {})
    if icon_path:
        try:
            icon = Image.open(icon_path).convert("RGBA")
            icon.thumbnail((78, 78), Image.LANCZOS)
            image.paste(icon, (418, 112), icon)
        except Exception:
            icon_path = None

    draw.text((36, 120), canonical_job_name(job_name), font=heading_font, fill="#f8fafc")
    draw.text((36, 154), resource_name, font=title_font, fill="#fbbf24")
    if item:
        draw.text((36, 192), f"Objet local #{item_id(item) or '?'}", font=body_font, fill="#cbd5e1")

    y = draw_wrapped(
        draw,
        "Capture d'origine introuvable localement. Cette carte fallback est generee pour eviter un ecran vide dans le module metier.",
        (36, 238),
        body_font,
        "#e2e8f0",
        488,
    )
    draw.text((36, y + 16), "A remplacer par une vraie capture route quand disponible.", font=body_font, fill="#93c5fd")
    draw.text((36, 372), display_path(path), font=small_font, fill="#94a3b8")
    image.save(path)


def main() -> int:
    previous_generated = read_previous_generated_paths()
    generated = []
    regenerated = []
    kept = []
    for job_name, resources in JOB_RESOURCE_GROUPS.items():
        for resource_name, _tag in resources:
            route_name = canonical_job_name(job_name)
            existing = existing_route_path(route_name, resource_name, 1)
            path = route_path_for(route_name, resource_name, 1)
            overwrite_generated = str(path.resolve()) in previous_generated
            if existing is not None and not overwrite_generated:
                kept.append({"job": job_name, "resource": resource_name})
                continue
            item = find_resource_item(job_name, resource_name)
            create_route_card(path, job_name, resource_name, item)
            row = {
                "job": job_name,
                "resource": resource_name,
                "path": display_path(path),
                "item_id": item_id(item or {}),
                "image_path": display_path(local_image_path(item or {})),
            }
            if overwrite_generated:
                regenerated.append(row)
            else:
                generated.append(row)

    write_json(
        REPORT_FILE,
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "generated": len(generated),
            "regenerated": len(regenerated),
            "kept_existing": len(kept),
            "note": "Fallback cards only. They do not overwrite real route captures.",
            "rows": regenerated + generated,
        },
    )
    print(
        f"generated={len(generated)} regenerated={len(regenerated)} "
        f"kept_existing={len(kept)} report={REPORT_FILE.relative_to(APP_ROOT_DIR)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
