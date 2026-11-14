"""Fail-closed, one-guide packaging of an already staged Guide candidate.

This is a delivery *preparer*, NOT a certification authority or live installer.
The trusted host must supply and continuously maintain an independent final
certificate witness. A generated JSON file and its hash cannot authorize itself.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.services.guide_trusted_source_package import (
    GuidePackageBlocked,
    GuidePackageEntry,
    GuideTrustedSourcePackage,
    Witness,
    _MAX_ROUTE_BYTES,
    _json_bytes,
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


__all__ = ["GuidePackagePublishBlocked", "prepare_attested_guide_package"]
