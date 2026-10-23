from __future__ import annotations

"""Deterministic titles for generated Guide route sheets.

The naming layer only composes names already carried by structured route
actions.  It never truncates an official name or derives game facts from free
text.  Titles outside the readability contract remain visible and are reported
for review instead of being silently shortened.
"""

from dataclasses import dataclass
from typing import Iterable

from app.modules.encyclopedia.services.adventure_route_engine import RouteStep


CHAPTER_TITLE_LIMIT = 40
SHEET_TITLE_LIMIT = 48
_VAGUE_TITLES = {
    "actions",
    "etape",
    "etape suivante",
    "faire des choses",
    "suite",
}


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip(" -—")


def _unique(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for raw in values if (value := _clean(raw))))


@dataclass(frozen=True, slots=True)
class GuideTitleDecision:
    text: str
    source: str
    limit: int = SHEET_TITLE_LIMIT

    @property
    def review_required(self) -> bool:
        return len(self.text) > self.limit or self.text.casefold() in _VAGUE_TITLES

    def to_payload(self) -> dict[str, object]:
        return {
            "text": self.text,
            "source": self.source,
            "limit": self.limit,
            "length": len(self.text),
            "review_required": self.review_required,
        }


@dataclass(frozen=True, slots=True)
class GuideTitleViolation:
    code: str
    index: int
    title: str
    detail: str


def title_for_route_step(step: RouteStep) -> GuideTitleDecision:
    """Build one concise title from exact structured names on the step."""

    dungeon_names = _unique(action.dungeon_name for action in step.actions)
    if len(dungeon_names) == 1:
        return GuideTitleDecision(f"Donjon — {dungeon_names[0]}", "dungeon_name")
    if len(dungeon_names) > 1:
        place = _clean(step.location.subzone or step.location.zone)
        return GuideTitleDecision(
            f"Donjons — {place}" if place else "Donjons groupés",
            "dungeon_group",
        )

    monster_names = _unique(
        name
        for action in step.actions
        for name in action.monster_names
    )
    if len(monster_names) == 1:
        return GuideTitleDecision(f"Combat — {monster_names[0]}", "monster_name")
    if len(monster_names) > 1:
        place = _clean(step.location.subzone or step.location.zone)
        return GuideTitleDecision(
            f"Combats — {place}" if place else "Combats groupés",
            "monster_group",
        )

    starts = _unique(
        action.title.removeprefix("Prendre — ")
        for action in step.actions
        if action.is_start
    )
    if len(starts) == 1:
        return GuideTitleDecision(f"Départ — {starts[0]}", "quest_start")

    exact_titles = _unique(action.title for action in step.actions)
    if len(exact_titles) == 1:
        return GuideTitleDecision(exact_titles[0], "action_title")

    place = _clean(step.location.subzone or step.location.zone)
    if place:
        return GuideTitleDecision(f"Actions — {place}", "location")
    return GuideTitleDecision("Actions coordonnées", "structured_fallback")


def title_for_ganymede_step(title: str, number: int) -> GuideTitleDecision:
    """Remove only the redundant numbered wrapper of a signed source title.

    Preserve its exact subject and punctuation; flag long/vague titles rather
    than truncating an NPC, monster, dungeon or quest name.
    """
    if type(number) is not int or number < 1 or not isinstance(title, str):
        raise ValueError("A source stage needs a numbered text title")
    name = " ".join(title.split())
    prefixes = (f"Étape {number} —", f"Etape {number} —")
    for prefix in prefixes:
        if name == prefix or name.startswith(prefix + " "):
            name = name[len(prefix):]
            break
    name = _clean(name)
    if not name:
        raise ValueError("Empty signed source stage title")
    return GuideTitleDecision(name, "ganymede_signed_source")


def audit_title_decisions(
    decisions: Iterable[GuideTitleDecision],
) -> tuple[GuideTitleViolation, ...]:
    rows = tuple(decisions)
    violations: list[GuideTitleViolation] = []
    positions: dict[str, list[int]] = {}
    for index, decision in enumerate(rows):
        positions.setdefault(decision.text.casefold(), []).append(index)
        if len(decision.text) > decision.limit:
            violations.append(
                GuideTitleViolation(
                    "title_too_long",
                    index,
                    decision.text,
                    f"{len(decision.text)}>{decision.limit}; conserver le nom exact et revoir manuellement",
                )
            )
        if decision.text.casefold() in _VAGUE_TITLES:
            violations.append(
                GuideTitleViolation("title_vague", index, decision.text, decision.source)
            )
    for title, indexes in positions.items():
        if len(indexes) <= 1:
            continue
        for index in indexes:
            violations.append(
                GuideTitleViolation(
                    "title_ambiguous_duplicate",
                    index,
                    rows[index].text,
                    f"indexes={','.join(map(str, indexes))}",
                )
            )
    return tuple(violations)


__all__ = [
    "CHAPTER_TITLE_LIMIT",
    "SHEET_TITLE_LIMIT",
    "GuideTitleDecision",
    "GuideTitleViolation",
    "audit_title_decisions",
    "title_for_route_step",
    "title_for_ganymede_step",
]
