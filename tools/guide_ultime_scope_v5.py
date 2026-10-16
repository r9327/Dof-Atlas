from __future__ import annotations

"""Pure helpers for Guide Ultime V5 UNIVERSAL scope selection.

V5 has one master guide. Class and Order are conditional branches inside that
single guide; they are never generator parameters and never create profiles.

AUDIT HOTFIX 1:
- parse Qf boolean branches structurally instead of flattening OR branches;
- support any-of prerequisite groups during closure/filler selection;
- allow universal conditional branches (class/order) to satisfy a future
  prerequisite without injecting every branch into the common route.
"""

from typing import Any, Callable, Iterable
import re

from app.modules.encyclopedia.services.guide_criterion_scope import (
    ATOM_RE,
    CriterionAlternative,
    CriterionAtom,
    _combine_and,
    _split_top_level,
    _strip_outer_parentheses,
    criterion_alternatives,
    mandatory_qf_ids,
    qf_alternative_sets,
    residual_qf_alternatives,
)

QF_POSITIVE_RE = re.compile(r"\bQf\s*=\s*(\d+)", re.IGNORECASE)
QA_POSITIVE_RE = re.compile(r"\bQa\s*=\s*(\d+)", re.IGNORECASE)
QQ_RE = re.compile(r"\bQQ\s*(>=|<=|=|>|<)\s*(\d+)", re.IGNORECASE)
SC_RE = re.compile(r"\bSc\s*=\s*(\d+)", re.IGNORECASE)


def positive_qf_ids(criterion: str) -> set[int]:
    # Compatibility API: this is the union, useful for display/discovery only.
    return {int(m.group(1)) for m in QF_POSITIVE_RE.finditer(str(criterion or ""))}


def active_qa_ids(criterion: str) -> set[int]:
    return {int(m.group(1)) for m in QA_POSITIVE_RE.finditer(str(criterion or ""))}


def qq_minimum_for_criterion(criterion: str) -> int | None:
    values: list[int] = []
    for operator, raw in QQ_RE.findall(str(criterion or "")):
        n = int(raw)
        if operator == ">":
            values.append(n + 1)
        elif operator in {">=", "="}:
            values.append(n)
    return max(values) if values else None


def max_qq_requirement(criteria: Iterable[str]) -> int:
    return max((v for c in criteria if (v := qq_minimum_for_criterion(c)) is not None), default=0)


def meta_achievement_ids(criterion: str) -> set[int]:
    return {int(m.group(1)) for m in SC_RE.finditer(str(criterion or ""))}


