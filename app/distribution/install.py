"""Transactional Windows release slots; no modification of running binaries."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from .manifest import ManifestError, ReleaseFile, ReleaseManifest, verify_file, valid_path, valid_sha
from .release_client import UpdateError

Progress = Callable[[int, int], None]
_STATE_NAME = "state.json"
_SLOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")


def _valid_slot(value: object) -> bool:
    return isinstance(value, str) and bool(_SLOT.fullmatch(value)) and not value.endswith(".")


def read_state(root: Path) -> dict:
    path = root / _STATE_NAME
    if not path.exists():
        return {"active": None, "previous": None, "pending": False}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise UpdateError("Broken installation state") from exc
    if not isinstance(doc, dict) or type(doc.get("pending")) is not bool:
        raise UpdateError("Invalid installation state")
    for key in ("active", "previous"):
        value = doc.get(key)
        if value is not None and (not _valid_slot(value)):
            raise UpdateError("Invalid release slot")
    return doc


def _write_state(root: Path, state: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".atlas-state-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / _STATE_NAME)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def slot_path(root: Path, slot: str) -> Path:
    if not _valid_slot(slot):
        raise UpdateError("Invalid slot")
    return root / "versions" / slot


def active_executable(root: Path) -> Path | None:
    doc = read_state(root)
    slot = doc.get("active")
    if not slot:
        return None
    # entrypoint is committed by the verified installer, never fetched as a URL.
    relative = doc.get("entrypoint")
    if not isinstance(relative, str):
        raise UpdateError("Missing executable path")
    try:
        valid_path(relative)
    except ManifestError as exc:
        raise UpdateError("Invalid active executable path") from exc
    result = slot_path(root, slot) / relative
    if not result.is_file() or result.is_symlink():
        raise UpdateError("Installed executable missing")
    size, digest = doc.get("entrypoint_size"), doc.get("entrypoint_sha256")
    if size is not None or digest is not None:
        try:
            if type(size) is not int or size < 0:
                raise ManifestError("Invalid installed binary size")
            valid_sha(digest)
        except ManifestError as exc:
            raise UpdateError("Invalid installed binary integrity metadata") from exc
        if not verify_file(result, ReleaseFile(relative, size, digest)):
            raise UpdateError("Installed executable is corrupt; repair required")
    return result


def rollback_pending(root: Path) -> bool:
    state = read_state(root)
    if not state["pending"]:
        return False
    old = state.get("previous")
    if old and slot_path(root, old).is_dir():
        blocked = state.get("source_sha")
        restored = dict(state.get("previous_metadata") or {})
        state.update(active=old, previous=None, pending=False,
                     entrypoint=state.get("previous_entrypoint") or "AtlasApp/AtlasApp.exe",
                     blocked_source_sha=blocked, **restored)
        state.pop("previous_metadata", None)
        _write_state(root, state)
        return True
    # First install has no earlier known-good version; do not fabricate one.
    state["pending"] = False
    state["blocked_source_sha"] = state.get("source_sha")
    _write_state(root, state)
    return False


def mark_healthy(root: Path) -> None:
    state = read_state(root)
    if state["pending"]:
        state["pending"] = False
        _write_state(root, state)


def _validate_archive(archive: zipfile.ZipFile, manifest: ReleaseManifest,
                      selected: set[str] | None = None) -> dict[str, zipfile.ZipInfo]:
    expected = {f.path: f for f in manifest.files if selected is None or f.path in selected}
    actual: dict[str, zipfile.ZipInfo] = {}
    seen: set[str] = set()
    for info in archive.infolist():
        if info.is_dir():
            dirname = info.filename.rstrip("/")
            # Only directory entries along the expected package tree.
            if dirname and not any(p.startswith(dirname + "/") for p in expected):
                raise UpdateError("Unexpected directory in archive")
            continue
        try:
            path = valid_path(info.filename)
        except ManifestError as exc:
            raise UpdateError("Unsafe archive path") from exc
        key = path.casefold()
        if key in seen or path not in expected:
            raise UpdateError("Unexpected/duplicate archive entry")
        seen.add(key)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not stat.S_ISREG(mode)):
            raise UpdateError("Archive links and device files are forbidden")
        if info.file_size != expected[path].size or info.flag_bits & 0x1:
            raise UpdateError("Archive size mismatch or encrypted content")
        actual[path] = info
    if set(actual) != set(expected):
        raise UpdateError("Release archive missing required files")
    return actual


def _copy_unchanged_verified(source: Path, destination: Path, entry: ReleaseFile,
                             progress: Callable[[int], None] | None = None) -> None:
    """Copy one unchanged delta file and verify its SHA-256 in the same pass.

    The old two-pass flow hashed the full source and then read it again for a
    copy. We still verify every copied byte before the transaction commits.
    """
    try:
        if (source.is_symlink() or not source.is_file()
                or source.stat().st_size != entry.size):
            raise UpdateError("Unchanged base file was modified or missing")
        digest = hashlib.sha256()
        copied = 0
        with source.open("rb") as original, destination.open("xb") as output:
            for block in iter(lambda: original.read(1024 * 1024), b""):
                copied += len(block)
                if copied > entry.size:
                    raise UpdateError("Unchanged base file exceeded manifest size")
                digest.update(block)
                output.write(block)
                if progress is not None:
                    progress(copied)
        if copied != entry.size or digest.hexdigest() != entry.sha256:
            raise UpdateError("Unchanged base file was modified or missing")
    except OSError as exc:
        raise UpdateError("Unchanged base file cannot be copied safely") from exc


def install_release(root: Path, archive_path: Path, manifest: ReleaseManifest,
                    progress: Progress | None = None, *, delta: bool = False) -> bool:
    """Stage, verify every byte, then atomically activate the new version.

    Returns False if this exact version is already installed/active.
    """
    if manifest.schema_version != 1:
        raise UpdateError("Unsupported data schema; updater upgrade required")
    state = read_state(root)
    if delta:
        if (manifest.delta is None or state.get("pending")
                or state.get("source_sha") != manifest.delta.base_source_sha
                or not state.get("active")):
            raise UpdateError("Local base does not match differential release")
    slot = f"{manifest.app_version}-{manifest.source_sha[:12]}".replace("+", "_")
    same_active = state.get("active") == slot
    if same_active:
        current = slot_path(root, slot)
        if current.is_dir() and all(verify_file(current / item.path, item) for item in manifest.files):
            return False
        # A missing or corrupt active slot is rebuilt in a fresh stage below.
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    target = slot_path(root, slot)
    stage = Path(tempfile.mkdtemp(prefix=".atlas-install-", dir=root))
    try:
        with zipfile.ZipFile(archive_path) as package:
            entries = _validate_archive(package, manifest,
                                        set(manifest.delta.paths) if delta else None)
            total = sum(f.size for f in manifest.files)
            done = 0
            last_percent = -1

            def report_copied(complete: int) -> None:
                nonlocal last_percent
                # At most 101 events, including progress inside large unchanged
                # files. This avoids flooding the Tk queue on multi-GB deltas.
                percent = min(100, complete * 100 // max(total, 1))
                if progress is not None and percent > last_percent:
                    last_percent = percent
                    progress(complete, total)

            for entry in manifest.files:
                destination = stage / entry.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                if delta and entry.path not in entries:
                    old = slot_path(root, state["active"]) / entry.path
                    _copy_unchanged_verified(
                        old, destination, entry,
                        lambda copied: report_copied(done + copied),
                    )
                    done += entry.size
                    report_copied(done)
                    continue
                digest = hashlib.sha256()
                count = 0
                with package.open(entries[entry.path]) as source, destination.open("xb") as output:
                    while True:
                        part = source.read(1024 * 1024)
                        if not part:
                            break
                        count += len(part)
                        if count > entry.size:
                            raise UpdateError("Decompressed file exceeds manifest limit")
                        output.write(part)
                        digest.update(part)
                        done += len(part)
                        report_copied(done)
                if count != entry.size or digest.hexdigest() != entry.sha256:
                    raise UpdateError("Release file SHA-256 validation failed")
        if not (stage / manifest.entrypoint).is_file():
            raise UpdateError("Missing packaged application")
        if target.exists():
            if same_active:
                quarantine = root / "quarantine"
                quarantine.mkdir(parents=True, exist_ok=True)
                damaged = quarantine / (slot + "." + next(tempfile._get_candidate_names()))
                os.replace(target, damaged)
                try:
                    os.replace(stage, target)
                except OSError:
                    os.replace(damaged, target)
                    raise
            elif not target.is_dir() or any(not verify_file(target / e.path, e) for e in manifest.files):
                raise UpdateError("Conflicting existing installation slot")
        else:
            os.replace(stage, target)
        prior = state.get("previous") if same_active else state.get("active")
        old_meta = state.get("previous_metadata") if same_active else {
            key: state[key] for key in ("app_version", "data_version", "schema_version", "source_sha",
                                  "entrypoint_size", "entrypoint_sha256")
            if key in state
        }
        old_entrypoint = state.get("previous_entrypoint") if same_active else state.get("entrypoint")
        _write_state(root, {
            "active": slot, "previous": prior, "pending": True,
            "entrypoint": manifest.entrypoint,
            "previous_entrypoint": old_entrypoint if prior else None,
            "app_version": manifest.app_version,
            "data_version": manifest.data_version,
            "schema_version": manifest.schema_version,
            "source_sha": manifest.source_sha,
            "entrypoint_size": next(e.size for e in manifest.files if e.path == manifest.entrypoint),
            "entrypoint_sha256": next(e.sha256 for e in manifest.files if e.path == manifest.entrypoint),
            "previous_metadata": old_meta or {},
        })
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("Release extraction failed") from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return True
