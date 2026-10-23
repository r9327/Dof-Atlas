"""Non-destructive Atlas data-change plan for Quests, Successes and Guides.

Standalone validation layer: does not open or change Atlas databases, progress
files or active guide routes. The authoritative schema/migrations stay in Atlas.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

_KINDS = frozenset({"quest", "success", "guide", "item"})
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class AtlasDataPlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DataRecord:
    kind: str
    identifier: str
    content_sha256: str
    references: tuple[tuple[str, str], ...] = ()

    def key(self) -> tuple[str, str]:
        return self.kind, self.identifier


@dataclass(frozen=True, slots=True)
class PlannedChange:
    kind: str
    identifier: str
    action: str  # add / update / keep / absent_in_batch
    old_sha256: str | None
    new_sha256: str | None


def _checked_records(records: Iterable[DataRecord], *, max_records: int = 50_000
                     ) -> dict[tuple[str, str], DataRecord]:
    result: dict[tuple[str, str], DataRecord] = {}
    for row in records:
        if len(result) >= max_records:
            raise AtlasDataPlanError("too many records")
        if not isinstance(row, DataRecord):
            raise AtlasDataPlanError("expected DataRecord")
        if row.kind not in _KINDS or not _ID.fullmatch(row.identifier):
            raise AtlasDataPlanError("invalid kind or ID")
        if not _SHA.fullmatch(row.content_sha256):
            raise AtlasDataPlanError("invalid source hash")
        if len(row.references) > 500:
            raise AtlasDataPlanError("too many references")
        for ref in row.references:
            if (not isinstance(ref, tuple) or len(ref) != 2 or
                ref[0] not in _KINDS or not isinstance(ref[1], str) or
                not _ID.fullmatch(ref[1])):
                raise AtlasDataPlanError("invalid reference")
        key = row.key()
        if key in result:
            raise AtlasDataPlanError("duplicate record key")
        result[key] = row
    return result


def plan_data_changes(current: Iterable[DataRecord], incoming: Iterable[DataRecord],
                      *, known_references: Iterable[tuple[str, str]] = ()
                      ) -> tuple[PlannedChange, ...]:
    """Treat absent records as an observation, never as authorization to delete.

    Cross-links can target the existing dataset, the new batch or explicit
    known_references. Caller verifies the latter against the canonical store.
    """
    old = _checked_records(current)
    new = _checked_records(incoming)
    known = set(known_references)
    for ref in known:
        if (not isinstance(ref, tuple) or len(ref) != 2 or ref[0] not in _KINDS or
            not isinstance(ref[1], str) or not _ID.fullmatch(ref[1])):
            raise AtlasDataPlanError("invalid trusted reference")
    available = old.keys() | new.keys() | known
    for row in new.values():
        for ref in row.references:
            if ref not in available:
                raise AtlasDataPlanError(f"unresolved reference {ref[0]}:{ref[1]}")
    plan = []
    for key in sorted(old.keys() | new.keys()):
        previous = old.get(key)
        following = new.get(key)
        action = ("add" if previous is None else
                  "absent_in_batch" if following is None else
                  "keep" if previous.content_sha256 == following.content_sha256 else "update")
        plan.append(PlannedChange(
            key[0], key[1], action,
            previous.content_sha256 if previous else None,
            following.content_sha256 if following else None,
        ))
    return tuple(plan)
