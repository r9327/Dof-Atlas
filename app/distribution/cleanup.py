"""Best-effort garbage collection after a successful, healthy update.

Only installer-owned caches and certified, unreferenced release slots may be
deleted. Running executables, rollback slot, pending transactions, user data
and the current resumable download are never touched.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .install import read_state

_PREFIX = re.compile(r"[0-9a-f]{20}\Z")
_SLOT_INDEX = ".atlas-file-index.json"
_PART_NAME = re.compile(r"atlas-windows[.]part[0-9]{4}(?:[.]download)?\Z")


def _link_or_junction(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _safe_part_cache(path: Path) -> bool:
    """Never recursively delete unexpected content or NTFS reparse points."""
    if not path.is_dir() or _link_or_junction(path):
        return False
    for child in path.iterdir():
        if (_link_or_junction(child) or not child.is_file()
                or not _PART_NAME.fullmatch(child.name)):
            return False
    return True



def cleanup_verified_runtime(root: Path) -> tuple[int, int]:
    """Return (obsolete slots, stale downloads) cleaned, never raise on locks."""
    state = read_state(root)
    if state.get("pending") or not state.get("active"):
        return (0, 0)
    current_sha = state.get("source_sha")
    if not isinstance(current_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", current_sha):
        return (0, 0)
    keep = {state.get("active"), state.get("previous")}
    removed_slots = 0
    versions = root / "versions"
    if versions.is_dir() and not _link_or_junction(versions):
        for item in versions.iterdir():
            # Require our own marker: never guess which unmarked directories
            # belong to Atlas, nor follow symlinks/junctions.
            if item.name in keep or _link_or_junction(item) or not item.is_dir():
                continue
            marker = item / _SLOT_INDEX
            if marker.is_file() and not _link_or_junction(marker) and (item / "AtlasApp").is_dir() and not _link_or_junction(item / "AtlasApp"):
                try:
                    shutil.rmtree(item)
                    removed_slots += 1
                except OSError:
                    pass  # Windows may still have a file handle open
    download_root = root / "downloads"
    removed_downloads = 0
    prefix = current_sha[:20]
    if download_root.is_dir() and not _link_or_junction(download_root):
        for item in download_root.iterdir():
            if _link_or_junction(item) or item.name.startswith(prefix):
                continue
            base = item.name[:20]
            if not _PREFIX.fullmatch(base):
                continue
            suffix = item.name[20:]
            # Exact updater-generated shapes only. Never recursively remove an
            # unexpected user folder or a random artifact.
            if suffix not in (".zip", ".zip.part", ".delta.zip.part", "-parts"):
                continue
            try:
                if suffix == "-parts":
                    if not _safe_part_cache(item):
                        continue
                    shutil.rmtree(item)
                elif item.is_file():
                    item.unlink()
                else:
                    continue
                removed_downloads += 1
            except OSError:
                pass
    return removed_slots, removed_downloads
