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
    GuideRouteContractError,
    _identifier as _canonical_source_identifier,
    project_authorized_guide,
)

# guide ID, projected file SHA, authorized source SHA, exact app HEAD, receipt ID
Witness = Callable[[str, str, str, str, str], bool]
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
    source_sha256: str
    head_sha: str
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
        if (not isinstance(self.source_sha256, str) or len(self.source_sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.source_sha256)
                or self.source_sha256 == "0" * 64):
            raise GuidePackageBlocked("A pinned authorized source SHA-256 is required")
        if (not isinstance(self.head_sha, str) or len(self.head_sha) != 40
                or any(char not in "0123456789abcdef" for char in self.head_sha)
                or self.head_sha == "0" * 40):
            raise GuidePackageBlocked("A pinned exact app Git HEAD is required")
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
        build_head_sha: str,
        witness: Witness | None,
    ) -> None:
        if (not isinstance(build_head_sha, str) or len(build_head_sha) != 40
                or any(c not in "0123456789abcdef" for c in build_head_sha)
                or build_head_sha == "0" * 40):
            raise GuidePackageBlocked("Trusted build HEAD must be an exact Git SHA")
        if not callable(witness):
            raise GuidePackageBlocked("Independent trusted witness required")
        self.root = Path(root)
        for boundary in (self.root, *self.root.parents):
            if _redirected(boundary):
                raise GuidePackageBlocked("Redirected package directory")
        if not self.root.is_dir():
            raise GuidePackageBlocked("Trusted package directory missing")
        self._entries = dict(entries)
        self._build_head_sha = build_head_sha
        for guide_id, entry in self._entries.items():
            if not isinstance(entry, GuidePackageEntry) or guide_id != entry.guide_id:
                raise GuidePackageBlocked("Entry key and source identity differ")
            if not hmac.compare_digest(entry.head_sha, build_head_sha):
                raise GuidePackageBlocked("Certificate belongs to a different app HEAD")
        if len({entry.filename for entry in self._entries.values()}) != len(self._entries):
            raise GuidePackageBlocked("One packaged file cannot own two Guide identities")
        self._witness = witness
        # Only tiny SHA strings are retained, never all projected guide routes.
        self._loaded: dict[str, tuple[str, str]] = {}

    def _attested(self, entry: GuidePackageEntry) -> bool:
        try:
            return self._witness(
                entry.guide_id, entry.sha256, entry.source_sha256,
                self._build_head_sha, entry.certificate_ref,
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
        except GuidePackageBlocked:
            # Preserve explicit duplicate-key and strict-number rejection details.
            raise
        except (OSError, ValueError, OverflowError, RecursionError) as exc:
            # The JSON decoder can also raise for excessive nesting or integer
            # digit limits. Malformed files must fail as controlled package blocks.
            raise GuidePackageBlocked("Unable to read strict packaged Guide JSON") from exc
        if (not isinstance(route, dict)
                or route.get("id") != entry.guide_id
                or route.get("source_compliance") != "NOT_CERTIFIED"
                or not isinstance(route.get("steps"), list)
                or not route["steps"]):
            raise GuidePackageBlocked("Invalid or mismatched projected Guide route")
        # Rebuild the canonical reader representation from the exact authored
        # steps embedded in this projected route. A matching file SHA alone
        # cannot prove that the renderer faithfully exposes the source actions:
        # reject changed UI sections, hidden steps, injected text and rerouting.
        try:
            metadata = route.get("source_guide_metadata")
            if not isinstance(metadata, dict):
                raise GuidePackageBlocked("Missing canonical source Guide metadata")
            source_steps = []
            for card in route["steps"]:
                if not isinstance(card, dict):
                    raise GuidePackageBlocked("Malformed projected Guide step")
                runtime = card.get("manual_runtime_metadata")
                source_step = (
                    runtime.get("source_step")
                    if isinstance(runtime, dict) else None
                )
                if not isinstance(source_step, dict):
                    raise GuidePackageBlocked("Missing original authored source step")
                source_steps.append(source_step)
            reconstructed = project_authorized_guide({
                **metadata, "steps": source_steps,
            })
            route_bytes = _json_bytes(route)
            if _json_bytes(reconstructed) != route_bytes:
                raise GuidePackageBlocked("Projected Guide differs from authored source")
            route_digest = hashlib.sha256(route_bytes).hexdigest()
        except (GuideRouteContractError, TypeError, ValueError) as exc:
            if isinstance(exc, GuidePackageBlocked):
                raise
            raise GuidePackageBlocked("Invalid canonical source projection") from exc
        # A fresh load revokes the previous in-memory identity proof.
        self._loaded[guide_id] = (entry.sha256, route_digest)
        return route

    def _installed_bytes_match(self, entry: GuidePackageEntry) -> bool:
        """Fail closed if a packaged route was modified or replaced after opening."""
        try:
            path = self.root / entry.filename
            if any(_redirected(boundary) for boundary in
                   (self.root, *self.root.parents, path)):
                return False
            with path.open("rb") as stream:
                payload = stream.read(_MAX_ROUTE_BYTES + 1)
            return (
                0 < len(payload) <= _MAX_ROUTE_BYTES
                and hmac.compare_digest(hashlib.sha256(payload).hexdigest(), entry.sha256)
            )
        except OSError:
            return False

    def authorize(self, guide_id: str, route: dict[str, Any]) -> bool:
        """Recheck installed bytes, exact in-memory snapshot and revocable witness."""
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
        return (
            hmac.compare_digest(receipt[1], current)
            and self._installed_bytes_match(entry)
            and self._attested(entry)
        )

    def catalog_guides(self, summaries: Mapping[str, Mapping[str, Any]]) -> tuple[Any, ...]:
        """Publish only trusted, revocable Home metadata without loading routes.

        The independent application publisher supplies titles and category
        labels separately from authored JSON. A witnessed package identity is
        mandatory for every visible card; the route bytes are never read here.
        """
        if not isinstance(summaries, Mapping):
            raise GuidePackageBlocked("Trusted Guide catalogue must be a mapping")
        categories = {
            "dofus": "Dofus", "alignements": "Alignements",
            "iles": "Îles", "dimensions": "Dimensions",
            "evenements": "Événements",
        }
        from app.modules.encyclopedia.models.guide import Guide
        from app.core.text import normalize_key
        guides = []
        for guide_id, summary in summaries.items():
            entry = self._entries.get(guide_id)
            if entry is None or not isinstance(summary, Mapping):
                raise GuidePackageBlocked("Unregistered or invalid trusted Guide summary")
            title = summary.get("title")
            category = summary.get("category")
            total = summary.get("total_steps")
            description = summary.get("description", "")
            if (not isinstance(title, str) or not title.strip()
                    or len(title) > 180 or not isinstance(category, str)
                    or category not in categories
                    or type(total) is not int or not 0 < total <= 10000
                    or not isinstance(description, str) or len(description) > 600):
                raise GuidePackageBlocked("Invalid trusted Guide catalogue fields")
            if not self._attested(entry):
                continue
            guides.append(Guide(
                id=guide_id, title=title.strip(), category=category,
                category_label=categories[category],
                description=description,
                total_steps=total,
                search_text=normalize_key(f"{title} {category} {description}"),
            ))
        return tuple(sorted(
            guides,
            key=lambda g: (list(categories).index(g.category), g.title.casefold(), g.id),
        ))

    def factories(
        self, quest_progress: Any, achievement_progress: Any, guide_progress: Any,
        *,
        gate_evaluators: Mapping[str, Callable[[str, dict[str, Any]], bool]] | None = None,
        zaap_planners: Mapping[str, Callable[[tuple[int, int], tuple[str, ...]], Any]] | None = None,
    ) -> dict[str, Callable[[], Any]]:
        """Adapter for EncyclopediaPage(imported_source_factories=...).

        Only the trusted composition owner may register qualified per-guide
        prerequisite evaluators. No evaluator is ever inferred from source JSON,
        and a missing evaluator keeps hard gates blocked rather than bypassed.
        Factories retain tiny registry references, not all route bytes.
        """
        if gate_evaluators is not None and not isinstance(gate_evaluators, Mapping):
            raise GuidePackageBlocked("Trusted per-guide gate registry must be a mapping")
        evaluators = dict(gate_evaluators or {})
        for guide_id, evaluator in evaluators.items():
            if guide_id not in self._entries or not callable(evaluator):
                raise GuidePackageBlocked("Unregistered or invalid source Guide gate evaluator")
        if zaap_planners is not None and not isinstance(zaap_planners, Mapping):
            raise GuidePackageBlocked("Trusted Zaap planner registry must be a mapping")
        planners = dict(zaap_planners or {})
        for guide_id, planner in planners.items():
            if guide_id not in self._entries or not callable(planner):
                raise GuidePackageBlocked("Unregistered or invalid verified Zaap planner")

        def make(
            guide_id: str,
            evaluator: Callable[[str, dict[str, Any]], bool] | None,
            planner: Callable[[tuple[int, int], tuple[str, ...]], Any] | None,
        ) -> Callable[[], Any]:
            def build() -> Any:
                from app.modules.encyclopedia.services.guide_imported_manual_runtime_service import (
                    ImportedSourceManualRuntimeService,
                )
                return ImportedSourceManualRuntimeService(
                    quest_progress, achievement_progress, guide_progress,
                    route=self.load_route(guide_id),
                    gate_evaluator=evaluator,
                    verified_zaap_planner=planner,
                )
            return build
        return {
            guide_id: make(guide_id, evaluators.get(guide_id), planners.get(guide_id))
            for guide_id in self._entries
        }


__all__ = [
    "GuidePackageBlocked", "GuidePackageEntry", "GuideTrustedSourcePackage",
]
