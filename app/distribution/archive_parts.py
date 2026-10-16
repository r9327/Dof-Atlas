"""Reassemble authenticated GitHub release parts into an atomic ZIP file."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .manifest import ReleaseFile, ReleaseManifest, verify_file


def assemble_archive_parts(manifest: ReleaseManifest, directory: Path, destination: Path) -> Path:
    """Reject missing, altered, truncated or out-of-order pieces before activation."""
    if not manifest.archive_parts or manifest.archive_size is None or manifest.archive_sha256 is None:
        raise ValueError("Release does not declare multipart archive metadata")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".joining")
    digest = hashlib.sha256()
    count = 0
    try:
        with temporary.open("wb") as output:
            for part in manifest.archive_parts:
                source = directory / part.name
                if not verify_file(source, ReleaseFile(part.name, part.size, part.sha256)):
                    raise ValueError("Missing or corrupted distribution part: " + part.name)
                with source.open("rb") as input_file:
                    for block in iter(lambda: input_file.read(1024 * 1024), b""):
                        count += len(block)
                        if count > manifest.archive_size:
                            raise ValueError("Multipart archive exceeds declared length")
                        digest.update(block)
                        output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if count != manifest.archive_size or digest.hexdigest() != manifest.archive_sha256:
            raise ValueError("Assembled archive SHA-256 mismatch")
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
