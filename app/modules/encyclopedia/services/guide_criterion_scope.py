from __future__ import annotations

"""Canonical pure DOFUS criterion boolean parser for runtime and audit tools."""

import re
from dataclasses import dataclass
from typing import Sequence


ATOM_RE = re.compile(
    r"(?<![!\w])([A-Za-z]{1,5})\s*(=|!=|>=|<=|>|<)\s*(-?\d+|[A-Za-z_]+)",
    re.IGNORECASE,
)
@dataclass(frozen=True, slots=True)
class CriterionAtom:
    code: str
    op: str
    value: str

    @property
    def int_value(self) -> int | None:
        try:
            return int(self.value)
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class CriterionAlternative:
    atoms: tuple[CriterionAtom, ...]

    @property
    def finished_quest_ids(self) -> frozenset[int]:
        return frozenset(
            atom.int_value
            for atom in self.atoms
            if atom.code == "qf" and atom.op == "=" and atom.int_value is not None
        )


def _strip_outer_parentheses(expression: str) -> str:
    text = str(expression or "").strip()
    while len(text) >= 2 and text[0] == "(" and text[-1] == ")":
        depth = 0
        wraps_all = True
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(text) - 1:
                    wraps_all = False
                    break
        if wraps_all and depth == 0:
            text = text[1:-1].strip()
        else:
            break
    return text


def _split_top_level(expression: str, separator: str) -> list[str]:
    text = str(expression or "")
    depth = 0
    start = 0
    result: list[str] = []
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == separator and depth == 0:
            part = text[start:index].strip()
            if part:
                result.append(part)
            start = index + 1
    tail = text[start:].strip()
    if tail:
        result.append(tail)
    return result


def _combine_and(
    left: Sequence[CriterionAlternative],
    right: Sequence[CriterionAlternative],
) -> list[CriterionAlternative]:
    return [CriterionAlternative(lhs.atoms + rhs.atoms) for lhs in left for rhs in right]


def criterion_alternatives(expression: str) -> tuple[CriterionAlternative, ...]:
    """Small DNF parser for DOFUS criteria.

    It intentionally parses only atomic comparison codes, but it preserves
    parentheses + AND/OR structure. This is enough to avoid the old and very
    dangerous `Qf=A|Qf=B -> require A and B` bug.
    """

    text = str(expression or "").replace("&&", "&").replace("||", "|").strip()
    if not text:
        return (CriterionAlternative(()),)

    def walk(fragment: str) -> list[CriterionAlternative]:
        fragment = _strip_outer_parentheses(fragment)
        or_parts = _split_top_level(fragment, "|")
        if len(or_parts) > 1:
            merged: list[CriterionAlternative] = []
            for part in or_parts:
                merged.extend(walk(part))
            return merged

        and_parts = _split_top_level(fragment, "&")
        if len(and_parts) > 1:
            current: list[CriterionAlternative] = [CriterionAlternative(())]
            for part in and_parts:
                current = _combine_and(current, walk(part))
            return current

        atoms = tuple(
            CriterionAtom(
                code=match.group(1).casefold(),
                op=match.group(2),
                value=match.group(3),
            )
            for match in ATOM_RE.finditer(fragment)
        )
        return [CriterionAlternative(atoms)]

    raw = walk(text)
    seen: set[tuple[CriterionAtom, ...]] = set()
    result: list[CriterionAlternative] = []
    for alternative in raw:
        if alternative.atoms not in seen:
            seen.add(alternative.atoms)
            result.append(alternative)
    return tuple(result or [CriterionAlternative(())])


def qf_alternative_sets(expression: str) -> tuple[frozenset[int], ...]:
    """Return each legal Qf completion set from the boolean expression.

    Example:
      Qf=1&(Qf=2|Qf=3) -> ({1,2}, {1,3})
      Qf=1|PO=123        -> ({1}, {})
    """

    rows: list[frozenset[int]] = []
    seen: set[frozenset[int]] = set()
    for alt in criterion_alternatives(expression):
        value = alt.finished_quest_ids
        if value not in seen:
            seen.add(value)
            rows.append(value)
    return tuple(rows or [frozenset()])


def mandatory_qf_ids(expression: str) -> frozenset[int]:
    """Qf IDs required by *every* legal boolean branch."""

    alternatives = qf_alternative_sets(expression)
    common = set(alternatives[0]) if alternatives else set()
    for row in alternatives[1:]:
        common.intersection_update(row)
    return frozenset(common)


def residual_qf_alternatives(expression: str) -> tuple[frozenset[int], ...]:
    """Any-of Qf branch sets after removing mandatory Qf intersections.

    An empty branch means the criterion can be satisfied without another quest,
    so no additional Qf alternative is hard-required by the scope selector.
    """

    alternatives = qf_alternative_sets(expression)
    mandatory = set(mandatory_qf_ids(expression))
    residual: list[frozenset[int]] = []
    seen: set[frozenset[int]] = set()
    for row in alternatives:
        value = frozenset(set(row) - mandatory)
        if value not in seen:
            seen.add(value)
            residual.append(value)
    if any(not row for row in residual):
        return tuple()
    return tuple(residual) if len(residual) > 1 else tuple()


