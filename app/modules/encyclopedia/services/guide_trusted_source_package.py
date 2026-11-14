"""Fail-closed bridge from independently attested packaged routes to the shared Guide reader.

This module neither certifies a guide nor discovers/stages candidates. The caller
must supply a trusted package directory, an exact file digest and an independent
revocable witness; JSON from a guide never acts as its own authorization.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    _identifier as _canonical_source_identifier,
)

Witness = Callable[[str, str, str], bool]
_MAX_ROUTE_BYTES = 16 * 1024 * 1024


class GuidePackageBlocked(ValueError):
    """A source bundle is not safe or independently approved for runtime."""


def _json_bytes(route: dict[str, Any]) -> bytes:
    return json.dumps(
        route, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GuidePackageBlocked(f"Duplicate package JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise GuidePackageBlocked(f"Invalid JSON number: {value}")


def _redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


@dataclass(frozen=True, slots=True)
class GuidePackageEntry:
    """Trusted publisher metadata, supplied separately from the route file."""

    guide_id: str
    filename: str
    sha256: str
    certificate_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.guide_id, str) or not self.guide_id.startswith("source_guide:"):
            raise GuidePackageBlocked("Non-canonical source Guide identifier")
        try:
            _canonical_source_identifier(
                self.guide_id.removeprefix("source_guide:"), "source guide ID",
            )
        except ValueError as exc:
            raise GuidePackageBlocked("Unsafe source Guide identifier") from exc
        if not isinstance(self.filename, str) or not self.filename.endswith(".json"):
            raise GuidePackageBlocked("A packaged Guide needs a JSON filename")
        # Only single filenames, never relative paths / drive letters / traversal.
        stem = self.filename[:-5]
        try:
            _canonical_source_identifier(stem, "package filename")
        except ValueError as exc:
            raise GuidePackageBlocked("Unsafe packaged Guide filename") from exc
        if stem in {".", ".."} or "/" in self.filename or "\\" in self.filename:
            raise GuidePackageBlocked("Package path traversal is forbidden")
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.sha256)):
            raise GuidePackageBlocked("A lowercase pinned SHA-256 is required")
        if (not isinstance(self.certificate_ref, str)
                or not self.certificate_ref.strip()
                or len(self.certificate_ref) > 256):
            raise GuidePackageBlocked("Independent certificate reference required")


class GuideTrustedSourcePackage:
    """Explicit, lazy, one-file-per-guide loader with a revocable trust gate.

    No real guide is registered by default. The independent witness must bind
    certificate_ref and exact file SHA to the named Guide, including source
    permissions and manual/Windows evidence. Returning True in a unit test is
    only synthetic proof of this interface, never a certificate.
    """

    def __init__(
        self,
        root: Path,
        entries: Mapping[str, GuidePackageEntry],
        *,
        witness: Witness | None,
    ) -> None:
        if not callable(witness):
            raise GuidePackageBlocked("Independent trusted witness required")
        self.root = Path(root)
        for boundary in (self.root, *self.root.parents):
            if _redirected(boundary):
                raise GuidePackageBlocked("Redirected package directory")
        if not self.root.is_dir():
            raise GuidePackageBlocked("Trusted package directory missing")
        self._entries = dict(entries)
        for guide_id, entry in self._entries.items():
            if not isinstance(entry, GuidePackageEntry) or guide_id != entry.guide_id:
                raise GuidePackageBlocked("Entry key and source identity differ")
        if len({entry.filename for entry in self._entries.values()}) != len(self._entries):
            raise GuidePackageBlocked("One packaged file cannot own two Guide identities")
        self._witness = witness
        # Only tiny SHA strings are retained, never all projected guide routes.
        self._loaded: dict[str, tuple[str, str]] = {}

    def _attested(self, entry: GuidePackageEntry) -> bool:
        try:
            return self._witness(
                entry.guide_id, entry.sha256, entry.certificate_ref,
            ) is True
        except Exception:
            return False

    def load_route(self, guide_id: str) -> dict[str, Any]:
        """Read one exact installed route only when explicitly selected."""
        entry = self._entries.get(guide_id)
        if entry is None:
            raise GuidePackageBlocked("Unknown packaged Guide")
        file = self.root / entry.filename
        if _redirected(self.root) or _redirected(file) or not file.is_file():
            raise GuidePackageBlocked("Missing or redirected packaged Guide")
        try:
            with file.open("rb") as stream:
                raw = stream.read(_MAX_ROUTE_BYTES + 1)
            if not raw or len(raw) > _MAX_ROUTE_BYTES:
                raise GuidePackageBlocked("Packaged Guide exceeds the size limit")
            digest = hashlib.sha256(raw).hexdigest()
            if not hmac.compare_digest(digest, entry.sha256):
                raise GuidePackageBlocked("Packaged Guide SHA-256 mismatch")
            if not self._attested(entry):
                raise GuidePackageBlocked("Independent Guide certificate missing or revoked")
            route = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_no_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise GuidePackageBlocked("Unable to read strict packaged Guide JSON") from exc
        if (not isinstance(route, dict)
                or route.get("id") != entry.guide_id
                or route.get("source_compliance") != "NOT_CERTIFIED"
                or not isinstance(route.get("steps"), list)
                or not route["steps"]):
            raise GuidePackageBlocked("Invalid or mismatched projected Guide route")
        try:
            route_digest = hashlib.sha256(_json_bytes(route)).hexdigest()
        except (TypeError, ValueError) as exc:
            raise GuidePackageBlocked("Non-JSON-compatible projected route") from exc
        # A fresh load revokes the previous in-memory identity proof.
        self._loaded[guide_id] = (entry.sha256, route_digest)
        return route

    def authorize(self, guide_id: str, route: dict[str, Any]) -> bool:
        """Recheck exact in-memory snapshot and independent revocation on writes."""
        entry = self._entries.get(guide_id)
        receipt = self._loaded.get(guide_id)
        if entry is None or receipt is None or not isinstance(route, dict):
            return False
        if not hmac.compare_digest(receipt[0], entry.sha256):
            return False
        if route.get("id") != guide_id or route.get("source_compliance") != "NOT_CERTIFIED":
            return False
        try:
            current = hashlib.sha256(_json_bytes(route)).hexdigest()
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(receipt[1], current) and self._attested(entry)

    def factories(
        self, quest_progress: Any, achievement_progress: Any, guide_progress: Any,
    ) -> dict[str, Callable[[], Any]]:
        """Adapter for EncyclopediaPage(imported_source_factories=...).

        Factories capture the registry and progress services, not route bytes.
        No service, route JSON or Qt reader is initialized here.
        """
        def make(guide_id: str) -> Callable[[], Any]:
            def build() -> Any:
                from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
                    ImportedSourceManualRuntimeService,
                )
                return ImportedSourceManualRuntimeService(
                    quest_progress, achievement_progress, guide_progress,
                    route=self.load_route(guide_id),
                )
            return build
        return {guide_id: make(guide_id) for guide_id in self._entries}


__all__ = [
    "GuidePackageBlocked", "GuidePackageEntry", "GuideTrustedSourcePackage",
]
