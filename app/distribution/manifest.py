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
class DeltaManifest:
    base_source_sha: str
    archive_sha256: str
    archive_size: int
    paths: tuple[str, ...]


@dataclass(frozen=True)
class ArchivePart:
    name: str
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
    launcher_sha256: str | None = None
    launcher_size: int | None = None
    delta: DeltaManifest | None = None
    archive_parts: tuple[ArchivePart, ...] = ()
    archive_size: int | None = None
    archive_sha256: str | None = None


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
    optional = {"launcher_sha256", "launcher_size", "delta",
                "archive_parts", "archive_size", "archive_sha256"}
    if not isinstance(doc, dict) or not fields.issubset(doc) or not set(doc).issubset(fields | optional):
        raise ManifestError("Unexpected manifest fields")
    if ("launcher_sha256" in doc) != ("launcher_size" in doc):
        raise ManifestError("Incomplete launcher asset metadata")
    launcher_sha256 = valid_sha(doc["launcher_sha256"]) if "launcher_sha256" in doc else None
    launcher_size = doc.get("launcher_size")
    if launcher_sha256 is not None and (
        type(launcher_size) is not int or not 0 < launcher_size <= 128 * 1024**2
    ):
        raise ManifestError("Invalid launcher asset size")
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
    normalized_paths = {f.path.casefold() for f in files}
    for candidate in normalized_paths:
        components = candidate.split("/")
        if any("/".join(components[:i]) in normalized_paths for i in range(1, len(components))):
            raise ManifestError("File/directory path collision")
    entrypoint = valid_path(doc["entrypoint"])
    if entrypoint not in {e.path for e in files} or not entrypoint.casefold().endswith(".exe"):
        raise ManifestError("Missing executable entrypoint")
    archive_parts: tuple[ArchivePart, ...] = ()
    archive_size = None
    archive_sha256 = None
    archive_fields = {"archive_parts", "archive_size", "archive_sha256"}
    if any(name in doc for name in archive_fields):
        if not archive_fields.issubset(doc):
            raise ManifestError("Incomplete multipart archive metadata")
        rows = doc["archive_parts"]
        if not isinstance(rows, list) or not 2 <= len(rows) <= 64:
            raise ManifestError("Invalid number of archive parts")
        archive_size = doc["archive_size"]
        if type(archive_size) is not int or not 0 < archive_size <= MAX_TOTAL_SIZE + 512 * 1024**2:
            raise ManifestError("Invalid assembled archive size")
        archive_sha256 = valid_sha(doc["archive_sha256"])
        pieces = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict) or set(row) != {"name", "size", "sha256"}:
                raise ManifestError("Invalid multipart archive entry")
            name = row["name"]
            if name != f"atlas-windows.part{index:04d}":
                raise ManifestError("Unexpected multipart archive name/order")
            size = row["size"]
            if type(size) is not int or not 0 < size <= 2 * 1024**3 - 1:
                raise ManifestError("Invalid multipart asset size")
            pieces.append(ArchivePart(name, size, valid_sha(row["sha256"])))
        if sum(piece.size for piece in pieces) != archive_size:
            raise ManifestError("Multipart archive lengths do not match")
        archive_parts = tuple(pieces)
    delta = None
    if "delta" in doc:
        item = doc["delta"]
        required = {"base_source_sha", "archive_sha256", "archive_size", "paths"}
        if not isinstance(item, dict) or set(item) != required:
            raise ManifestError("Invalid differential archive metadata")
        base = valid_source_sha(item["base_source_sha"])
        if base == doc["source_sha"]:
            raise ManifestError("Delta base must differ from release")
        length = item["archive_size"]
        if type(length) is not int or not 0 < length <= 2 * 1024**3 - 1:
            raise ManifestError("Invalid differential archive size")
        paths = item["paths"]
        if not isinstance(paths, list) or not 0 < len(paths) <= len(files):
            raise ManifestError("Invalid differential file list")
        checked = [valid_path(path) for path in paths]
        if len(set(checked)) != len(checked) or not set(checked).issubset({f.path for f in files}):
            raise ManifestError("Invalid differential file paths")
        delta = DeltaManifest(base, valid_sha(item["archive_sha256"]),
                              length, tuple(checked))
    return ReleaseManifest(
        valid_version(doc["app_version"]),
        valid_version(doc["data_version"]),
        doc["schema_version"],
        valid_source_sha(doc["source_sha"]),
        entrypoint,
        tuple(files),
        launcher_sha256=launcher_sha256,
        launcher_size=launcher_size,
        delta=delta,
        archive_parts=archive_parts,
        archive_size=archive_size,
        archive_sha256=archive_sha256,
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
