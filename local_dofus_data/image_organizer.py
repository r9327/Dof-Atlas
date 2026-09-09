from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .data_store import DataStore
from .image_indexer import ImageIndexer
from .utils import image_basename_from_url, normalize_text, safe_int, save_json_atomic

JOB_ICON_IDS = {
    2: 1,
    24: 13,
    26: 14,
    28: 18,
    36: 30,
}


class ImageOrganizer:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG, store: DataStore | None = None):
        self.config = config
        self.store = store or DataStore(config=config)
        self.store.initialize()

    def organize(self, move_unreferenced: bool = True, dry_run: bool = False) -> dict[str, Any]:
        ensure_directories(self.config)
        for directory in (self.config.image_items_dir, self.config.image_resources_dir, self.config.image_misc_dir):
            directory.mkdir(parents=True, exist_ok=True)

        item_targets = self._build_item_targets()
        job_targets = self._build_job_targets()
        copied = self._copy_known_files(item_targets, dry_run=dry_run) + self._copy_known_files(job_targets, dry_run=dry_run)
        updated = 0 if dry_run else self._apply_targets(item_targets) + self._apply_job_targets(job_targets)
        missing = self._missing_files(item_targets) + self._missing_files(job_targets)
        moved_unreferenced = self._move_unreferenced_files(dry_run=dry_run) if move_unreferenced else 0

        indexed = {"dry_run": True} if dry_run else self._reindex_assets()

        report = {
            "dry_run": dry_run,
            "items_with_target": len(item_targets),
            "jobs_with_target": len(job_targets),
            "updated_rows": updated,
            "copied_files": copied,
            "missing_files": len(missing),
            "missing_samples": missing[:100],
            "moved_unreferenced": moved_unreferenced,
            "image_index": indexed,
        }
        save_json_atomic(self.config.reports_dir / "image_organization_report.json", report)
        return report

    def _reindex_assets(self) -> dict[str, Any]:
        with self.store.transaction() as conn:
            conn.execute("DELETE FROM image_assets")
        return ImageIndexer(self.store, self.config).index()

    def _build_item_targets(self) -> dict[int, dict[str, str]]:
        resource_ids = {safe_int(row.get("ankama_id")) for row in self.store.query_all("SELECT ankama_id FROM resources")}
        resource_ids.discard(None)
        targets: dict[int, dict[str, str]] = {}
        for row in self.store.query_all("SELECT ankama_id, name_fr, type, category, family, metadata_json FROM items WHERE ankama_id IS NOT NULL"):
            ankama_id = safe_int(row.get("ankama_id"))
            if ankama_id is None:
                continue
            image_name = self._image_name_from_metadata(row.get("metadata_json"))
            if not image_name:
                continue
            folder = self._target_folder(row, ankama_id in resource_ids or self._looks_like_resource(row))
            rel_path = str((folder / image_name).resolve().relative_to(self.config.root_dir.resolve())).replace("\\", "/")
            targets[ankama_id] = {"image_name": image_name, "rel_path": rel_path}
        return targets

    def _build_job_targets(self) -> dict[int, dict[str, str]]:
        targets: dict[int, dict[str, str]] = {}
        for row in self.store.query_all("SELECT ankama_id, metadata_json FROM jobs WHERE ankama_id IS NOT NULL"):
            ankama_id = safe_int(row.get("ankama_id"))
            if ankama_id is None:
                continue
            metadata = self._loads(row.get("metadata_json"))
            raw = metadata.get("raw") or metadata.get("legacy") or {}
            image_name = image_basename_from_url(raw.get("image") if isinstance(raw, dict) else "")
            if not image_name and ankama_id in JOB_ICON_IDS:
                image_name = f"{JOB_ICON_IDS[ankama_id]}.png"
            if not image_name:
                continue
            image_name = re.sub(r"\.(?:jpg|jpeg|webp)$", ".png", image_name, flags=re.IGNORECASE)
            rel_path = str((self.config.image_misc_dir / "jobs" / image_name).resolve().relative_to(self.config.root_dir.resolve())).replace("\\", "/")
            targets[ankama_id] = {"image_name": image_name, "rel_path": rel_path}
        return targets

    def _copy_known_files(self, targets: dict[int, dict[str, str]], dry_run: bool = False) -> int:
        copied = 0
        known_files = self._known_image_files()
        for target in targets.values():
            image_name = target["image_name"]
            destination = self.config.root_dir / target["rel_path"]
            if destination.exists():
                continue
            source = known_files.get(image_name.casefold())
            if not source:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not dry_run:
                shutil.copy2(source, destination)
            copied += 1
        return copied

    def _known_image_files(self) -> dict[str, Path]:
        files: dict[str, Path] = {}
        for directory in (self.config.image_items_dir, self.config.image_resources_dir, self.config.image_misc_dir, self.config.images_dir / "archive"):
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}:
                    files.setdefault(path.name.casefold(), path)
        return files

    def _apply_targets(self, targets: dict[int, dict[str, str]]) -> int:
        updated = 0
        with self.store.transaction() as conn:
            for ankama_id, target in targets.items():
                rel_path = target["rel_path"]
                for table in ("items", "resources", "equipment", "consumables"):
                    before = conn.total_changes
                    conn.execute(f"UPDATE {table} SET image_path=? WHERE ankama_id=?", (rel_path, ankama_id))
                    updated += max(0, conn.total_changes - before)
                before = conn.total_changes
                conn.execute("UPDATE recipe_ingredients SET image_path=? WHERE ingredient_ankama_id=?", (rel_path, ankama_id))
                updated += max(0, conn.total_changes - before)

            conn.execute("UPDATE equipment SET set_id=json_extract(metadata_json, '$.raw.itemSetId') WHERE metadata_json LIKE '%itemSetId%'")
        return updated

    def _apply_job_targets(self, targets: dict[int, dict[str, str]]) -> int:
        updated = 0
        with self.store.transaction() as conn:
            for ankama_id, target in targets.items():
                before = conn.total_changes
                conn.execute("UPDATE jobs SET image_path=? WHERE ankama_id=?", (target["rel_path"], ankama_id))
                updated += max(0, conn.total_changes - before)
        return updated

    def _missing_files(self, targets: dict[int, dict[str, str]]) -> list[dict[str, Any]]:
        missing = []
        for ankama_id, target in targets.items():
            path = self.config.root_dir / target["rel_path"]
            if not path.exists():
                missing.append({"ankama_id": ankama_id, "path": target["rel_path"]})
        return missing

    def _move_unreferenced_files(self, dry_run: bool = False) -> int:
        referenced = set()
        for table, column in (
            ("items", "image_path"),
            ("resources", "image_path"),
            ("equipment", "image_path"),
            ("consumables", "image_path"),
            ("recipe_ingredients", "image_path"),
            ("spells", "image_path"),
            ("classes", "image_path"),
            ("monsters", "image_path"),
            ("monster_families", "image_path"),
            ("areas", "image_path"),
            ("subareas", "image_path"),
        ):
            for row in self.store.query_all(f"SELECT {column} AS path FROM {table} WHERE COALESCE({column}, '')!=''"):
                referenced.add(str(row["path"]).replace("\\", "/"))

        moved = 0
        directory_targets = (
            (self.config.image_items_dir, self.config.images_dir / "archive" / "unmatched" / "items"),
            (self.config.image_resources_dir, self.config.images_dir / "archive" / "unmatched" / "resources"),
        )
        for directory, unmatched_dir in directory_targets:
            unmatched_dir.mkdir(parents=True, exist_ok=True)
            for path in sorted(directory.glob("*")):
                if not path.is_file() or path.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                rel = str(path.resolve().relative_to(self.config.root_dir.resolve())).replace("\\", "/")
                if rel in referenced:
                    continue
                destination = self._unique_destination(unmatched_dir / path.name)
                if not dry_run:
                    os.replace(path, destination)
                moved += 1
        return moved

    @staticmethod
    def _unique_destination(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        for index in range(1, 10000):
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"destination unique introuvable: {path}")

    @staticmethod
    def _image_name_from_metadata(metadata_json: Any) -> str:
        metadata = ImageOrganizer._loads(metadata_json)
        raw = metadata.get("raw") or metadata.get("legacy") or metadata.get("ingredient") or {}
        if isinstance(raw, dict):
            icon_id = safe_int(raw.get("iconId"))
            if icon_id is not None:
                return f"{icon_id}.png"
        for value in (
            metadata.get("image_url"),
            raw.get("img") if isinstance(raw, dict) else "",
            raw.get("image") if isinstance(raw, dict) else "",
        ):
            image_name = image_basename_from_url(value)
            if image_name:
                return image_name
        return ""

    @staticmethod
    def _looks_like_resource(row: dict[str, Any]) -> bool:
        text = normalize_text(" ".join(str(row.get(key, "")) for key in ("type", "category", "family", "name_fr")))
        if any(token in text for token in ("trophee", "prysmaradite", "dofus", "anneau", "amulette", "cape", "coiffe", "botte", "ceinture", "bouclier")):
            return False
        return bool(re.search(r"\b(ressource|resource|bois|minerai|cereale|poisson|plante|fleur|viande|alliage|pierre|graine)\b", text))

    def _target_folder(self, row: dict[str, Any], is_resource: bool) -> Path:
        text = normalize_text(" ".join(str(row.get(key, "")) for key in ("type", "category", "family", "name_fr")))
        type_slug = self._folder_slug(row.get("type") or row.get("category") or "autres")
        if is_resource:
            for folder, hints in {
                "metiers/bois": ("bois",),
                "metiers/minerais": ("minerai", "alliage"),
                "metiers/cereales": ("cereale", "ble", "orge", "avoine", "houblon", "seigle", "riz", "malt", "chanvre", "mais", "millet"),
                "metiers/plantes": ("plante", "fleur", "ortie", "sauge", "trefle", "menthe", "orchidee", "edelweiss", "pandouille", "ginseng", "belladone", "mandragore"),
                "metiers/poissons": ("poisson", "goujon", "greuvette", "truite", "crabe", "carpe", "sardine", "brochet", "kralamoure", "anguille", "dorade", "perche", "raie", "lotte"),
                "metiers/viandes": ("viande",),
            }.items():
                if any(hint in text for hint in hints):
                    return self.config.image_resources_dir / folder
            return self.config.image_resources_dir / type_slug

        if "prysmaradite" in text:
            return self.config.image_items_dir / "prysmaradite"
        if "trophee" in text or "dofus / trophee" in text:
            return self.config.image_items_dir / "trophees"
        for folder, hints in {
            "armes": ("arme", "epee", "arc", "baguette", "baton", "dague", "pelle", "marteau", "hache"),
            "coiffes": ("coiffe", "chapeau"),
            "capes": ("cape",),
            "ceintures": ("ceinture",),
            "anneaux": ("anneau",),
            "colliers": ("collier", "amulette"),
            "bottes": ("botte",),
            "boucliers": ("bouclier",),
            "dofus": ("dofus",),
        }.items():
            if any(hint in text for hint in hints):
                return self.config.image_items_dir / folder
        return self.config.image_items_dir / type_slug

    @staticmethod
    def _folder_slug(value: Any) -> str:
        slug = normalize_text(value)
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        return slug or "autres"

    @staticmethod
    def _loads(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                loaded = json.loads(value)
                return loaded if isinstance(loaded, dict) else {}
            except Exception:
                return {}
        return value if isinstance(value, dict) else {}


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Organize local Dofus image files and repair image paths")
    parser.add_argument("--keep-unreferenced", action="store_true", help="leave orphan image files in their current folders")
    parser.add_argument("--dry-run", action="store_true", help="write report without moving files or updating SQLite")
    args = parser.parse_args(argv)
    report = ImageOrganizer().organize(move_unreferenced=not args.keep_unreferenced, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
