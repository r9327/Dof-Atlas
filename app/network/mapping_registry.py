from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.network.mapping_manifest import (
    ProtocolMappingError,
    ProtocolMappingManifest,
    load_protocol_mapping,
)


@dataclass(frozen=True, slots=True)
class ProtocolMappingSelection:
    manifest: ProtocolMappingManifest | None
    matched_paths: tuple[Path, ...]
    invalid_paths: tuple[Path, ...]
    reason: str

    @property
    def usable(self) -> bool:
        return self.manifest is not None and self.reason == "exact_match"


class ProtocolMappingRegistry:
    """Find one unambiguous protocol mapping for an exact Unity build hash.

    Invalid files are reported but never partially accepted. Two manifests for
    the same build are treated as ambiguity rather than choosing one by filename
    or modification time.
    """

    def __init__(self, roots: Iterable[str | Path]) -> None:
        self.roots = tuple(Path(root) for root in roots)

    def select(self, build_sha256: str) -> ProtocolMappingSelection:
        fingerprint = str(build_sha256 or "").strip().casefold()
        if not _is_sha256(fingerprint):
            return ProtocolMappingSelection(None, (), (), "invalid_build_fingerprint")

        matched: list[tuple[Path, ProtocolMappingManifest]] = []
        invalid: list[Path] = []
        for path in self._candidate_paths():
            try:
                manifest = load_protocol_mapping(path)
            except ProtocolMappingError:
                invalid.append(path)
                continue
            if manifest.build_sha256 == fingerprint:
                matched.append((path, manifest))

        matched_paths = tuple(path for path, _ in matched)
        invalid_paths = tuple(invalid)
        if not matched:
            return ProtocolMappingSelection(None, (), invalid_paths, "no_exact_match")
        if len(matched) != 1:
            return ProtocolMappingSelection(None, matched_paths, invalid_paths, "ambiguous_exact_match")
        return ProtocolMappingSelection(
            matched[0][1],
            matched_paths,
            invalid_paths,
            "exact_match",
        )

    def _candidate_paths(self) -> tuple[Path, ...]:
        candidates: set[Path] = set()
        for root in self.roots:
            try:
                if root.is_file():
                    if root.suffix.casefold() == ".json":
                        candidates.add(root)
                    continue
                if not root.is_dir():
                    continue
                for path in root.glob("*.json"):
                    if path.is_file():
                        candidates.add(path)
            except OSError:
                continue
        return tuple(sorted(candidates, key=lambda path: str(path).casefold()))


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = ["ProtocolMappingRegistry", "ProtocolMappingSelection"]
