"""Versioned Atlas data-pack update planner (no filesystem or network writes).

Data packs are independent from the Windows EXE; validating signed manifests,
downloading, atomic staging and rollback remain duties of the existing updater.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

_KINDS = frozenset({"quests", "successes", "guides", "items", "equipment"})
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PATH = re.compile(r"data/[a-z0-9_./-]{1,180}\Z", re.ASCII)


class InvalidDataPack(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DataPack:
    kind: str
    revision: int
    schema_version: int
    sha256: str
    artifact_path: str


@dataclass(frozen=True, slots=True)
class InstalledPack:
    revision: int
    schema_version: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PackAction:
    kind: str
    action: str  # download / keep
    expected_sha256: str
    artifact_path: str | None


def _check_pack(pack: DataPack) -> None:
    if not isinstance(pack, DataPack) or pack.kind not in _KINDS:
        raise InvalidDataPack("unknown pack kind")
    if (type(pack.revision) is not int or not 1 <= pack.revision <= 2**31 or
        type(pack.schema_version) is not int or not 1 <= pack.schema_version <= 65535):
        raise InvalidDataPack("invalid revision or schema")
    if not isinstance(pack.sha256, str) or not _SHA.fullmatch(pack.sha256):
        raise InvalidDataPack("invalid SHA-256")
    if (not isinstance(pack.artifact_path, str) or
        not _PATH.fullmatch(pack.artifact_path) or
        any(part in ("", ".", "..") for part in pack.artifact_path.split("/"))):
        raise InvalidDataPack("unsafe artifact path")


def _check_state(state: InstalledPack) -> None:
    if (not isinstance(state, InstalledPack) or
        type(state.revision) is not int or state.revision < 1 or
        type(state.schema_version) is not int or state.schema_version < 1 or
        not isinstance(state.sha256, str) or not _SHA.fullmatch(state.sha256)):
        raise InvalidDataPack("invalid installed state")


def plan_pack_updates(installed: Mapping[str, InstalledPack],
                      offered: Iterable[DataPack]) -> tuple[PackAction, ...]:
    """Reject downgrade, schema mismatch and conflicting same-version releases.

    Planning does not authorize installation; artifact hashes and manifest
    authenticity must still be checked by the privileged installer.
    """
    if not isinstance(installed, Mapping):
        raise InvalidDataPack("invalid installed inventory")
    for kind, state in installed.items():
        if kind not in _KINDS:
            raise InvalidDataPack("unrecognized installed pack")
        _check_state(state)
    actions = []
    seen = set()
    for pack in offered:
        _check_pack(pack)
        if pack.kind in seen:
            raise InvalidDataPack("duplicate pack")
        seen.add(pack.kind)
        current = installed.get(pack.kind)
        if current is not None:
            if pack.revision < current.revision:
                raise InvalidDataPack("data pack downgrade refused")
            if pack.revision == current.revision:
                if pack.sha256 != current.sha256 or pack.schema_version != current.schema_version:
                    raise InvalidDataPack("same-version data mismatch")
                actions.append(PackAction(pack.kind, "keep", pack.sha256, None))
                continue
            if pack.schema_version < current.schema_version:
                raise InvalidDataPack("schema downgrade refused")
        actions.append(PackAction(pack.kind, "download", pack.sha256, pack.artifact_path))
    return tuple(sorted(actions, key=lambda a: a.kind))