def _dedupe_conflicts(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    import json
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def transitive_closure(
    seeds: Iterable[int],
    prerequisites: dict[int, set[int]],
    *,
    allowed: Callable[[int], bool],
    exists: Callable[[int], bool],
    alternatives: dict[int, tuple[frozenset[int], ...]] | None = None,
    defer_allowed: Callable[[int], bool] | None = None,
    preselected: Iterable[int] = (),
) -> tuple[set[int], set[int], list[dict[str, Any]]]:
    seed_set = {int(v) for v in seeds}
    selected = {int(v) for v in preselected} | seed_set
    added: set[int] = set()
    conflicts: list[dict[str, Any]] = []
    # Only expand the new seeds. Preselected IDs were already validated by the
    # caller and must not re-emit the same conflict for every class/order branch.
    stack = list(seed_set)
    seen_edges: set[tuple[int, int]] = set()
    seen_any: set[int] = set()
    alternatives = alternatives or {}

    while stack:
        qid = int(stack.pop())
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

        # One residual Qf alternative set must be satisfied. A conditional
        # class/order alternative may be deferred to the corresponding inline
        # branch of the universal guide instead of polluting the common route.
        if qid in seen_any:
            continue
        seen_any.add(qid)
        groups = tuple(alternatives.get(qid, ()) or ())
        if not groups:
            continue
        if any(set(group).issubset(selected) for group in groups):
            continue

        viable: list[tuple[tuple[int, tuple[int, ...]], frozenset[int]]] = []
        deferred = False
        missing_rows: list[int] = []
        for group in groups:
            ids = {int(v) for v in group}
            missing = [v for v in ids if not exists(v)]
            if missing:
                missing_rows.extend(missing)
                continue
            disallowed = [v for v in ids if not allowed(v)]
            if disallowed:
                if defer_allowed is not None and disallowed and all(defer_allowed(v) for v in disallowed):
                    deferred = True
                continue
            new_ids = ids - selected
            viable.append(((len(new_ids), tuple(sorted(ids))), frozenset(ids)))

        if viable:
            viable.sort(key=lambda row: row[0])
            chosen = set(viable[0][1])
            for previous in sorted(chosen):
                if previous not in selected:
                    selected.add(previous)
                    added.add(previous)
                    stack.append(previous)
            continue
        if deferred:
            continue
        conflicts.append({
            "type": "no_compatible_prerequisite_alternative",
            "quest_id": qid,
            "alternative_quest_id_sets": [sorted(map(int, group)) for group in groups],
            **({"missing_prerequisite_ids": sorted(set(missing_rows))} if missing_rows else {}),
        })

    return selected, added, _dedupe_conflicts(conflicts)


def choose_one_candidate(
    candidates: Iterable[int],
    *,
    selected: set[int],
    prerequisites: dict[int, set[int]],
    allowed: Callable[[int], bool],
    exists: Callable[[int], bool],
    rank_key: Callable[[int], tuple],
    alternatives: dict[int, tuple[frozenset[int], ...]] | None = None,
    defer_allowed: Callable[[int], bool] | None = None,
) -> tuple[int | None, set[int], list[dict[str, Any]]]:
    scored: list[tuple[tuple, int, set[int], list[dict[str, Any]]]] = []
    for candidate in sorted({int(v) for v in candidates}):
        if not exists(candidate) or not allowed(candidate):
            continue
        closure, _added, conflicts = transitive_closure(
            {candidate},
            prerequisites,
            allowed=allowed,
            exists=exists,
            alternatives=alternatives,
            defer_allowed=defer_allowed,
            preselected=selected,
        )
        new_ids = closure - selected
        scored.append(((bool(conflicts), len(new_ids), rank_key(candidate), candidate), candidate, new_ids, conflicts))
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
    alternatives: dict[int, tuple[frozenset[int], ...]] | None = None,
    defer_allowed: Callable[[int], bool] | None = None,
) -> tuple[set[int], set[int], list[dict[str, Any]]]:
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
                {candidate},
                prerequisites,
                allowed=allowed,
                exists=exists,
                alternatives=alternatives,
                defer_allowed=defer_allowed,
                preselected=current,
            )
            new_ids = closure - current
            if new_ids:
                options.append(((bool(local_conflicts), len(new_ids), rank_key(candidate), candidate), candidate, new_ids, local_conflicts))
        if not options:
            conflicts.append({"type": "qq_shortfall", "required": int(target_count), "current": len(current)})
            break
        options.sort(key=lambda row: row[0])
        _score, candidate, new_ids, local_conflicts = options[0]
        if local_conflicts:
            # Keep the audit precise: do not dump hundreds of repeated branch
            # conflicts just because the QQ loop retried them.
            conflicts.extend(local_conflicts)
            conflicts.append({"type": "qq_no_conflict_free_candidate", "required": int(target_count), "current": len(current)})
            break
        current.update(new_ids)
        fillers.update(new_ids)
        pool.difference_update(new_ids)
        pool.discard(candidate)
    return current, fillers, _dedupe_conflicts(conflicts)


def branch_combination_counts(
    common_ids: set[int],
    class_deltas: dict[str, set[int]],
    order_deltas: dict[str, set[int]],
) -> list[int]:
    """Execution counts for validation only; never creates runtime profiles."""
    return [
        len(common_ids | class_ids | order_ids)
        for class_ids in class_deltas.values()
        for order_ids in order_deltas.values()
    ]
