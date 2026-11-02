"""Atomic candidate bundle storage for independently prepared Atlas guide routes.

This module NEVER writes into installed Atlas data, the Guide manifest, or
character progress. It does not activate a runtime route or claim certification.
It preserves multiple immutable candidates and an atomic local selection pointer.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    GuideRouteContractError,
)

_FORMAT = "atlas-guide-candidate-store/v1"
_ROOT_MARKER = ".atlas-guide-candidates-v1.json"
_SELECTED = "selected.json"
_FORBIDDEN_PARTS = frozenset({".git", ".cache", "data", "saves", "profiles", "user_data"})
_NO_SELECTION = "NONE"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_candidate(preview: dict[str, Any]) -> None:
    if not isinstance(preview, dict):
        raise GuideRouteContractError("preview must be a JSON object")
    if preview.get("schema_version") != 1 or preview.get("mode") != "DRY_RUN_ONLY":
        raise GuideRouteContractError("preview must come from the dry-run importer")
    if preview.get("status") != "PREVIEW_ONLY_NOT_CERTIFIED" or preview.get("certified") is not False:
        raise GuideRouteContractError("candidate must remain NOT_CERTIFIED")
    source_hash = preview.get("source_sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64 or any(
        char not in "0123456789abcdef" for char in source_hash
    ):
        raise GuideRouteContractError("missing source SHA-256")
    routes = preview.get("routes")
    if not isinstance(routes, list) or not routes:
        raise GuideRouteContractError("nonempty projected routes required")
    ids: set[str] = set()
    count = 0
    for route in routes:
        if not isinstance(route, dict) or route.get("source_compliance") != "NOT_CERTIFIED":
            raise GuideRouteContractError("route cannot claim certification")
        identifier = route.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("source_guide:"):
            raise GuideRouteContractError("invalid candidate route ID")
        if identifier in ids:
            raise GuideRouteContractError("duplicate candidate route")
        ids.add(identifier)
        steps = route.get("steps")
        if not isinstance(steps, list) or not steps:
            raise GuideRouteContractError("route without steps")
        keys: set[str] = set()
        for step in steps:
            if not isinstance(step, dict):
                raise GuideRouteContractError("invalid projected step")
            key = step.get("manual_stage_id")
            if not isinstance(key, str) or not key.startswith("source:") or key in keys:
                raise GuideRouteContractError("missing/duplicate stable stage identity")
            keys.add(key)
        count += len(steps)
    if preview.get("guide_count") != len(routes) or preview.get("step_count") != count:
        raise GuideRouteContractError("preview coverage mismatch")
    if preview.get("is_partial") is not True:
        if preview.get("guide_count") != preview.get("expected_guide_count"):
            raise GuideRouteContractError("incomplete full guide inventory")
        if preview.get("step_count") != preview.get("expected_step_count"):
            raise GuideRouteContractError("incomplete full step inventory")


def _safe_root(root: Path) -> Path:
    candidate = Path(root).absolute()
    if candidate.is_symlink() or any(part in _FORBIDDEN_PARTS for part in candidate.parts):
        raise GuideRouteContractError("candidate root must not be an Atlas data/save/cache directory")
    if candidate.is_file():
        raise GuideRouteContractError("candidate root is a file")
    for parent in candidate.parents:
        if parent.is_symlink():
            raise GuideRouteContractError("symlinked parent is not supported")
    return candidate


def _sync_file(path: Path, contents: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_file(path: Path, content: bytes) -> None:
    # Same directory guarantees a same-volume os.replace on Windows.
    fd, name = tempfile.mkstemp(prefix=".atlas-stage-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise GuideRouteContractError(f"invalid store file: {path.name}: {exc}") from exc
    if not isinstance(result, dict):
        raise GuideRouteContractError(f"invalid store JSON object: {path.name}")
    return result


@contextmanager
def _locked(root: Path) -> Iterator[Path]:
    root = _safe_root(root)
    # No implicit adoption of existing directories with arbitrary user data.
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
    if not root.is_dir():
        raise GuideRouteContractError("candidate store is not a directory")
    marker = root / _ROOT_MARKER
    if not marker.exists():
        if list(root.iterdir()):
            raise GuideRouteContractError("unmanaged nonempty candidate directory")
        _sync_file(marker, _json_bytes({"format": _FORMAT, "runtime_activation": False}))
    if _read_json(marker) != {"format": _FORMAT, "runtime_activation": False}:
        raise GuideRouteContractError("wrong candidate directory marker")
    lock = root / ".writer.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise GuideRouteContractError("concurrent publisher or interrupted write: manual review required") from exc
    try:
        yield root
    finally:
        # Only the owner of a successfully created lock removes it.
        lock.rmdir()


def _selection(root: Path) -> str:
    path = root / _SELECTED
    if not path.exists():
        return _NO_SELECTION
    doc = _read_json(path)
    value = doc.get("candidate_sha256")
    if doc.get("format") != _FORMAT or doc.get("runtime_activation") is not False:
        raise GuideRouteContractError("invalid selection marker")
    if not isinstance(value, str) or (value != _NO_SELECTION and (
        len(value) != 64 or any(x not in "0123456789abcdef" for x in value)
    )):
        raise GuideRouteContractError("invalid selection digest")
    return value


def _candidate_file(root: Path, digest: str) -> Path:
    return root / "generations" / (digest + ".json")


def _verify_generation(root: Path, digest: str) -> None:
    if digest == _NO_SELECTION:
        return
    path = _candidate_file(root, digest)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise GuideRouteContractError(f"missing candidate generation: {digest}") from exc
    if _digest(payload) != digest:
        raise GuideRouteContractError(f"candidate generation SHA mismatch: {digest}")
    _validate_candidate(_read_json(path))


def publish_candidate(
    preview: dict[str, Any],
    *,
    root: Path,
    expected_selected: str = _NO_SELECTION,
) -> dict[str, Any]:
    """Immutable candidate + atomic CAS selection; not a live Atlas install.

    The expected selection must be from a fresh call to selected_candidate()
    or explicitly NONE when initializing. A stale selection fails closed.
    """
    _validate_candidate(preview)
    if not isinstance(expected_selected, str):
        raise GuideRouteContractError("expected_selected must be a digest or NONE")
    payload = _json_bytes(preview)
    digest = _digest(payload)
    with _locked(root) as store:
        old = _selection(store)
        _verify_generation(store, old)
        if old != expected_selected:
            raise GuideRouteContractError("stale candidate selection; compare-and-swap rejected")
        folder = store / "generations"
        folder.mkdir(exist_ok=True)
        target = _candidate_file(store, digest)
        if target.exists():
            _verify_generation(store, digest)
        else:
            # An immutable generation is visible before the selection pointer;
            # a crash leaves an orphan that can be safely resumed/inspected.
            _sync_file(target, payload)
        _atomic_file(store / _SELECTED, _json_bytes({
            "format": _FORMAT, "candidate_sha256": digest,
            "runtime_activation": False,
        }))
    return {
        "status": "CANDIDATE_STORED_NOT_ACTIVE",
        "candidate_sha256": digest, "previous_sha256": old,
        "certified": False, "runtime_activation": False,
    }


def selected_candidate(root: Path) -> str:
    """Read and verify a managed selection; reject any invalid/foreign directory."""
    root = _safe_root(root)
    marker = _read_json(root / _ROOT_MARKER)
    if marker != {"format": _FORMAT, "runtime_activation": False}:
        raise GuideRouteContractError("not a candidate store")
    value = _selection(root)
    _verify_generation(root, value)
    return value


def rollback_candidate(
    *,
    root: Path,
    expected_selected: str,
    restore_sha256: str = _NO_SELECTION,
) -> dict[str, Any]:
    """CAS rollback of the candidate selection only, never character progress."""
    with _locked(root) as store:
        actual = _selection(store)
        if actual != expected_selected:
            raise GuideRouteContractError("stale rollback; selection changed")
        if restore_sha256 != _NO_SELECTION:
            _verify_generation(store, restore_sha256)
        _atomic_file(store / _SELECTED, _json_bytes({
            "format": _FORMAT, "candidate_sha256": restore_sha256,
            "runtime_activation": False,
        }))
    return {"status": "CANDIDATE_ROLLED_BACK_NOT_ACTIVE",
            "candidate_sha256": restore_sha256, "certified": False}


__all__ = ["publish_candidate", "selected_candidate", "rollback_candidate"]
