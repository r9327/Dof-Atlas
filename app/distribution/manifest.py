"""Strict, portable release manifest validation (standard library only)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_SHA256 = re.compile(r"[0-9a-f]{64}\\Z")
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,79}\\Z")
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_FILES = 100_000


class ManifestError(ValueError):
    """Release metadata violates the update contract."""


@dataclass(frozen=True)
class ReleaseFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ReleaseManifest:
    app_version: str
    data_version: str
    schema_version: int
    source_sha: str
    files: tuple[ReleaseFile, ...]


def _version(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ManifestError(f"Invalid {field}")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ManifestError(f"Invalid {field}")
    return value


def _path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\\\" in value or "\\x00" in value:
        raise ManifestError("Invalid file path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")) or ":" in value:
        raise ManifestError("Unsafe file path")
    if p.parts[0].casefold() in ("user", "profiles", "logs", "cache", ".cache"):
        raise ManifestError("User data path cannot be distributed")
    return value


def parse_manifest(raw: bytes) -> ReleaseManifest:
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ManifestError("Manifest too large")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError("Malformed JSON") from exc
    if not isinstance(doc, dict) or set(doc) != {"app_version", "data_version", "schema_version", "source_sha", "files"}:
        raise ManifestError("Unexpected manifest fields")
    schema = doc["schema_version"]
    if type(schema) is not int or schema < 1:
        raise ManifestError("Invalid schema version")
    entries = doc["files"]
    if not isinstance(entries, list) or len(entries) > _MAX_FILES:
        raise ManifestError("Invalid file list")
    seen: set[str] = set()
    files: list[ReleaseFile] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise ManifestError("Invalid file entry")
        path = _path(item["path"])
        key = path.casefold()
        if key in seen:
            raise ManifestError("Duplicate file path")
        seen.add(key)
        size = item["size"]
        if type(size) is not int or size < 0:
            raise ManifestError("Invalid file size")
        files.append(ReleaseFile(path, size, _sha(item["sha256"], "file hash")))
    return ReleaseManifest(
        _version(doc["app_version"], "app version"),
        _version(doc["data_version"], "data version"),
        schema,
        _sha(doc["source_sha"], "source SHA"),
        tuple(files),
    )


def verify_file(path: Path, entry: ReleaseFile) -> bool:
    """Check an existing regular file against its expected length and digest."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size != entry.size:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == entry.sha256
