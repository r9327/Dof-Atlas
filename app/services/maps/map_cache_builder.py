from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.services.maps.map_manifest import (
    DEFAULT_WORLD_NAME,
    MAP_IMAGES_DIR,
    MAP_RAW_DIR,
    MAP_THUMBNAILS_DIR,
    MapEntry,
    ensure_cache_layout,
    image_exists,
    load_map_entries,
    save_manifest,
)
from app.services.maps.providers.base_provider import BaseMapProvider

LOCAL_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
LOCAL_IMAGE_DIRS = (MAP_IMAGES_DIR, MAP_THUMBNAILS_DIR, MAP_RAW_DIR)


@dataclass(slots=True)
class MapCacheSummary:
    scanned_count: int = 0
    total_count: int | None = None
    cache_state: str = "Cache local : en attente"
    image_count: int = 0
    manifest_has_entries: bool = False


@dataclass(slots=True)
class LocalImageStats:
    image_count: int = 0
    total_bytes: int = 0
    first_image: Path | None = None
    empty_dirs: tuple[Path, ...] = ()


def get_local_image_files() -> list[Path]:
    ensure_cache_layout()
    files: list[Path] = []
    for root in LOCAL_IMAGE_DIRS:
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() in LOCAL_IMAGE_EXTENSIONS
        )
    return sorted(files, key=lambda path: str(path).casefold())


def get_local_image_stats() -> LocalImageStats:
    ensure_cache_layout()
    files = get_local_image_files()
    empty_dirs: list[Path] = []
    for root in LOCAL_IMAGE_DIRS:
        if not root.exists():
            empty_dirs.append(root)
            continue
        try:
            if not any(root.iterdir()):
                empty_dirs.append(root)
        except OSError:
            empty_dirs.append(root)

    total_bytes = 0
    for path in files:
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue

    return LocalImageStats(
        image_count=len(files),
        total_bytes=total_bytes,
        first_image=files[0] if files else None,
        empty_dirs=tuple(empty_dirs),
    )


def get_cache_summary(selected_world: str | None = None) -> MapCacheSummary:
    ensure_cache_layout()
    entries = load_map_entries()
    if not entries:
        return MapCacheSummary()

    filtered_entries = filter_entries_for_world(entries, selected_world)
    scanned_count = sum(1 for entry in filtered_entries if entry.status in {"scanned", "image_ready"})
    image_count = sum(1 for entry in filtered_entries if image_exists(entry))
    cache_state = "Cache local : prêt" if image_count else "Extraction nécessaire"
    return MapCacheSummary(
        scanned_count=scanned_count,
        total_count=len(filtered_entries),
        cache_state=cache_state,
        image_count=image_count,
        manifest_has_entries=True,
    )


def filter_entries_for_world(entries: list[MapEntry], selected_world: str | None) -> list[MapEntry]:
    if selected_world is None:
        return entries
    world = normalize_world(selected_world or DEFAULT_WORLD_NAME)
    if world == normalize_world(DEFAULT_WORLD_NAME):
        return [entry for entry in entries if is_default_world_entry(entry)]
    return [
        entry
        for entry in entries
        if normalize_world(entry.world) == world or normalize_world(entry.sub_world) == world
    ]


def is_default_world_entry(entry: MapEntry) -> bool:
    default_world = normalize_world(DEFAULT_WORLD_NAME)
    return (
        normalize_world(entry.world) == default_world
        or normalize_world(entry.sub_world) == default_world
        or (not str(entry.sub_world or "").strip() and entry.x is not None and entry.y is not None)
    )


def normalize_world(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.replace("’", "'").strip().casefold()


def build_cache_from_providers(providers: Iterable[BaseMapProvider]) -> MapCacheSummary:
    ensure_cache_layout()
    entries: list[MapEntry] = []
    sources: list[str] = []
    for provider in providers:
        if not provider.is_available():
            continue
        provider_entries = provider.list_maps()
        if provider_entries:
            entries.extend(provider_entries)
            sources.append(provider.name)
    if entries:
        save_manifest(entries, source="+".join(sources) or "unknown", complete=False)
    return get_cache_summary()
