"""One source-media contract shared by Guide imports, policy and Qt readers.

Only explicit authored image references are recognized. No UI theme, no
network fallback and no guessed asset paths belong to this service.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

SOURCE_IMAGE_FIELDS = ("image_path", "local_image_path", "image_paths", "images")


def has_source_images(row: Mapping[str, Any]) -> bool:
    return any(row.get(field) for field in SOURCE_IMAGE_FIELDS) or bool(
        row.get("kind") == "image" and row.get("path")
    )


def source_image_values(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Read all supported source payload shapes, preserving authored order."""
    candidates: list[Any] = []
    for field in SOURCE_IMAGE_FIELDS:
        raw = row.get(field)
        if isinstance(raw, (list, tuple)):
            candidates.extend(raw)
        elif raw:
            candidates.append(raw)
    if row.get("kind") == "image" and row.get("path"):
        candidates.append(row["path"])

    paths: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        if isinstance(raw, Mapping):
            raw = raw.get("image_path") or raw.get("local_image_path") or raw.get("path")
        if isinstance(raw, str):
            value = raw.strip()
            if value and value not in seen:
                seen.add(value)
                paths.append(value)
    return tuple(paths)


def resolved_source_images(
    row: Mapping[str, Any], *, roots: tuple[Path, ...],
) -> tuple[str, ...]:
    """Use the canonical Quest asset resolver, including legacy Windows paths."""
    # Lazy import: pure route processing never has to load Quest data to
    # classify a screenshot. Only a visible image resolves its disk path.
    from app.quest_catalog import resolve_local_asset_path

    images: list[str] = []
    seen: set[str] = set()
    for raw in source_image_values(row):
        resolved = resolve_local_asset_path(raw, roots=roots)
        if resolved and resolved not in seen and Path(resolved).is_file():
            seen.add(resolved)
            images.append(resolved)
    return tuple(images)


def source_image_key(row: Mapping[str, Any]) -> str:
    """Distinguish two screenshots even when their action text is identical."""
    metadata = tuple(
        (field, repr(row[field]))
        for field in SOURCE_IMAGE_FIELDS if row.get(field)
    )
    if row.get("kind") == "image" and row.get("path") and not metadata:
        metadata = (("path", repr(row["path"])),)
    return repr(metadata) if metadata else ""


def carry_source_images(source: Mapping[str, Any], target: dict[str, Any]) -> None:
    """Copy authored media metadata into one rendered instruction."""
    for field in SOURCE_IMAGE_FIELDS:
        if source.get(field):
            target[field] = deepcopy(source[field])
    if source.get("kind") == "image" and source.get("path") and not any(
        target.get(field) for field in SOURCE_IMAGE_FIELDS
    ):
        target["image_path"] = source["path"]
    if has_source_images(source) and source.get("caption"):
        target["caption"] = str(source["caption"])


def drop_source_images(row: dict[str, Any]) -> None:
    """Remove media from later split sentences; the first owns the image."""
    if not has_source_images(row):
        return
    for field in SOURCE_IMAGE_FIELDS:
        row.pop(field, None)
    row.pop("caption", None)
    if row.get("kind") == "image":
        row.pop("path", None)
