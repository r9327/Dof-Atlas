"""Lossless, Qt-free adapter for the existing SharedGuideManualCard contract.

This is an additive source adapter, not another guide renderer or progress store.
The application must load one independently verified guide on selection; route
projection alone never marks a guide as source-verified or game-certified.
"""
from __future__ import annotations

import copy
import re
from typing import Any

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")
_TRAVEL_COORDINATE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
_SECTIONS = ("now", "opportunity", "keep", "boss", "before_leave")
_KINDS = frozenset({
    "travel", "talk", "item", "collect", "craft", "interact", "fight",
    "combat", "dungeon", "quest", "achievement", "choice", "warning",
    "prepare", "keep", "optional",
})
_SECTION_BY_KIND = {"warning": "before_leave", "keep": "keep", "prepare": "prepare"}
_UI_SECTIONS = frozenset((*_SECTIONS, "prepare"))
# These fields can carry actions that the shared card currently keeps only
# as opaque source metadata. Keeping bytes is not equivalent to displaying
# or making a user choice actionable. Block before a guide can be staged.
_UNRENDERED_ACTION_FIELDS = frozenset({
    "dialogue_options", "choices", "branches", "branching",
    "alternative_routes", "subactions", "substeps", "interactions",
    "achievement_ids", "success_ids", "images", "image", "media",
    "attachments", "links", "commands",
    "conditions", "validation", "validation_rule", "completion_rule",
    "required_level", "required_class", "required_alignment", "required_order",
    "prerequisites", "objectives", "dungeon_successes", "challenges",
})
_UNRENDERED_ENTRY_FIELDS = frozenset({
    "choices", "condition", "conditions", "location", "equip", "consume",
    "buy", "collect", "craft_recipe", "drop", "success_ids",
    "achievement_ids", "challenges", "media", "links", "actions",
})
_UNRENDERED_STEP_FIELDS = frozenset({
    "choices", "branches", "branching", "alternative_routes",
    "images", "image", "media", "attachments", "links",
})


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
        for field in sorted(_UNRENDERED_ENTRY_FIELDS & value.keys()):
            if value[field] not in (None, [], {}, ""):
                raise GuideRouteContractError(
                    f"{label}[{index}].{field}: unsupported authored UI content"
                )
        name = _text(value.get("name"), f"{label}[{index}].name")
        quantity = value.get("quantity")
        if type(quantity) is not int or quantity <= 0:
            raise GuideRouteContractError(f"{label}[{index}].quantity: positive integer required")
        if "item_id" in value and value["item_id"] is not None and (
            type(value["item_id"]) is not int or value["item_id"] <= 0
        ):
            raise GuideRouteContractError(
                f"{label}[{index}].item_id: positive integer required when present"
            )
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
        for field in sorted(_UNRENDERED_STEP_FIELDS & step.keys()):
            if step[field] not in (None, [], {}, ""):
                raise GuideRouteContractError(
                    f"{prefix}.{field}: unsupported authored UI content"
                )
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
            for field in sorted(_UNRENDERED_ACTION_FIELDS & action.keys()):
                if action[field] not in (None, [], {}, ""):
                    raise GuideRouteContractError(
                        f"{label}.{field}: unsupported authored UI content"
                    )
            text = _text(action.get("text"), f"{label}.text")
            position = _position(action.get("coordinates"), f"{label}.coordinates") or step_position
            names = _items(action.get("items"), f"{label}.items")
            if kind == "travel" and not position:
                raise GuideRouteContractError(f"{label}: travel requires verified coordinates")
            if kind == "travel":
                # The /travel shortcut must not contradict coordinates that
                # the authored instruction spells out. Never guess a target
                # from prose or silently substitute a step's source position.
                for x_text, y_text in _TRAVEL_COORDINATE.findall(text):
                    if (len(x_text) > 6 or len(y_text) > 6
                            or f"{int(x_text)},{int(y_text)}" != position):
                        raise GuideRouteContractError(
                            f"{label}.coordinates: conflicts with authored travel text"
                        )
            if kind in {"item", "collect", "craft", "keep", "prepare"} and not names:
                raise GuideRouteContractError(f"{label}: item action requires structured items")
            npc = action.get("npc")
            if npc is not None:
                _text(npc, f"{label}.npc")
            # Dialogue choices are shown in the shared source detail. An
            # invalid value would be silently dropped by the Qt renderer.
            if "dialogue_choice" in action:
                _text(action["dialogue_choice"], f"{label}.dialogue_choice")
            monsters = action.get("monsters")
            if monsters is not None:
                _items(monsters, f"{label}.monsters")
            if kind in {"fight", "combat"} and not monsters:
                raise GuideRouteContractError(f"{label}: combat requires structured monsters")
            section = action.get("section", _SECTION_BY_KIND.get(kind, "now"))
            if not isinstance(section, str) or section not in _UI_SECTIONS:
                raise GuideRouteContractError(f"{label}.section: unknown section {section!r}")
            # The shared viewer renders "prepare" only in its global
            # inventory panel. Do not hide a talk/travel/combat action there
            # or silently omit an authored preparation from that panel.
            if (section == "prepare") != (kind == "prepare"):
                raise GuideRouteContractError(
                    f"{label}.section: prepare action/section must match"
                )
            if section == "prepare":
                # Only the structured resource/quantity survives the global
                # preparation aggregation. Do not silently hide authored
                # NPCs, dialogue, combats or action-specific destinations.
                for field in ("npc", "dialogue_choice", "monsters", "coordinates"):
                    if action.get(field) not in (None, []):
                        raise GuideRouteContractError(
                            f"{label}.{field}: not renderable in preparation panel"
                        )
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
                # The shared renderer recognizes [x,y] for clickable
                # travel-copy links. Keep the raw source coordinates separately.
                "position": f"[{position}]" if position else "",
                "source_action_id": action_id,
                "source_action_kind": kind,
                "source_action": copy.deepcopy(action),
            }
            if section == "prepare":
                if not names:
                    raise GuideRouteContractError(
                        f"{label}: preparation needs explicit item names and quantities"
                    )
                for item in action["items"]:
                    preparation.append({
                        "name": item["name"],
                        "quantity": item["quantity"],
                        "item_id": item.get("item_id"),
                        "source_action_id": action_id,
                    })
                sections.setdefault("prepare", []).append(row)
            else:
                sections[section].append(row)
            for name in names:
                if name not in resource_names:
                    resource_names.append(name)
        for field in ("quest_ids", "quest_names", "prerequisites"):
            value = step.get(field, [])
            if not isinstance(value, list):
                raise GuideRouteContractError(f"{prefix}.{field}: list required")
        seen_quest_ids: set[int] = set()
        for quest_id in step.get("quest_ids", []):
            if type(quest_id) is not int or quest_id <= 0:
                raise GuideRouteContractError(f"{prefix}.quest_ids: positive integer IDs required")
            if quest_id in seen_quest_ids:
                raise GuideRouteContractError(f"{prefix}.quest_ids: duplicate quest ID {quest_id}")
            seen_quest_ids.add(quest_id)
        # A source action can own a precise Quest shortcut. It may only
        # reference IDs explicitly declared on its containing source step;
        # neither the reader nor an external catalog may invent that link.
        for action_index, action in enumerate(actions):
            if "quest_ids" not in action:
                continue
            linked = action["quest_ids"]
            label = f"{prefix}.actions[{action_index}].quest_ids"
            if not isinstance(linked, list):
                raise GuideRouteContractError(f"{label}: list required")
            if any(type(qid) is not int or qid <= 0 for qid in linked):
                raise GuideRouteContractError(f"{label}: positive integer IDs required")
            if len(linked) != len(set(linked)):
                raise GuideRouteContractError(f"{label}: duplicate quest ID")
            if any(qid not in seen_quest_ids for qid in linked):
                raise GuideRouteContractError(
                    f"{label}: quest ID must be declared in step.quest_ids"
                )
            if linked and action.get("kind") == "prepare":
                raise GuideRouteContractError(
                    f"{label}: preparation panel cannot render Quest shortcuts"
                )
        for name in step.get("quest_names", []):
            _text(name, f"{prefix}.quest_names")
        # Hard gates are structured, not rendered text. Retain every unknown
        # recognized field verbatim, but refuse missing/empty opaque entries.
        for gate in step.get("prerequisites", []):
            if not isinstance(gate, dict) or not gate:
                raise GuideRouteContractError(
                    f"{prefix}.prerequisites: nonempty structured gate objects required"
                )
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
        "source_guide_metadata": copy.deepcopy({
            key: value for key, value in guide.items() if key != "steps"
        }),
        "route_model": "authored_step_actions",
        "manual_manifest": False,
        "manual_preview": False,
        "manual_chapters": [guide_id],
        "steps": cards,
        "source_compliance": "NOT_CERTIFIED",
    }


__all__ = ["GuideRouteContractError", "project_authorized_guide"]
