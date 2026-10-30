"""Portable, build-time Quest catalogue index for clean Windows installations.

Stores only small Quest summary columns/relations; rich details are explicitly
NOT bundled and remain deferred. A release manifest authenticates the artifact,
and the runtime restores it to the per-install cache name computed from the
current canonical source signature. This prevents 1,976-Quest source parsing
on a user's first launch without changing the QuestCatalog public contract.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
from app.quest_catalog import QUEST_CATALOG_SOURCE_FILES

SCHEMA = 1
MIN_QUESTS = 1900
MAX_BYTES = 128 * 1024 * 1024
FILENAME = "quest_index_v1.sqlite3"
MANIFEST = "quest_index_v1.manifest.json"
BUNDLE_ROOT = DATA_DIR / "bootstrap"


def _source_sizes(data_dir: Path) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for _label, relative in QUEST_CATALOG_SOURCE_FILES:
        try:
            sizes[str(relative).replace("\\", "/")] = (Path(data_dir) / relative).stat().st_size
        except OSError:
            sizes[str(relative).replace("\\", "/")] = -1
    return sizes


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_index(path: Path, *, minimum: int = MIN_QUESTS) -> int:
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("Portable Quest SQLite outside size budget")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        ready = db.execute("SELECT value FROM metadata WHERE key='ready'").fetchone()
        count = db.execute("SELECT COUNT(*) FROM quests").fetchone()[0]
        detailed = db.execute("SELECT COUNT(*) FROM quests WHERE detail IS NOT NULL").fetchone()[0]
        if ready is None or int(count) < int(minimum) or int(detailed):
            raise ValueError("Quest source cache incomplete or contains rich details")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Quest SQLite integrity check failed")
    return int(count)


def publish_quest_index(source: Path, output_dir: Path, *, source_sha: str) -> dict[str, object]:
    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        raise ValueError("Exact release source SHA required")
    source = Path(source)
    output_dir = Path(output_dir)
    _check_index(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / FILENAME
    temp = dest.with_name("." + FILENAME + "." + uuid4().hex + ".tmp")
    try:
        # SQLite backup checkpoints any WAL pages without blocking app caches.
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader:
            with closing(sqlite3.connect(temp)) as writer:
                reader.backup(writer)
        count = _check_index(temp)
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)
    metadata: dict[str, object] = {
        "schema": SCHEMA,
        "source_sha": source_sha,
        "quest_count": count,
        "file_size": dest.stat().st_size,
        "file_sha256": _sha256(dest),
        "quest_source_sizes": _source_sizes(RAW_QUEST_DATA_DIR),
    }
    manifest = output_dir / MANIFEST
    draft = manifest.with_name("." + MANIFEST + "." + uuid4().hex + ".tmp")
    try:
        draft.write_text(json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8")
        draft.replace(manifest)
    finally:
        draft.unlink(missing_ok=True)
    return metadata


def _bundle_root(root: Path | None = None) -> Path | None:
    if root is not None:
        return Path(root)
    override = os.environ.get("DOFUS_ATLAS_PREBUILT_QUEST_INDEX_DIR", "").strip()
    if override:
        return Path(override)
    return BUNDLE_ROOT if bool(getattr(sys, "frozen", False)) else None


def verify_quest_index(*, root: Path | None = None, data_dir: Path = RAW_QUEST_DATA_DIR) -> int:
    bundle = _bundle_root(root)
    if bundle is None:
        return 0
    try:
        data = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
        file = bundle / FILENAME
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            return 0
        if data.get("quest_source_sizes") != _source_sizes(data_dir):
            return 0
        if file.stat().st_size != data.get("file_size") or file.stat().st_size > MAX_BYTES:
            return 0
        if _sha256(file) != data.get("file_sha256"):
            return 0
        count = _check_index(file)
        if count != data.get("quest_count"):
            return 0
        return count
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        return 0


def restore_quest_index(
    destination: Path,
    *,
    root: Path | None = None,
    data_dir: Path = RAW_QUEST_DATA_DIR,
) -> bool:
    """Atomically install a verified immutable Quest index, never progression."""
    # Only the canonical installed Quest generation can consume a release seed.
    if Path(data_dir).resolve() != RAW_QUEST_DATA_DIR.resolve():
        return False
    bundle = _bundle_root(root)
    if bundle is None:
        return False
    if not verify_quest_index(root=bundle, data_dir=data_dir):
        return False
    destination = Path(destination)
    if destination.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name("." + destination.name + "." + uuid4().hex + ".tmp")
    try:
        with (bundle / FILENAME).open("rb") as src, temp.open("wb") as target:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                target.write(chunk)
        # A corrupt/replaced source between verification and copy must fail.
        if _sha256(temp) != _sha256(bundle / FILENAME):
            return False
        _check_index(temp)
        if destination.is_file():
            return False
        temp.replace(destination)
        return True
    except (OSError, ValueError, sqlite3.Error):
        return False
    finally:
        temp.unlink(missing_ok=True)
