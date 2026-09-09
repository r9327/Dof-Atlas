from __future__ import annotations

"""Pure helpers for Guide Ultime V4 minimum-useful-scope selection.

This module deliberately has no Dofus Atlas imports so the hard selection policy
can be unit-tested without the game data bundle.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
import re

QF_POSITIVE_RE = re.compile(r"\bQf\s*=\s*(\d+)", re.IGNORECASE)
QA_POSITIVE_RE = re.compile(r"\bQa\s*=\s*(\d+)", re.IGNORECASE)
QQ_RE = re.compile(r"\bQQ\s*(>=|<=|=|>|<)\s*(\d+)", re.IGNORECASE)
SC_RE = re.compile(r"\bSc\s*=\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class ProfileKey:
    alignment: str
    order: str
    character_class: str

    @property
    def id(self) -> str:
        return f"{self.alignment}|{self.order}|{self.character_class}"


@dataclass
class ScopeResult:
    profile: ProfileKey
    selected_ids: set[int] = field(default_factory=set)
    seed_ids: set[int] = field(default_factory=set)
    prerequisite_ids: set[int] = field(default_factory=set)
    qq_filler_ids: set[int] = field(default_factory=set)
    choice_selections: dict[str, int] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    qq_required_count: int = 0
    count_before_qq_fill: int = 0
    count_after_qq_fill: int = 0


def positive_qf_ids(criterion: str) -> set[int]:
    """Only Qf=X is a hard completed-quest dependency.

    Qa=X means active, Qf!=X means forbidden/not done; neither may be converted
    into a completion prerequisite.
    """
    return {int(m.group(1)) for m in QF_POSITIVE_RE.finditer(str(criterion or ""))}


def active_qa_ids(criterion: str) -> set[int]:
    return {int(m.group(1)) for m in QA_POSITIVE_RE.finditer(str(criterion or ""))}


def qq_minimum_for_criterion(criterion: str) -> int | None:
    """Return minimum completed-quest count implied by one QQ comparison.

    Equality is treated as a target threshold for planning. Upper-bound-only
    predicates do not require adding quests and therefore return None.
    """
    values: list[int] = []
    for operator, raw in QQ_RE.findall(str(criterion or "")):
        n = int(raw)
        if operator == ">":
            values.append(n + 1)
        elif operator in {">=", "="}:
            values.append(n)
    return max(values) if values else None


def max_qq_requirement(criteria: Iterable[str]) -> int:
    return max((value for criterion in criteria if (value := qq_minimum_for_criterion(criterion)) is not None), default=0)


def meta_achievement_ids(criterion: str) -> set[int]:
    return {int(m.group(1)) for m in SC_RE.finditer(str(criterion or ""))}


def condition_matches_profile(condition: dict[str, Any], profile: ProfileKey) -> bool:
    side = str(condition.get("alignment") or "").casefold()
    if side and side != profile.alignment.casefold():
        return False
    order = str(condition.get("order") or "").casefold()
    if order and order != profile.order.casefold():
        return False
    klass = str(condition.get("class") or "").casefold()
    if klass and klass != profile.character_class.casefold():
        return False
    return True


def transitive_closure(
    seeds: Iterable[int],
    prerequisites: dict[int, set[int]],
    *,
    allowed: Callable[[int], bool],
    exists: Callable[[int], bool],
) -> tuple[set[int], set[int], list[dict[str, Any]]]:
    selected = {int(v) for v in seeds}
    added: set[int] = set()
    conflicts: list[dict[str, Any]] = []
    stack = list(selected)
    seen_edges: set[tuple[int, int]] = set()
    while stack:
        qid = stack.pop()
        for previous in prerequisites.get(qid, set()):
            previous = int(previous)
            edge = (qid, previous)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            if not exists(previous):
                conflicts.append({"type": "missing_prerequisite", "quest_id": qid, "prerequisite_id": previous})
                continue
            if not allowed(previous):
                conflicts.append({"type": "incompatible_prerequisite", "quest_id": qid, "prerequisite_id": previous})
                continue
            if previous not in selected:
                selected.add(previous)
                added.add(previous)
                stack.append(previous)
    return selected, added, conflicts


def choose_one_candidate(
    candidates: Iterable[int],
    *,
    selected: set[int],
    prerequisites: dict[int, set[int]],
    allowed: Callable[[int], bool],
    exists: Callable[[int], bool],
    rank_key: Callable[[int], tuple],
) -> tuple[int | None, set[int], list[dict[str, Any]]]:
    scored: list[tuple[tuple, int, set[int], list[dict[str, Any]]]] = []
    for candidate in sorted({int(v) for v in candidates}):
        if not exists(candidate) or not allowed(candidate):
            continue
        closure, added, conflicts = transitive_closure(
            selected | {candidate}, prerequisites, allowed=allowed, exists=exists
        )
        new_ids = closure - selected
        score = (bool(conflicts), len(new_ids), rank_key(candidate), candidate)
        scored.append((score, candidate, new_ids, conflicts))
    if not scored:
        return None, set(), [{"type": "no_compatible_choice", "candidate_ids": sorted({int(v) for v in candidates})}]
    scored.sort(key=lambda row: row[0])
    _score, candidate, new_ids, conflicts = scored[0]
    return candidate, new_ids, conflicts


def fill_to_qq_threshold(
    selected: set[int],
    target_count: int,
    candidates: Iterable[int],
    prerequisites: dict[int, set[int]],
    *,
    allowed: Callable[[int], bool],
    exists: Callable[[int], bool],
    rank_key: Callable[[int], tuple],
) -> tuple[set[int], set[int], list[dict[str, Any]]]:
    """Greedily add the lowest-cost neutral quests until QQ is satisfied.

    Candidate cost includes its still-missing transitive Qf closure, so a
    supposedly cheap filler cannot silently drag a large quest chain with it.
    """
    current = set(selected)
    fillers: set[int] = set()
    conflicts: list[dict[str, Any]] = []
    pool = {int(v) for v in candidates if int(v) not in current}
    while len(current) < int(target_count):
        options: list[tuple[tuple, int, set[int], list[dict[str, Any]]]] = []
        for candidate in pool:
            if not exists(candidate) or not allowed(candidate):
                continue
            closure, _added, local_conflicts = transitive_closure(
                current | {candidate}, prerequisites, allowed=allowed, exists=exists
            )
            new_ids = closure - current
            if not new_ids:
                continue
            score = (bool(local_conflicts), len(new_ids), rank_key(candidate), candidate)
            options.append((score, candidate, new_ids, local_conflicts))
        if not options:
            conflicts.append({
                "type": "qq_shortfall",
                "required": int(target_count),
                "current": len(current),
            })
            break
        options.sort(key=lambda row: row[0])
        _score, candidate, new_ids, local_conflicts = options[0]
        if local_conflicts:
            # Never use a conflicting filler merely to make the number look good.
            conflicts.extend(local_conflicts)
            conflicts.append({
                "type": "qq_no_conflict_free_candidate",
                "required": int(target_count),
                "current": len(current),
            })
            break
        current.update(new_ids)
        fillers.update(new_ids)
        pool.difference_update(new_ids)
        pool.discard(candidate)
    return current, fillers, conflicts
