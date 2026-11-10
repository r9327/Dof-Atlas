"""Reassemble authenticated GitHub release parts into an atomic ZIP file."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

from .manifest import ReleaseManifest


def assemble_archive_parts(
    manifest: ReleaseManifest,
    directory: Path,
    destination: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Verify every part and the whole archive in a single sequential read.

    The old implementation hashed each individual part *before* reading it
    again to assemble/hash the ZIP: up to twice the disk I/O for a 2.7 GB
    release, with no progress while the user saw 75%. Per-part and archive
    SHA-256 are still checked before atomic publication.
    """
    if not manifest.archive_parts or manifest.archive_size is None or manifest.archive_sha256 is None:
        raise ValueError("Release does not declare multipart archive metadata")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".joining")
    digest = hashlib.sha256()
    count = 0
    total = manifest.archive_size
    last_percent = -1
    try:
        with temporary.open("wb") as output:
            for part in manifest.archive_parts:
                source = directory / part.name
                if not source.is_file():
                    raise ValueError("Missing distribution part: " + part.name)
                part_digest = hashlib.sha256()
                part_count = 0
                with source.open("rb") as input_file:
                    for block in iter(lambda: input_file.read(1024 * 1024), b""):
                        part_count += len(block)
                        count += len(block)
                        if part_count > part.size or count > total:
                            raise ValueError("Multipart archive exceeds declared length")
                        part_digest.update(block)
                        digest.update(block)
                        output.write(block)
                        if progress is not None:
                            percentage = count * 100 // max(total, 1)
                            if percentage > last_percent and percentage < 100:
                                last_percent = percentage
                                progress(count, total)
                if part_count != part.size or part_digest.hexdigest() != part.sha256:
                    raise ValueError("Missing or corrupted distribution part: " + part.name)
            output.flush()
            os.fsync(output.fileno())
        if count != total or digest.hexdigest() != manifest.archive_sha256:
            raise ValueError("Assembled archive SHA-256 mismatch")
        os.replace(temporary, destination)
        if progress is not None:
            progress(total, total)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
