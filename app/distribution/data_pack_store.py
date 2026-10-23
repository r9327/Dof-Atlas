"""Transactional, independent Atlas data-pack store.

This does not alter the running EXE or the user's progress, favourites or
character profiles. Publishing a pack makes it active in this store ONLY;
runtime catalogue adoption needs a separate versioned reader/migration gate.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .data_pack_plan import (
    DataPack, InstalledPack, InvalidDataPack, _check_pack, _check_state,
    plan_pack_updates,
)
from .data_pack_verify import verify_staged_pack

_KINDS = frozenset({"quests", "successes", "guides", "items", "equipment"})
_CHUNK = 1024 * 1024
_SCHEMA = "atlas-pack-store/v1"


def _dir(root: Path) -> Path:
    if not isinstance(root, Path) or root.is_symlink():
        raise InvalidDataPack("unsafe pack store root")
    directory = root / "data-pack-store"
    if directory.is_symlink():
        raise InvalidDataPack("unsafe pack store directory")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _blob(directory: Path, kind: str, state: InstalledPack) -> Path:
    path = directory / "versions" / kind / f"{state.revision}-{state.sha256}.blob"
    if not path.resolve().is_relative_to(directory.resolve()):
        raise InvalidDataPack("pack path escaped store")
    return path


def _read(directory: Path) -> dict:
    path = directory / "state.json"
    if path.is_symlink():
        raise InvalidDataPack("unsafe pack index")
    if not path.exists():
        return {"schema": _SCHEMA, "packs": {}}
    if path.stat().st_size > 64 * 1024:
        raise InvalidDataPack("pack index too large")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise InvalidDataPack("corrupt pack index") from exc
    if not isinstance(document, dict) or set(document) != {"schema", "packs"}:
        raise InvalidDataPack("invalid pack index")
    if document["schema"] != _SCHEMA or not isinstance(document["packs"], dict):
        raise InvalidDataPack("unsupported pack index schema")
    for kind, entry in document["packs"].items():
        if kind not in _KINDS or not isinstance(entry, dict) or set(entry) != {"active", "previous", "pending"}:
            raise InvalidDataPack("invalid pack index entry")
        if type(entry["pending"]) is not bool:
            raise InvalidDataPack("invalid pending flag")
        for key in ("active", "previous"):
            item = entry[key]
            if item is not None:
                if not isinstance(item, dict) or set(item) != {"revision", "schema_version", "sha256"}:
                    raise InvalidDataPack("invalid stored pack identity")
                _check_state(InstalledPack(**item))
    return document


def _write(directory: Path, state: dict) -> None:
    fd, filename = tempfile.mkstemp(prefix=".pack-index-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(filename, directory / "state.json")
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


@contextmanager
def _locked(directory: Path):
    """Single-process critical section across Windows and POSIX pack writers."""
    lock = directory / ".pack-store.lock"
    if lock.is_symlink():
        raise InvalidDataPack("unsafe pack lock")
    with lock.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InvalidDataPack("concurrent pack update refused") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _identity(state: InstalledPack) -> dict:
    return {"revision": state.revision, "schema_version": state.schema_version,
            "sha256": state.sha256}


def _state(item: dict | None) -> InstalledPack | None:
    return None if item is None else InstalledPack(**item)


def _check_blob(path: Path, identity: InstalledPack) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    digest = sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(data)
    return digest.hexdigest() == identity.sha256


def active_pack(root: Path, kind: str) -> Path | None:
    """Return the verified *store* blob, not a runtime catalogue pathname."""
    if kind not in _KINDS:
        raise InvalidDataPack("unknown pack kind")
    directory = _dir(root)
    document = _read(directory)
    entry = document["packs"].get(kind)
    if not entry or entry["active"] is None:
        return None
    current = _state(entry["active"])
    assert current is not None
    path = _blob(directory, kind, current)
    if not _check_blob(path, current):
        raise InvalidDataPack("active data pack is missing or corrupt")
    return path



def accepted_pack(root: Path, kind: str) -> Path | None:
    """Only expose acknowledged, checksum-verified pack bytes to app readers.

    A newly downloaded or staged pack is NOT an active catalog merely because
    its blob exists. Readers cannot see pending updates awaiting smoke tests.
    """
    if kind not in _KINDS:
        raise InvalidDataPack("unknown pack kind")
    if not isinstance(root, Path) or root.is_symlink():
        raise InvalidDataPack("unsafe pack store root")
    directory = root / "data-pack-store"
    if directory.is_symlink():
        raise InvalidDataPack("unsafe pack store directory")
    if not (directory / "state.json").exists():
        return None
    doc = _read(directory)
    row = doc["packs"].get(kind)
    if not row or row["pending"] or row["active"] is None:
        return None
    record = _state(row["active"])
    assert record is not None
    blob = _blob(directory, kind, record)
    if not _check_blob(blob, record):
        raise InvalidDataPack("acknowledged data pack is corrupt")
    return blob


def install_pack(root: Path, staging_root: Path, pack: DataPack) -> str:
    """Copy verified bytes into an immutable version, then atomically switch.

    Returns INSTALLED or ALREADY_ACTIVE. Staged input remains unchanged.
    Explicit acknowledge_pack or rollback_pack is required before next update.
    """
    _check_pack(pack)
    verify_staged_pack(pack, staging_root)
    directory = _dir(root)
    with _locked(directory):
        doc = _read(directory)
        existing = doc["packs"].get(pack.kind)
        current = _state(existing["active"]) if existing else None
        if existing and existing["pending"]:
            raise InvalidDataPack("previous pack update awaits health validation")
        next_state = InstalledPack(pack.revision, pack.schema_version, pack.sha256)
        action = plan_pack_updates({pack.kind: current} if current else {}, [pack])[0]
        if action.action == "keep":
            if not _check_blob(_blob(directory, pack.kind, next_state), next_state):
                raise InvalidDataPack("active pack is corrupt, repair required")
            return "ALREADY_ACTIVE"
        target = _blob(directory, pack.kind, next_state)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise InvalidDataPack("unsafe target pack blob")
        if not _check_blob(target, next_state):
            # Do not overwrite a corrupt existing immutable version: fail closed.
            if target.exists():
                raise InvalidDataPack("corrupt immutable target pack")
            fd, temp_name = tempfile.mkstemp(prefix=".pack-", dir=target.parent)
            try:
                copied = sha256()
                with os.fdopen(fd, "wb") as out, (staging_root / pack.artifact_path).open("rb") as stream:
                    for block in iter(lambda: stream.read(_CHUNK), b""):
                        copied.update(block)
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                if copied.hexdigest() != pack.sha256:
                    raise InvalidDataPack("staged source changed during pack copy")
                os.replace(temp_name, target)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        doc["packs"][pack.kind] = {
            "active": _identity(next_state),
            "previous": _identity(current) if current else None,
            "pending": True,
        }
        _write(directory, doc)
        return "INSTALLED"


def acknowledge_pack(root: Path, kind: str) -> bool:
    """Trusted runtime smoke-test caller confirms this newly activated pack."""
    if kind not in _KINDS:
        raise InvalidDataPack("unknown pack kind")
    directory = _dir(root)
    with _locked(directory):
        doc = _read(directory)
        entry = doc["packs"].get(kind)
        if not entry or not entry["pending"]:
            return False
        current = _state(entry["active"])
        if current is None or not _check_blob(_blob(directory, kind, current), current):
            raise InvalidDataPack("cannot acknowledge a corrupt pack")
        entry["pending"] = False
        entry["previous"] = None
        _write(directory, doc)
        return True


def rollback_pack(root: Path, kind: str) -> bool:
    """Restore the last verified pack after a failed runtime acceptance."""
    if kind not in _KINDS:
        raise InvalidDataPack("unknown pack kind")
    directory = _dir(root)
    with _locked(directory):
        doc = _read(directory)
        entry = doc["packs"].get(kind)
        if not entry or not entry["pending"]:
            return False
        previous = _state(entry["previous"])
        if previous and not _check_blob(_blob(directory, kind, previous), previous):
            raise InvalidDataPack("rollback pack is corrupt")
        entry["active"] = _identity(previous) if previous else None
        entry["previous"] = None
        entry["pending"] = False
        _write(directory, doc)
        return True



def recover_pending_packs(root: Path) -> tuple[str, ...]:
    """Rollback all unacknowledged data-pack updates after interrupted startup.

    Validate *every* previous blob before changing the index, so one corrupt
    baseline cannot silently leave a partially recovered pack collection.
    This is an explicit launcher recovery operation, not an implicit UI import.
    """
    directory = _dir(root)
    with _locked(directory):
        doc = _read(directory)
        pending = tuple(sorted(
            kind for kind, entry in doc["packs"].items() if entry["pending"]
        ))
        if not pending:
            return ()
        for kind in pending:
            old = _state(doc["packs"][kind]["previous"])
            if old is not None and not _check_blob(_blob(directory, kind, old), old):
                raise InvalidDataPack(f"cannot recover {kind}: previous pack is missing or corrupt")
        for kind in pending:
            entry = doc["packs"][kind]
            old = _state(entry["previous"])
            entry["active"] = _identity(old) if old is not None else None
            entry["previous"] = None
            entry["pending"] = False
        _write(directory, doc)
        return pending
