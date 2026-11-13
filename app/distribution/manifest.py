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

# Candidate repository-update channel (NRU-001). Parsing only: never authorizes an
# install until the certified channel publisher, frozen payload and rollback are
# wired and validated. Keep the existing ReleaseManifest as the single payload
# format; do not invent a second installer or accept unverified git source.
REPO_UPDATE_POINTER_LIMIT = 4096
REPO_UPDATE_MAX_DELTA = 95 * 1024 * 1024
_REPO_UPDATE_FIELDS = frozenset({
    "protocol_version", "channel", "source_sha", "app_commit_sha",
    "base_source_sha", "manifest_sha256", "delta_sha256", "delta_size",
})


@dataclass(frozen=True)
class RepoUpdatePointer:
    source_sha: str
    app_commit_sha: str
    base_source_sha: str
    manifest_sha256: str
    delta_sha256: str
    delta_size: int

    def pinned_asset_url(self, *, manifest: bool = False) -> str:
        """Only immutable GitHub blob paths, never caller-provided URLs."""
        name = "atlas-manifest.json" if manifest else "atlas-delta.zip"
        return (
            "https://raw.githubusercontent.com/r9327/Dof-Atlas-App/"
            f"{self.app_commit_sha}/updates/{self.source_sha}/{name}"
        )


def parse_repo_update_pointer(raw: bytes) -> RepoUpdatePointer:
    """Fail closed on unstable, unbounded or unpinned APP update metadata.

    This is metadata verification, not proof that a DEV SHA was certified.
    The publisher must verify source provenance and certification separately.
    """
    if not isinstance(raw, bytes) or len(raw) > REPO_UPDATE_POINTER_LIMIT:
        raise ManifestError("Invalid repository update pointer length")
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ManifestError("Malformed repository update pointer") from exc
    if (not isinstance(doc, dict) or set(doc) != _REPO_UPDATE_FIELDS or
            type(doc["protocol_version"]) is not int or doc["protocol_version"] != 1 or
            doc["channel"] != "stable"):
        raise ManifestError("Unsupported repository update pointer")
    source = valid_source_sha(doc["source_sha"])
    base = valid_source_sha(doc["base_source_sha"])
    commit = valid_source_sha(doc["app_commit_sha"])
    if base == source:
        raise ManifestError("Repository patch base cannot equal target")
    digest = valid_sha(doc["manifest_sha256"])
    delta_digest = valid_sha(doc["delta_sha256"])
    size = doc["delta_size"]
    if type(size) is not int or not 0 < size <= REPO_UPDATE_MAX_DELTA:
        raise ManifestError("Repository patch exceeds safe Git transport size")
    return RepoUpdatePointer(source, commit, base, digest, delta_digest, size)


def verify_repo_update_manifest(pointer: RepoUpdatePointer, raw: bytes) -> ReleaseManifest:
    """Bind an immutable repo pointer to the canonical frozen-app manifest."""
    if not isinstance(pointer, RepoUpdatePointer) or not isinstance(raw, bytes):
        raise ManifestError("Invalid repository update manifest inputs")
    if hashlib.sha256(raw).hexdigest() != pointer.manifest_sha256:
        raise ManifestError("Repository manifest digest mismatch")
    manifest = parse_manifest(raw)
    if manifest.source_sha != pointer.source_sha or manifest.delta is None:
        raise ManifestError("Repository patch manifest source or delta missing")
    if (manifest.delta.base_source_sha != pointer.base_source_sha or
            manifest.delta.archive_sha256 != pointer.delta_sha256 or
            manifest.delta.archive_size != pointer.delta_size):
        raise ManifestError("Repository patch identity mismatch")
    return manifest
