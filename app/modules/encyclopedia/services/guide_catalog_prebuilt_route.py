"""Portable, reconstructible Guide route shipped inside a certified Atlas bundle.

No character or progress data is stored here. A signed release build produces
the SQLite route once; the runtime reads the compact index plus one detail row.
Custom providers and source/development launches keep their existing path.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
from app.quest_catalog import QUEST_CATALOG_SOURCE_FILES
from app.modules.encyclopedia.providers.guide_provider import GUIDES_DIR
from app.modules.encyclopedia.services.guide_catalog_route_store import (
    indexed_path, restore_indexed_route, write_indexed_route,
)

SCHEMA = 1
GUIDE_ID = "dofus_sylvestre"
STORE_SIGNATURE = "atlas-release-precompiled-route-v1"
BUNDLE_DIR = DATA_DIR / "bootstrap" / "guide_routes"
MANIFEST_NAME = "dofus_sylvestre.manifest.json"
LEGACY_STORE_NAME = "dofus_sylvestre.route.json.gz"
MAX_STORE_BYTES = 128 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_sizes(data_dir: Path) -> dict[str, int]:
    """Cheap installed-source check: no 300 MB source hash at Guide open."""
    sizes = {}
    for _label, relative in QUEST_CATALOG_SOURCE_FILES:
        file = data_dir / relative
        try:
            sizes[str(relative).replace("\\", "/")] = file.stat().st_size
        except OSError:
            sizes[str(relative).replace("\\", "/")] = -1
    return sizes


def _steps_digest(guide: Any) -> str:
    steps = [
        (
            str(getattr(step, "id", "") or ""),
            str(getattr(step, "step_type", "") or ""),
            str(getattr(step, "entity_id", "") or ""),
            int(getattr(step, "order", 0) or 0),
        )
        for step in getattr(guide, "required_steps", ()) or ()
    ]
    return hashlib.sha256(
        json.dumps(steps, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _bundle_dir() -> Path | None:
    explicit = os.environ.get("DOFUS_ATLAS_PREBUILT_ROUTE_DIR", "").strip()
    if explicit:
        return Path(explicit)
    if bool(getattr(sys, "frozen", False)):
        return BUNDLE_DIR
    return None


def restore_prebuilt_route(service: Any, *, directory: Path | None = None) -> bool:
    """Fail closed on corruption, mismatched source or provider, then use fallback."""
    if str(getattr(service, "guide_id", "")) != GUIDE_ID:
        return False
    from app.modules.encyclopedia.providers.quest_provider import QuestProvider
    provider = getattr(service, "quest_provider", None)
    if type(provider) is not QuestProvider:
        return False
    if Path(provider.data_dir).resolve() != RAW_QUEST_DATA_DIR.resolve():
        return False
    if getattr(provider, "_catalog", None) is not None and not bool(
        getattr(provider._catalog, "deferred_details", False)
    ):
        return False
    directory = Path(directory) if directory is not None else _bundle_dir()
    if directory is None:
        return False
    manifest_path = directory / MANIFEST_NAME
    route = indexed_path(directory / LEGACY_STORE_NAME)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return False
        if (manifest.get("schema") != SCHEMA
                or manifest.get("guide_id") != GUIDE_ID
                or manifest.get("store_signature") != STORE_SIGNATURE
                or manifest.get("store_name") != route.name):
            return False
        size = route.stat().st_size
        if not (0 < size <= MAX_STORE_BYTES) or size != manifest.get("store_size"):
            return False
        if _source_sizes(RAW_QUEST_DATA_DIR) != manifest.get("quest_source_sizes"):
            return False
        guide_file = GUIDES_DIR / (GUIDE_ID + ".json")
        if _sha256(guide_file) != manifest.get("guide_sha256"):
            return False
        if _steps_digest(service.catalog_guide) != manifest.get("guide_steps_sha256"):
            return False
        if _sha256(route) != manifest.get("store_sha256"):
            return False
        return restore_indexed_route(service, directory / LEGACY_STORE_NAME, STORE_SIGNATURE)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def publish_prebuilt_route(
    service: Any, directory: Path, *, source_sha: str,
) -> dict[str, object]:
    """Builder-only: publish index and metadata after successful full projection."""
    if str(getattr(service, "guide_id", "")) != GUIDE_ID:
        raise ValueError("Expected Sylvestre Guide for precompiled route")
    if len(service.cards) < 1000:
        raise ValueError("Incomplete precompiled route: fewer than 1000 cards")
    if len(str(source_sha)) != 40 or any(c not in "0123456789abcdef" for c in source_sha):
        raise ValueError("Build source must be an exact 40-character commit SHA")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    route = write_indexed_route(service, directory / LEGACY_STORE_NAME, STORE_SIGNATURE)
    metadata: dict[str, object] = {
        "schema": SCHEMA,
        "guide_id": GUIDE_ID,
        "source_sha": source_sha,
        "store_signature": STORE_SIGNATURE,
        "store_name": route.name,
        "store_size": route.stat().st_size,
        "store_sha256": _sha256(route),
        "guide_sha256": _sha256(GUIDES_DIR / (GUIDE_ID + ".json")),
        "guide_steps_sha256": _steps_digest(service.catalog_guide),
        "quest_source_sizes": _source_sizes(RAW_QUEST_DATA_DIR),
        "card_count": len(service.cards),
    }
    temp = directory / (MANIFEST_NAME + ".tmp")
    try:
        temp.write_text(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temp.replace(directory / MANIFEST_NAME)
    finally:
        temp.unlink(missing_ok=True)
    return metadata
