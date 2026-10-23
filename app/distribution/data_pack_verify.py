"""Read-only staged-data-pack verification before Atlas installs anything.

DataPack manifests must be authenticated by the outer updater. This module
does not trust a declared hash without reading the downloaded bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .data_pack_plan import DataPack, InvalidDataPack, _check_pack


@dataclass(frozen=True, slots=True)
class VerifiedPack:
    kind: str
    bytes_checked: int
    sha256: str
    status: str = "VERIFIED_BLOB_ONLY"


def verify_staged_pack(pack: DataPack, staging_root: Path, *,
                       max_bytes: int = 512 * 1024 * 1024,
                       chunk_bytes: int = 1024 * 1024) -> VerifiedPack:
    """Verify a staged blob without copying it into the live Atlas data area."""
    _check_pack(pack)
    if (not isinstance(staging_root, Path) or
            type(max_bytes) is not int or not 0 <= max_bytes <= 1 << 40 or
            type(chunk_bytes) is not int or not 4096 <= chunk_bytes <= 8 * 1024 * 1024):
        raise InvalidDataPack("invalid verification bounds")
    if staging_root.is_symlink():
        raise InvalidDataPack("staging root cannot be a symlink")
    root = staging_root.resolve(strict=True)
    candidate = staging_root / pack.artifact_path
    if candidate.is_symlink() or not candidate.is_file():
        raise InvalidDataPack("staged pack is absent or unsafe")
    actual = candidate.resolve(strict=True)
    if not actual.is_relative_to(root):
        raise InvalidDataPack("staging path escapes trusted root")
    try:
        size = actual.stat().st_size
        if size > max_bytes:
            raise InvalidDataPack("pack exceeds maximum allowed bytes")
        digest = sha256()
        read = 0
        with actual.open("rb") as handle:
            while block := handle.read(chunk_bytes):
                read += len(block)
                if read > max_bytes:
                    raise InvalidDataPack("pack exceeds maximum allowed bytes")
                digest.update(block)
        if digest.hexdigest() != pack.sha256:
            raise InvalidDataPack("pack SHA-256 mismatch")
        return VerifiedPack(pack.kind, read, pack.sha256)
    except OSError as exc:
        raise InvalidDataPack("unable to verify staged pack") from exc
