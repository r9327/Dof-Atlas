"""Build and certify a reproducible public Craft seed from pinned Doduda data.

No personal data, private caches, network access at application runtime, or
dependency on a developer's local SQLite database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

from local_dofus_data.schema import CREATE_TABLES_SQL

ROOT = Path(__file__).resolve().parents[2]
RAW = Path("data/cache/dofus_maps/raw/doduda_cli")
SEED = Path("data/bootstrap/craft_seed.sqlite")
LOCK = Path("scripts/windows/craft_assets_lock.json")
_SOURCE_LABEL = "doduda_craft_seed_3.7.10.10"
_STAMP = "2026-10-13T00:00:00Z"
_MIN_COUNTS = {"items": 1000, "jobs": 10, "recipes": 100, "recipe_ingredients": 100}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def ensure_recipe_asset(root: Path, *, download: bool = False) -> Path:
    doc = json.loads((root / LOCK).read_text(encoding="utf-8"))
    pin = doc["assets"]["recipes.json"]
    if (doc.get("schema_version") != 1 or doc.get("tag") != "3.7.10.10"
            or doc.get("source_repo") != "dofusdude/dofus3-main"
            or set(doc["assets"]) != {"recipes.json"}
            or pin["asset"] != "recipes.json" or not isinstance(pin["size"], int)
            or pin["size"] <= 0 or pin["size"] > 20_000_000
            or len(pin["sha256"]) != 64):
        raise ValueError("Unsupported Craft recipe provenance lock")
    dest = root / RAW / "recipes.json"
    if dest.is_file() and dest.stat().st_size == pin["size"] and _sha256(dest) == pin["sha256"]:
        return dest
    if not download:
        raise FileNotFoundError(f"Craft source absent or modified: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{doc['source_repo']}/releases/download/{doc['tag']}/recipes.json"
    request = urllib.request.Request(url, headers={"User-Agent": "DofusAtlas-CraftBuild/1"})
    fd, tmp = tempfile.mkstemp(prefix=".atlas-recipes-", dir=dest.parent)
    try:
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=90) as response:
            for part in iter(lambda: response.read(1024 * 1024), b""):
                size += len(part)
                if size > pin["size"]:
                    raise ValueError("Craft recipe asset larger than pinned size")
                digest.update(part)
                out.write(part)
            out.flush()
            os.fsync(out.fileno())
        if size != pin["size"] or digest.hexdigest() != pin["sha256"]:
            raise ValueError("Craft recipe source failed pinned SHA256 verification")
        os.replace(tmp, dest)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return dest


def _load(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _rows(path: Path):
    payload = _load(path)
    refs = payload.get("references", {}).get("RefIds", [])
    if not isinstance(refs, list):
        raise ValueError(f"Unsupported Doduda source: {path}")
    for ref in refs:
        data = ref.get("data") if isinstance(ref, dict) else None
        if isinstance(data, dict):
            yield data


def _number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _array(value):
    if isinstance(value, dict):
        value = value.get("Array", [])
    return value if isinstance(value, list) else []


def _label(row, entries, *, key="nameId"):
    direct = row.get("name")
    if isinstance(direct, dict):
        direct = direct.get("fr") or direct.get("en")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    return str(entries.get(str(row.get(key) or ""), "") or "").strip()


def validate_seed(path: Path, *, minimums=None) -> dict[str, int]:
    """Fail before a release or first install when the Craft index is unusable."""
    required = _MIN_COUNTS if minimums is None else minimums
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise ValueError(f"Craft seed absent: {path}")
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Craft SQLite integrity check failed")
        counts = {table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                  for table in ("items", "jobs", "recipes", "recipe_ingredients")}
        for table, expected in required.items():
            if counts[table] < expected:
                raise ValueError(f"Craft seed incomplete: {table}={counts[table]} < {expected}")
        if not con.execute(
            "SELECT 1 FROM items i JOIN recipes r ON i.ankama_id=r.result_ankama_id "
            "WHERE i.name_fr<>'' AND r.result_name_fr<>'' LIMIT 1"
        ).fetchone():
            raise ValueError("Craft seed has no searchable recipes")
        if not con.execute(
            "SELECT 1 FROM recipe_ingredients ri JOIN recipes r ON ri.recipe_id=r.id "
            "WHERE ri.name_fr<>'' LIMIT 1"
        ).fetchone():
            raise ValueError("Craft seed has no named recipe ingredients")
    return counts


def build_seed(root: Path, output: Path, *, minimums=None) -> dict[str, int]:
    ensure_recipe_asset(root)
    base = root / RAW
    for name in ("items.json", "jobs.json", "item_types.json", "languages/fr.json"):
        if not (base / name).is_file():
            raise FileNotFoundError(f"Required Craft source missing: {base / name}")
    locale = _load(base / "languages/fr.json")
    entries = locale.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("Unrecognized Doduda French dictionary")
    item_types = { _number(row.get("id")): _label(row, entries)
                   for row in _rows(base / "item_types.json") }
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".atlas-craft-", suffix=".sqlite", dir=output.parent)
    os.close(fd)
    temp = Path(name)
    try:
        with closing(sqlite3.connect(temp)) as con:
            con.executescript(CREATE_TABLES_SQL)
            items = {}
            for row in _rows(base / "items.json"):
                ident = _number(row.get("id"))
                label = _label(row, entries)
                if ident <= 0 or not label:
                    continue
                level = _number(row.get("level"))
                type_name = item_types.get(_number(row.get("typeId")), "")
                icon = _number(row.get("iconId"))
                con.execute(
                    "INSERT OR IGNORE INTO items "
                    "(ankama_id,gid,name_fr,name_en,category,type,family,level,source,image_path,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ident,ident,label,"",type_name,type_name,type_name,
                     level,_SOURCE_LABEL,f"data/images/items/{icon}.png" if icon else "",_STAMP),
                )
                items[ident] = (label,level,type_name,icon)
            jobs = {}
            for row in _rows(base / "jobs.json"):
                ident = _number(row.get("id"))
                label = _label(row, entries)
                if not ident or not label:
                    continue
                jobs[ident] = label
                con.execute(
                    "INSERT OR IGNORE INTO jobs "
                    "(ankama_id,gid,name_fr,name_en,type,category,source,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (ident,ident,label,"","job","job",_SOURCE_LABEL,_STAMP),
                )
            for row in _rows(base / "recipes.json"):
                result_id = _number(row.get("resultId"))
                result = items.get(result_id)
                ingredients = _array(row.get("ingredientIds"))
                quantities = _array(row.get("quantities"))
                if not result_id or not result or not ingredients or len(ingredients) != len(quantities):
                    continue
                job_id = _number(row.get("jobId"))
                name_fr, item_level, _, _ = result
                con.execute(
                    "INSERT OR IGNORE INTO recipes "
                    "(ankama_id,result_item_id,result_ankama_id,result_name_fr,result_name_en,"
                    "job_id,job_name,level,source,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (result_id,result_id,result_id,name_fr,"",job_id,jobs.get(job_id,""),
                     _number(row.get("resultLevel")) or item_level,_SOURCE_LABEL,_STAMP),
                )
                recipe = con.execute("SELECT id FROM recipes WHERE result_ankama_id=?",
                                     (result_id,)).fetchone()
                if recipe is None:
                    continue
                for raw_id, raw_qty in zip(ingredients, quantities):
                    ing_id, qty = _number(raw_id), _number(raw_qty)
                    ingredient = items.get(ing_id)
                    if not ingredient or qty <= 0:
                        continue
                    ing_name, ing_level, ing_type, ing_icon = ingredient
                    con.execute(
                        "INSERT OR IGNORE INTO recipe_ingredients "
                        "(recipe_id,ingredient_item_id,ingredient_ankama_id,name_fr,name_en,"
                        "quantity,type,level,source,image_path) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (recipe[0],ing_id,ing_id,ing_name,"",qty,ing_type,ing_level,
                         _SOURCE_LABEL,f"data/images/items/{ing_icon}.png" if ing_icon else ""),
                    )
            con.commit()
        counts = validate_seed(temp, minimums=minimums)
        os.replace(temp, output)
        return counts
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / SEED)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        if args.download:
            ensure_recipe_asset(args.root, download=True)
        counts = validate_seed(args.output) if args.verify else build_seed(args.root, args.output)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"CRAFT SEED FAILED: {exc}")
        return 1
    print(f"VERIFIED: public offline Craft SQLite {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
