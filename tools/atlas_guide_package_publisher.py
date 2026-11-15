"""Fail-closed, one-guide packaging of an already staged Guide candidate.

This is a delivery *preparer*, NOT a certification authority or live installer.
The trusted host must supply and continuously maintain an independent final
certificate witness. A generated JSON file and its hash cannot authorize itself.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.services.guide_trusted_source_package import (
    GuidePackageBlocked,
    GuidePackageEntry,
    GuideTrustedSourcePackage,
    Witness,
    _MAX_ROUTE_BYTES,
    _json_bytes,
    _no_duplicate_keys,
    _reject_constant,
    _redirected,
)
from tools.atlas_guide_candidate_store import (
    _safe_root,
    read_selected_preview,
)

TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-package-publisher",
    "role": "guide_trusted_delivery_preparer",
    "capabilities": ["guide", "validation"],
    "modes": ["trusted_host_api_only", "single_guide_atomic_unmounted_package"],
    "cost_hint": "variable",
    "side_effects": "repo_mutation_explicit",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_atlas_guide_package_publisher"],
    "target_scopes": ["encyclopedia_guide"],
}


class GuidePackagePublishBlocked(ValueError):
    """No independently verified, intact and unambiguous delivery is possible."""


_INSTALL_FORMAT = 1
_INSTALL_MARKER = "atlas-guide-install-v1.json"
_INSTALL_SELECTED = "selected.json"
_INSTALL_GENERATIONS = "generations"
_INSTALL_LOCK = ".install.lock"
_NO_INSTALL = "NONE"


def _entry_payload(entry: GuidePackageEntry) -> dict[str, str]:
    return {
        "guide_id": entry.guide_id,
        "filename": entry.filename,
        "sha256": entry.sha256,
        "source_sha256": entry.source_sha256,
        "head_sha": entry.head_sha,
        "certificate_ref": entry.certificate_ref,
    }


def _strict_document(path: Path, *, limit: int = 16 * 1024) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > limit:
            raise GuidePackagePublishBlocked("Invalid installed package metadata size")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except GuidePackagePublishBlocked:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise GuidePackagePublishBlocked("Invalid installed package metadata") from exc
    if not isinstance(value, dict):
        raise GuidePackagePublishBlocked("Installed package metadata must be an object")
    return value


def _atomic_document(path: Path, payload: dict[str, Any]) -> None:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _selection_payload(selected: str, entry: GuidePackageEntry | None) -> dict[str, Any]:
    return {
        "format": _INSTALL_FORMAT,
        "selected_sha256": selected,
        "entry": _entry_payload(entry) if entry is not None else None,
        "runtime_activation": False,
    }


def _checked_install_sha(value: str, label: str) -> str:
    if value == _NO_INSTALL:
        return value
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            or value == "0" * 64):
        raise GuidePackagePublishBlocked(f"Invalid {label}")
    return value


def _read_selection(root: Path) -> tuple[str, GuidePackageEntry | None]:
    payload = _strict_document(root / _INSTALL_SELECTED)
    if (set(payload) != {
                "format", "selected_sha256", "entry", "runtime_activation",
            }
            or payload.get("format") != _INSTALL_FORMAT
            or payload.get("runtime_activation") is not False):
        raise GuidePackagePublishBlocked("Invalid installed selection contract")
    selected = _checked_install_sha(payload.get("selected_sha256"), "installed selection")
    raw_entry = payload.get("entry")
    if selected == _NO_INSTALL:
        if raw_entry is not None:
            raise GuidePackagePublishBlocked("Empty selection cannot carry a package entry")
        return selected, None
    if not isinstance(raw_entry, dict):
        raise GuidePackagePublishBlocked("Installed selection is missing its package entry")
    try:
        entry = GuidePackageEntry(**raw_entry)
    except (TypeError, GuidePackageBlocked) as exc:
        raise GuidePackagePublishBlocked("Invalid installed package entry") from exc
    if not hmac.compare_digest(selected, entry.sha256):
        raise GuidePackagePublishBlocked("Installed selection and package digest differ")
    return selected, entry


def _managed_install_root(path: Path, *, initialize: bool) -> Path:
    try:
        root = _safe_root(path)
    except (OSError, ValueError) as exc:
        raise GuidePackagePublishBlocked("Unsafe installed package root") from exc
    if _redirected(root) or _redirected(root.parent) or not root.parent.is_dir():
        raise GuidePackagePublishBlocked("Installed package root is redirected or unavailable")
    if not root.exists():
        if not initialize:
            raise GuidePackagePublishBlocked("Installed package root is missing")
        root.mkdir(exist_ok=False)
        (root / _INSTALL_GENERATIONS).mkdir()
        _atomic_document(root / _INSTALL_MARKER, {
            "format": _INSTALL_FORMAT, "runtime_activation": False,
        })
        _atomic_document(
            root / _INSTALL_SELECTED,
            _selection_payload(_NO_INSTALL, None),
        )
    marker = _strict_document(root / _INSTALL_MARKER)
    if marker != {"format": _INSTALL_FORMAT, "runtime_activation": False}:
        raise GuidePackagePublishBlocked("Foreign installed package root")
    generations = root / _INSTALL_GENERATIONS
    if (any(_redirected(root / name) for name in (_INSTALL_MARKER, _INSTALL_SELECTED))
            or not generations.is_dir() or _redirected(generations)):
        raise GuidePackagePublishBlocked("Installed generations directory is unavailable")
    allowed = {_INSTALL_MARKER, _INSTALL_SELECTED, _INSTALL_GENERATIONS, _INSTALL_LOCK}
    if any(child.name not in allowed for child in root.iterdir()):
        raise GuidePackagePublishBlocked("Foreign file in installed package root")
    return root


@contextmanager
def _install_locked(root: Path):
    lock = root / _INSTALL_LOCK
    descriptor: int | None = None
    acquired = False
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        acquired = True
        os.write(descriptor, b"atlas-guide-install-v1")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        yield
    except FileExistsError as exc:
        raise GuidePackagePublishBlocked("Installed package transaction already running") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if acquired:
            lock.unlink(missing_ok=True)


def _verify_installed_generation(
    root: Path, selected: str, entry: GuidePackageEntry | None,
    *, build_head_sha: str, witness: Witness | None,
) -> dict[str, Any] | None:
    if selected == _NO_INSTALL:
        if entry is not None:
            raise GuidePackagePublishBlocked("Empty installed selection has an entry")
        return None
    if entry is None or not hmac.compare_digest(selected, entry.sha256):
        raise GuidePackagePublishBlocked("Installed generation entry mismatch")
    generation = root / _INSTALL_GENERATIONS / selected
    entry_file = generation / "entry.json"
    if _redirected(generation) or _redirected(entry_file):
        raise GuidePackagePublishBlocked("Installed generation metadata is redirected")
    stored_entry = _strict_document(entry_file)
    if stored_entry != _entry_payload(entry):
        raise GuidePackagePublishBlocked("Installed generation metadata changed")
    try:
        return GuideTrustedSourcePackage(
            generation, {entry.guide_id: entry},
            build_head_sha=build_head_sha, witness=witness,
        ).load_route(entry.guide_id)
    except (GuidePackageBlocked, OSError, ValueError) as exc:
        raise GuidePackagePublishBlocked("Installed generation verification failed") from exc


def selected_installed_guide_package(
    *, install_root: Path, build_head_sha: str, witness: Witness | None,
) -> dict[str, Any]:
    """Read and independently verify the currently installed inactive package."""
    root = _managed_install_root(install_root, initialize=False)
    selected, entry = _read_selection(root)
    _verify_installed_generation(
        root, selected, entry, build_head_sha=build_head_sha, witness=witness,
    )
    return {
        "status": "NO_PACKAGE_INSTALLED" if selected == _NO_INSTALL else "PACKAGE_INSTALLED_NOT_ACTIVATED",
        "selected_sha256": selected,
        "entry": _entry_payload(entry) if entry is not None else None,
        "certified": False,
        "runtime_activation": False,
    }


def _approved(entry: GuidePackageEntry, witness: Witness | None) -> bool:
    if not callable(witness):
        return False
    try:
        return witness(
            entry.guide_id, entry.sha256, entry.source_sha256,
            entry.head_sha, entry.certificate_ref,
        ) is True
    except Exception:
        return False


def prepare_attested_guide_package(
    *,
    candidate_root: Path,
    expected_selected: str,
    route_id: str,
    destination: Path,
    build_head_sha: str,
    certificate_ref: str,
    witness: Witness | None,
) -> dict[str, Any]:
    """Prepare ONE new versioned package, without mounting it in Atlas.

    The source candidate is read by its exact CAS selection. A separate
    independent witness must authenticate the *final* certificate and exact
    exported route, not merely a source JSON field. The package remains
    inactive and uncertified as an Atlas delivery until a trusted application
    composition and Windows/DOFUS review independently accept it.

    Destination must be a fresh dedicated directory, outside source/data/user
    trees (or under disposable repository artifacts/). Never replaces an
    existing directory, route, saved character or installed Guide catalogue.
    """
    if not callable(witness):
        raise GuidePackagePublishBlocked("Independent final certificate witness required")
    try:
        preview = read_selected_preview(
            root=candidate_root, expected_selected=expected_selected,
        )
    except (OSError, ValueError) as exc:
        raise GuidePackagePublishBlocked("Candidate is absent, stale or corrupted") from exc
    if (preview.get("is_partial") is not False
            or preview.get("guide_count") != 1
            or preview.get("expected_guide_count") != 1
            or not isinstance(preview.get("routes"), list)
            or len(preview["routes"]) != 1):
        raise GuidePackagePublishBlocked("Exactly one complete staged guide required")
    route = preview["routes"][0]
    if not isinstance(route, dict) or route.get("id") != route_id:
        raise GuidePackagePublishBlocked("Explicit route identity differs from staged guide")
    source_sha = preview.get("source_sha256")
    if not isinstance(source_sha, str) or source_sha == "0" * 64:
        raise GuidePackagePublishBlocked("Missing pinned source inventory")
    try:
        content = _json_bytes(route)
    except (TypeError, ValueError, RecursionError) as exc:
        raise GuidePackagePublishBlocked("Invalid projected package JSON") from exc
    if not content or len(content) > _MAX_ROUTE_BYTES:
        raise GuidePackagePublishBlocked("Projected route is empty or exceeds 16 MiB")
    if not isinstance(route_id, str) or not route_id.startswith("source_guide:"):
        raise GuidePackagePublishBlocked("Canonical route identity required")
    filename = route_id.removeprefix("source_guide:") + ".json"
    try:
        entry = GuidePackageEntry(
            guide_id=route_id, filename=filename,
            sha256=hashlib.sha256(content).hexdigest(),
            source_sha256=source_sha,
            head_sha=build_head_sha, certificate_ref=certificate_ref,
        )
    except GuidePackageBlocked as exc:
        raise GuidePackagePublishBlocked("Invalid trusted certificate binding") from exc
    if not _approved(entry, witness):
        raise GuidePackagePublishBlocked("Independent final certificate missing or revoked")

    # _safe_root refuses source tree writes, protected app/save paths, redirected
    # Windows junction parents, and lexical '..' before any directory is made.
    try:
        package_root = _safe_root(destination)
        source_root = _safe_root(candidate_root)
    except (OSError, ValueError) as exc:
        raise GuidePackagePublishBlocked("Unsafe package or candidate destination") from exc
    if (package_root == source_root or package_root.is_relative_to(source_root)
            or source_root.is_relative_to(package_root)):
        raise GuidePackagePublishBlocked("Cannot package inside or over the candidate store")
    if (_redirected(package_root) or package_root.exists()
            or not package_root.parent.is_dir()):
        raise GuidePackagePublishBlocked("Package destination must be a new dedicated directory")

    # Preflight the exact authored content with the existing shared-runtime
    # trust boundary, on a disposable sibling volume and no live registration.
    scratch = Path(tempfile.mkdtemp(
        prefix=".atlas-guide-package-", dir=package_root.parent,
    ))
    created_destination = False
    try:
        file = scratch / entry.filename
        with file.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        checked = GuideTrustedSourcePackage(
            scratch, {route_id: entry},
            build_head_sha=build_head_sha, witness=witness,
        ).load_route(route_id)
        if checked != route:
            raise GuidePackagePublishBlocked("Packaged route differs from the pinned source")
        # The witness may run arbitrary external code. Ensure selection remains
        # exactly pinned after callbacks, before the first public write.
        if read_selected_preview(
            root=candidate_root, expected_selected=expected_selected,
        ) != preview or not _approved(entry, witness):
            raise GuidePackagePublishBlocked("Source selection or certificate changed")
        # mkdir(exist_ok=False) is an atomic, no-clobber claim on Windows and
        # POSIX. Renaming a directory could silently replace an EMPTY existing
        # directory on POSIX, so never use os.replace for the destination.
        package_root.mkdir(exist_ok=False)
        created_destination = True
        if _redirected(package_root) or _redirected(package_root.parent):
            raise GuidePackagePublishBlocked("Package destination was redirected")
        os.replace(file, package_root / entry.filename)
        verified = GuideTrustedSourcePackage(
            package_root, {route_id: entry},
            build_head_sha=build_head_sha, witness=witness,
        ).load_route(route_id)
        if verified != route or read_selected_preview(
            root=candidate_root, expected_selected=expected_selected,
        ) != preview or not _approved(entry, witness):
            raise GuidePackagePublishBlocked("Post-publication package evidence changed")
        # A two-stage marker is deliberately not treated as a certificate.
        # The trusted host must independently supply entry + revocable witness
        # to the app and must separately authorize actual installation.
        return {
            "status": "PACKAGE_PREPARED_NOT_INSTALLED",
            "certified": False,
            "runtime_activation": False,
            "candidate_sha256": expected_selected,
            "source_sha256": source_sha,
            "package_sha256": entry.sha256,
            "route_id": route_id,
            "destination": str(package_root),
            "entry": {
                "guide_id": entry.guide_id,
                "filename": entry.filename,
                "sha256": entry.sha256,
                "source_sha256": entry.source_sha256,
                "head_sha": entry.head_sha,
                "certificate_ref": entry.certificate_ref,
            },
        }
    except (OSError, ValueError, TypeError) as exc:
        if created_destination:
            try:
                # The directory was exclusively created by this call.
                shutil.rmtree(package_root)
            except OSError as cleanup_error:
                raise GuidePackagePublishBlocked(
                    "Partial package cleanup failed; manual review required"
                ) from cleanup_error
        if isinstance(exc, GuidePackagePublishBlocked):
            raise
        raise GuidePackagePublishBlocked("Atomic package preparation refused") from exc
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def install_attested_guide_package(
    *,
    prepared: dict[str, Any],
    install_root: Path,
    expected_selected: str = _NO_INSTALL,
    build_head_sha: str,
    witness: Witness | None,
) -> dict[str, Any]:
    """Transactionally install one prepared package without activating it.

    The dedicated install root is versioned and CAS-selected. Installation
    never writes Guide progress, data routes, saves, or either optimized Guide.
    A post-install load through the canonical trusted reader is mandatory. Any
    failure after pointer publication restores and verifies the old selection.
    """
    _checked_install_sha(expected_selected, "expected installed selection")
    if (not isinstance(prepared, dict)
            or prepared.get("status") != "PACKAGE_PREPARED_NOT_INSTALLED"
            or prepared.get("certified") is not False
            or prepared.get("runtime_activation") is not False):
        raise GuidePackagePublishBlocked("A fresh inactive prepared package is required")
    raw_entry = prepared.get("entry")
    try:
        entry = GuidePackageEntry(**raw_entry) if isinstance(raw_entry, dict) else None
    except (TypeError, GuidePackageBlocked) as exc:
        raise GuidePackagePublishBlocked("Prepared package entry is invalid") from exc
    if (entry is None
            or prepared.get("route_id") != entry.guide_id
            or prepared.get("package_sha256") != entry.sha256
            or prepared.get("source_sha256") != entry.source_sha256
            or not hmac.compare_digest(entry.head_sha, build_head_sha)
            or not _approved(entry, witness)):
        raise GuidePackagePublishBlocked("Prepared package evidence differs or is revoked")
    try:
        prepared_root = _safe_root(Path(prepared.get("destination", "")))
    except (OSError, TypeError, ValueError) as exc:
        raise GuidePackagePublishBlocked("Prepared package path is unsafe") from exc
    if not prepared_root.is_dir() or _redirected(prepared_root):
        raise GuidePackagePublishBlocked("Prepared package directory is unavailable")
    try:
        route = GuideTrustedSourcePackage(
            prepared_root, {entry.guide_id: entry},
            build_head_sha=build_head_sha, witness=witness,
        ).load_route(entry.guide_id)
    except (GuidePackageBlocked, OSError, ValueError) as exc:
        raise GuidePackagePublishBlocked("Prepared package verification failed") from exc

    if expected_selected != _NO_INSTALL and not Path(install_root).exists():
        raise GuidePackagePublishBlocked("Stale install selection on missing store")
    root = _managed_install_root(install_root, initialize=True)
    if (root == prepared_root or root.is_relative_to(prepared_root)
            or prepared_root.is_relative_to(root)):
        raise GuidePackagePublishBlocked("Install root and prepared package must be separate")
    generation = root / _INSTALL_GENERATIONS / entry.sha256
    created_generation = False
    with _install_locked(root):
        old_selected, old_entry = _read_selection(root)
        _verify_installed_generation(
            root, old_selected, old_entry,
            build_head_sha=build_head_sha, witness=witness,
        )
        if old_selected != expected_selected:
            raise GuidePackagePublishBlocked("Stale install selection")
        if generation.exists():
            raise GuidePackagePublishBlocked("Installed generation already exists")
        old_payload = _selection_payload(old_selected, old_entry)
        pointer_started = False
        try:
            generation.mkdir(exist_ok=False)
            created_generation = True
            source = prepared_root / entry.filename
            destination = generation / entry.filename
            with source.open("rb") as input_stream, destination.open("xb") as output_stream:
                payload = input_stream.read(_MAX_ROUTE_BYTES + 1)
                if (not payload or len(payload) > _MAX_ROUTE_BYTES
                        or not hmac.compare_digest(
                            hashlib.sha256(payload).hexdigest(), entry.sha256,
                        )):
                    raise GuidePackagePublishBlocked("Prepared route changed during installation")
                output_stream.write(payload)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            _atomic_document(generation / "entry.json", _entry_payload(entry))
            installed_route = _verify_installed_generation(
                root, entry.sha256, entry,
                build_head_sha=build_head_sha, witness=witness,
            )
            if installed_route != route or not _approved(entry, witness):
                raise GuidePackagePublishBlocked("Installed route differs or witness was revoked")
            pointer_started = True
            _atomic_document(
                root / _INSTALL_SELECTED,
                _selection_payload(entry.sha256, entry),
            )
            selected, selected_entry = _read_selection(root)
            verified = _verify_installed_generation(
                root, selected, selected_entry,
                build_head_sha=build_head_sha, witness=witness,
            )
            if selected != entry.sha256 or verified != route or not _approved(entry, witness):
                raise GuidePackagePublishBlocked("Post-installation verification failed")
        except (GuidePackagePublishBlocked, GuidePackageBlocked, OSError, ValueError) as exc:
            if pointer_started:
                try:
                    current, _current_entry = _read_selection(root)
                    if current != old_selected:
                        _atomic_document(root / _INSTALL_SELECTED, old_payload)
                    restored, restored_entry = _read_selection(root)
                    _verify_installed_generation(
                        root, restored, restored_entry,
                        build_head_sha=build_head_sha, witness=witness,
                    )
                    if restored != old_selected:
                        raise GuidePackagePublishBlocked("Install rollback selection mismatch")
                except (GuidePackagePublishBlocked, OSError, ValueError) as rollback_exc:
                    raise GuidePackagePublishBlocked(
                        "Installation and rollback verification failed; manual review required"
                    ) from rollback_exc
            if created_generation and entry.sha256 != old_selected:
                try:
                    shutil.rmtree(generation)
                except OSError as cleanup_exc:
                    raise GuidePackagePublishBlocked(
                        "Failed installed generation cleanup; manual review required"
                    ) from cleanup_exc
            if isinstance(exc, GuidePackagePublishBlocked):
                raise
            raise GuidePackagePublishBlocked("Transactional package installation failed") from exc
    return {
        "status": "PACKAGE_INSTALLED_NOT_ACTIVATED",
        "selected_sha256": entry.sha256,
        "previous_sha256": old_selected,
        "entry": _entry_payload(entry),
        "certified": False,
        "runtime_activation": False,
    }


def rollback_installed_guide_package(
    *,
    install_root: Path,
    expected_selected: str,
    restore_sha256: str = _NO_INSTALL,
    build_head_sha: str,
    witness: Witness | None,
) -> dict[str, Any]:
    """CAS rollback to a verified installed generation, never Guide progress."""
    _checked_install_sha(expected_selected, "expected installed selection")
    _checked_install_sha(restore_sha256, "restore installed selection")
    root = _managed_install_root(install_root, initialize=False)
    with _install_locked(root):
        selected, selected_entry = _read_selection(root)
        _verify_installed_generation(
            root, selected, selected_entry,
            build_head_sha=build_head_sha, witness=witness,
        )
        if selected != expected_selected:
            raise GuidePackagePublishBlocked("Stale installed rollback selection")
        restore_entry: GuidePackageEntry | None = None
        if restore_sha256 != _NO_INSTALL:
            raw = _strict_document(
                root / _INSTALL_GENERATIONS / restore_sha256 / "entry.json",
            )
            try:
                restore_entry = GuidePackageEntry(**raw)
            except (TypeError, GuidePackageBlocked) as exc:
                raise GuidePackagePublishBlocked("Rollback generation entry is invalid") from exc
            _verify_installed_generation(
                root, restore_sha256, restore_entry,
                build_head_sha=build_head_sha, witness=witness,
            )
        old_payload = _selection_payload(selected, selected_entry)
        try:
            _atomic_document(
                root / _INSTALL_SELECTED,
                _selection_payload(restore_sha256, restore_entry),
            )
            restored, restored_entry = _read_selection(root)
            _verify_installed_generation(
                root, restored, restored_entry,
                build_head_sha=build_head_sha, witness=witness,
            )
            if restored != restore_sha256:
                raise GuidePackagePublishBlocked("Installed rollback selection mismatch")
        except (GuidePackagePublishBlocked, OSError, ValueError) as exc:
            try:
                _atomic_document(root / _INSTALL_SELECTED, old_payload)
                current, current_entry = _read_selection(root)
                _verify_installed_generation(
                    root, current, current_entry,
                    build_head_sha=build_head_sha, witness=witness,
                )
                if current != selected:
                    raise GuidePackagePublishBlocked("Rollback recovery selection mismatch")
            except (GuidePackagePublishBlocked, OSError, ValueError) as recovery_exc:
                raise GuidePackagePublishBlocked(
                    "Rollback and recovery verification failed; manual review required"
                ) from recovery_exc
            raise GuidePackagePublishBlocked(
                "Rollback verification failed; previous selection restored"
            ) from exc
    return {
        "status": "INSTALLED_PACKAGE_ROLLED_BACK",
        "selected_sha256": restore_sha256,
        "previous_sha256": selected,
        "certified": False,
        "runtime_activation": False,
    }


__all__ = [
    "GuidePackagePublishBlocked",
    "install_attested_guide_package",
    "prepare_attested_guide_package",
    "rollback_installed_guide_package",
    "selected_installed_guide_package",
]
