"""Lossless, Qt-free adapter for the existing SharedGuideManualCard contract.

This is an additive source adapter, not another guide renderer or progress store.
The application must load one independently verified guide on selection; route
projection alone never marks a guide as source-verified or game-certified.
"""
from __future__ import annotations

import copy
import re
from typing import Any

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
_SECTIONS = ("now", "opportunity", "keep", "boss", "before_leave")
_KINDS = frozenset({
    "travel", "talk", "item", "collect", "craft", "interact", "fight",
    "combat", "dungeon", "quest", "achievement", "choice", "warning",
    "prepare", "keep", "optional",
})
_SECTION_BY_KIND = {"warning": "before_leave", "keep": "keep", "prepare": "prepare"}
_UI_SECTIONS = frozenset((*_SECTIONS, "prepare"))


class GuideRouteContractError(ValueError):
    """Reject invalid or lossy source data rather than inventing a route."""


def _identifier(raw: Any, label: str) -> str:
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise GuideRouteContractError(f"{label}: stable string/int ID required")
    value = str(raw)
    if not _ID.fullmatch(value) or value in {".", ".."}:
        raise GuideRouteContractError(f"{label}: unsafe or empty identifier")
    return value


def _text(raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise GuideRouteContractError(f"{label}: nonempty text required")
    return raw


def _position(raw: Any, label: str) -> str:
    if raw is None:
        return ""
    if (not isinstance(raw, (list, tuple)) or len(raw) != 2
            or any(type(v) is not int for v in raw)):
        raise GuideRouteContractError(f"{label}: [integer x, integer y] required")
    x, y = raw
    if abs(x) > 10000 or abs(y) > 10000:
        raise GuideRouteContractError(f"{label}: coordinates out of bounds")
    return f"{x},{y}"


def _items(raw: Any, label: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise GuideRouteContractError(f"{label}: items list required")
    names: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, dict):
            raise GuideRouteContractError(f"{label}[{index}]: item object required")
        name = _text(value.get("name"), f"{label}[{index}].name")
        quantity = value.get("quantity")
        if type(quantity) is not int or quantity <= 0:
            raise GuideRouteContractError(f"{label}[{index}].quantity: positive integer required")
        names.append(name)
    return tuple(names)


def project_authorized_guide(guide: dict[str, Any]) -> dict[str, Any]:
    """Project checked source actions to the shared UI card schema.

    No guessing, no reordered actions, no index-derived persistent stage keys,
    no Qt import and no save writes. Unknown semantic fields stay in source_actions.
    This does NOT check third-party rights, provenance or gameplay correctness.
    """
    if not isinstance(guide, dict):
        raise GuideRouteContractError("guide must be an object")
    guide_id = _identifier(guide.get("guide_id"), "guide_id")
    title = _text(guide.get("title"), "title")
    steps = guide.get("steps")
    if not isinstance(steps, list) or not steps:
        raise GuideRouteContractError("steps: nonempty ordered list required")
    cards: list[dict[str, Any]] = []
    seen_steps: set[str] = set()
    for step_index, step in enumerate(steps):
        prefix = f"steps[{step_index}]"
        if not isinstance(step, dict):
            raise GuideRouteContractError(f"{prefix}: object required")
        source_id = _identifier(step.get("source_step_id"), f"{prefix}.source_step_id")
        if source_id in seen_steps:
            raise GuideRouteContractError(f"{prefix}: duplicate source_step_id {source_id}")
        seen_steps.add(source_id)
        step_title = _text(step.get("title"), f"{prefix}.title")
        step_position = _position(step.get("coordinates"), f"{prefix}.coordinates")
        actions = step.get("actions")
        if not isinstance(actions, list) or not actions:
            raise GuideRouteContractError(f"{prefix}.actions: nonempty list required")
        sections: dict[str, list[dict[str, Any]]] = {name: [] for name in _SECTIONS}
        preparation: list[dict[str, Any]] = []
        resource_names: list[str] = []
        seen_actions: set[str] = set()
        last_rank = -1
        for action_index, action in enumerate(actions):
            label = f"{prefix}.actions[{action_index}]"
            if not isinstance(action, dict):
                raise GuideRouteContractError(f"{label}: object required")
            action_id = _identifier(action.get("action_id"), f"{label}.action_id")
            if action_id in seen_actions:
                raise GuideRouteContractError(f"{label}: duplicate action_id {action_id}")
            seen_actions.add(action_id)
            kind = _text(action.get("kind"), f"{label}.kind")
            if kind not in _KINDS:
                raise GuideRouteContractError(f"{label}: unsupported action kind {kind!r}")
            text = _text(action.get("text"), f"{label}.text")
            position = _position(action.get("coordinates"), f"{label}.coordinates") or step_position
            names = _items(action.get("items"), f"{label}.items")
            npc = action.get("npc")
            if npc is not None:
                _text(npc, f"{label}.npc")
            monsters = action.get("monsters")
            if monsters is not None:
                _items(monsters, f"{label}.monsters")
            section = action.get("section", _SECTION_BY_KIND.get(kind, "now"))
            if not isinstance(section, str) or section not in _UI_SECTIONS:
                raise GuideRouteContractError(f"{label}.section: unknown section {section!r}")
            if section == "prepare" and last_rank >= 0:
                raise GuideRouteContractError(
                    f"{label}: preparation would reorder source actions"
                )
            # Existing SharedGuideManualCard renders sections in a fixed order.
            # Reject source order incompatible with that UI instead of silently
            # rearranging an action. Preparation is a separate shared panel.
            if section != "prepare":
                rank = _SECTIONS.index(section)
                if rank < last_rank:
                    raise GuideRouteContractError(f"{label}: section would reorder source actions")
                last_rank = rank
            row = {
                "kind": "combat" if kind in {"fight", "combat"} else
                        "warning" if kind == "warning" else "action",
                "text": text,
                "position": position,
                "source_action_id": action_id,
                "source_action_kind": kind,
                "source_action": copy.deepcopy(action),
            }
            if section == "prepare":
                preparation.append(row)
            else:
                sections[section].append(row)
            for name in names:
                if name not in resource_names:
                    resource_names.append(name)
        for field in ("quest_ids", "quest_names", "prerequisites"):
            value = step.get(field, [])
            if not isinstance(value, list):
                raise GuideRouteContractError(f"{prefix}.{field}: list required")
        card = {
            "index": step_index + 1,
            "manual_source": True,
            "manual_chapter_id": guide_id,
            "manual_chapter_label": title,
            "manual_stage_id": f"source:{guide_id}:{source_id}",
            "source_step_id": source_id,
            "manual_title": step_title,
            "manual_route_position": step_position,
            "manual_sections": sections,
            "manual_lines": [row for name in _SECTIONS for row in sections[name]],
            "manual_resource_names": resource_names,
            "manual_quest_ids": copy.deepcopy(step.get("quest_ids", [])),
            "manual_quest_names": copy.deepcopy(step.get("quest_names", [])),
            "a_preparer": preparation,
            "hard_runtime_gates": copy.deepcopy(step.get("prerequisites", [])),
            "manual_runtime_metadata": {
                "source_guide_id": guide_id,
                "source_step_id": source_id,
                "source_step": copy.deepcopy(step),
            },
        }
        cards.append(card)
    return {
        "schema_version": 5,
        "id": f"source_guide:{guide_id}",
        "source": "authorized_import",
        "route_model": "authored_step_actions",
        "manual_manifest": False,
        "manual_preview": False,
        "manual_chapters": [guide_id],
        "steps": cards,
        "source_compliance": "NOT_CERTIFIED",
    }


__all__ = ["GuideRouteContractError", "project_authorized_guide"]
