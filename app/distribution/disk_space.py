"""Conservative disk preflight for multi-gigabyte first-install payloads."""
from __future__ import annotations

import shutil
from pathlib import Path

from .manifest import ReleaseFile, ReleaseManifest, verify_file
from .release_client import UpdateError

RESERVE_BYTES = 512 * 1024**2


def remaining_space_needed(manifest: ReleaseManifest, downloads: Path,
                           *, reserve_bytes: int = RESERVE_BYTES) -> int:
    """Plan for compressed parts, assembled ZIP and extracted staging files.

    Existing resumed chunks count only when their length is in bounds; hashes
    are still checked by the downloader before activation.
    """
    extracted = sum(entry.size for entry in manifest.files)
    if not manifest.archive_parts or manifest.archive_size is None:
        # For single-file distributions the exact archive size is supplied by
        # RemoteRelease; the caller should pass that to the helper below.
        return extracted + reserve_bytes

    zip_path = downloads / (manifest.source_sha[:20] + ".zip")
    if verify_file(zip_path, ReleaseFile(zip_path.name, manifest.archive_size,
                                         manifest.archive_sha256)):
        return extracted + reserve_bytes

    cache = downloads / (manifest.source_sha[:20] + "-parts")
    cached = 0
    for part in manifest.archive_parts:
        complete = cache / part.name
        if verify_file(complete, ReleaseFile(part.name, part.size, part.sha256)):
            cached += part.size
            continue
        partial = cache / (part.name + ".download")
        try:
            size = partial.stat().st_size
        except (FileNotFoundError, OSError):
            size = 0
        if 0 <= size <= part.size:
            cached += size
    return extracted + manifest.archive_size + (manifest.archive_size - cached) + reserve_bytes


def ensure_space(manifest: ReleaseManifest, root: Path, *,
                 archive_size: int = 0, reserve_bytes: int = RESERVE_BYTES) -> None:
    """Fail early with a useful diagnostic instead of an ambiguous network error."""
    needed = remaining_space_needed(manifest, root / "downloads",
                                    reserve_bytes=reserve_bytes)
    if not manifest.archive_parts:
        needed += archive_size
    free = shutil.disk_usage(root).free
    if free < needed:
        gb = 1024**3
        raise UpdateError(
            "Espace disque insuffisant pour installer Atlas : "
            f"{free / gb:.1f} Go libres, {needed / gb:.1f} Go necessaires. "
            "Liberez de la place sur le disque Windows et relancez."
        )
