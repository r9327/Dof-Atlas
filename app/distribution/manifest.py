"""Versioned, strictly validated update manifest. Standard library only."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_GIT_SHA = re.compile(r"[a-f0-9]{40}\Z")
_VERSION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._+-]{0,79}\Z")
_BAD_WIN = re.compile(r'[<>:"\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILE_SIZE = 4 * 1024**3
MAX_TOTAL_SIZE = 16 * 1024**3
MAX_FILE_COUNT = 100_000
PROTOCOL_VERSION = 1


class ManifestError(ValueError):
    """Release metadata does not satisfy the update protocol."""


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
    entrypoint: str
    files: tuple[ReleaseFile, ...]
    protocol_version: int = PROTOCOL_VERSION


def valid_version(value: Any) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ManifestError("Invalid version string")
    return value


def valid_sha(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ManifestError("Invalid SHA-256")
    return value


def valid_source_sha(value: Any) -> str:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        raise ManifestError("Invalid Git commit SHA")
    return value


def valid_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or _BAD_WIN.search(value):
        raise ManifestError("Invalid Windows path")
    if value.startswith("/") or any(
        part in ("", ".", "..") or part.endswith((" ", ".")) or
        _RESERVED.fullmatch(part) or len(part) > 160
        for part in value.split("/")
    ):
        raise ManifestError("Unsafe path component")
    parts = PurePosixPath(value).parts
    if not parts or parts[0] != "AtlasApp":
        raise ManifestError("Files must belong to AtlasApp payload")
    lowered = tuple(p.casefold() for p in parts)
    if len(lowered) > 1 and lowered[1] in ("user", "profiles", "logs", ".cache", "config"):
        raise ManifestError("User-specific paths cannot ship in releases")
    return value


def parse_manifest(raw: bytes) -> ReleaseManifest:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError("Manifest too large")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError("Malformed JSON") from exc
    fields = {"protocol_version", "app_version", "data_version", "schema_version",
              "source_sha", "entrypoint", "files"}
    if not isinstance(doc, dict) or set(doc) != fields:
        raise ManifestError("Unexpected manifest fields")
    if type(doc["protocol_version"]) is not int or doc["protocol_version"] != PROTOCOL_VERSION:
        raise ManifestError("Unsupported updater protocol")
    if type(doc["schema_version"]) is not int or not 1 <= doc["schema_version"] <= 100_000:
        raise ManifestError("Invalid data schema")
    entries = doc["files"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILE_COUNT:
        raise ManifestError("Invalid file list")
    files = []
    seen: set[str] = set()
    total = 0
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise ManifestError("Invalid file entry")
        path = valid_path(item["path"])
        folded = path.casefold()
        if folded in seen:
            raise ManifestError("Case-insensitive duplicate path")
        seen.add(folded)
        size = item["size"]
        if type(size) is not int or not 0 <= size <= MAX_FILE_SIZE:
            raise ManifestError("Invalid file size")
        total += size
        if total > MAX_TOTAL_SIZE:
            raise ManifestError("Payload too large")
        files.append(ReleaseFile(path, size, valid_sha(item["sha256"])))
    entrypoint = valid_path(doc["entrypoint"])
    if entrypoint.casefold() not in seen or not entrypoint.casefold().endswith(".exe"):
        raise ManifestError("Missing executable entrypoint")
    return ReleaseManifest(
        valid_version(doc["app_version"]),
        valid_version(doc["data_version"]),
        doc["schema_version"],
        valid_source_sha(doc["source_sha"]),
        entrypoint,
        tuple(files),
    )


def verify_file(path: Path, entry: ReleaseFile) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry.size:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest() == entry.sha256
    except OSError:
        return False
