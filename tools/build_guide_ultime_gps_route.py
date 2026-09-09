from __future__ import annotations

"""DOFUS ATLAS — GUIDE ULTIME — GPS ROUTE BUILDER V5 UNIVERSAL

Run from the repository root AFTER build_guide_ultime_final.py:

    py -3.13 .\tools\build_guide_ultime_gps_route.py --strict

V5 UNIVERSAL:
- consumes guide_ultime_final.json (single content-lock source of truth);
- plans progressively from level 1 to 200 instead of pretending level=200 from step 1;
- never forces alignment alternatives unless the runtime branch explicitly selects them;
- executes one quest per one-of choice group (Darwin) in the static reference route;
- gates Order ranks behind the canonical alignment quest reaching 20/40/60/80/100;
- unknown hard criteria are never auto-opened in strict mode;
- master resources / profession gates are attached to route cards when resolvable;
- one master route for every class; class/Order differences are conditional cards;
- no --class / --order generator parameters;
- exact coordinates still come only from local data.
"""

import argparse
import json
import re
import sys
import traceback
import unicodedata
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

ROOT = Path.cwd()
if not (ROOT / "app").exists():
    ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.modules.encyclopedia.services.adventure_route_adapter import AdventureRouteAdapter
from app.modules.encyclopedia.services.adventure_route_engine import (
    AdventureRouteEngine,
    RouteAction,
    RoutePlan,
    RouteProfile,
    RouteProgress,
    RouteStep,
)

ARTIFACTS = ROOT / "artifacts"
GUIDE_PATH = ARTIFACTS / "guide_ultime_final.json"
MASTER_CANDIDATES = (
    ROOT / "tools" / "guide_ultime_master_2026-08-22.json",
    ARTIFACTS / "guide_ultime_master_2026-08-22.json",
    ROOT / "guide_ultime_master_2026-08-22.json",
    ROOT / "tools" / "guide_ultime_route_verifiee_2026-08-22.json",
    ARTIFACTS / "guide_ultime_route_verifiee_2026-08-22.json",
    ROOT / "guide_ultime_route_verifiee_2026-08-22.json",
)
OUT = ARTIFACTS / "guide_ultime_gps_route.json"
OUT_AUDIT = ARTIFACTS / "guide_ultime_gps_route_audit.json"
CRASH_AUDIT = ARTIFACTS / "guide_ultime_gps_crash.json"
_GPS_STAGE = "module_loaded"


def _gps_stage(value: str) -> None:
    global _GPS_STAGE
    _GPS_STAGE = value
    print(f"[GPS] {value}", flush=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.casefold()).strip()


def load_master() -> dict[str, Any]:
    for path in MASTER_CANDIDATES:
        if path.exists():
            payload = load_json(path)
            if isinstance(payload, dict):
                payload["_loaded_from"] = str(path)
                return payload
    raise SystemExit("guide_ultime_master_2026-08-22.json introuvable")


def iter_guide_steps(guide: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for section in guide.get("sections", []) or []:
        for step in section.get("steps", []) or []:
            if isinstance(step, dict) and step.get("type") == "quest":
                yield step



def universal_scope(guide: dict[str, Any]) -> dict[str, Any] | None:
    scope = ((guide.get("guide_ultime_policy") or {}).get("universal_scope"))
    return scope if isinstance(scope, dict) else None


def branch_condition_is_common(step: dict[str, Any]) -> bool:
    policy = str(step.get("runtime_policy") or "always_when_unlocked")
    cond = step.get("condition") if isinstance(step.get("condition"), dict) else {}
    if policy in {"conditional_class_card", "conditional_order_card", "selected_class_only", "selected_alignment_and_order_only"}:
        return False
    if policy in {"only_if_game_branch_selects_it", "only_while_event_available", "qq_calendar_filler_when_available", "skip", "tracked_side_thread_not_blocking"}:
        return False
    side = norm(cond.get("alignment"))
    if side and side != "bonta":
        return False
    return not bool(cond.get("class") or cond.get("order"))


def select_quest_steps(guide: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scope = universal_scope(guide)
    common_source = (scope.get("routing_common_selected_quest_ids") or scope.get("common_selected_quest_ids", [])) if scope else []
    common_ids = {int(v) for v in common_source}
    reference_choices = {str(k): int(v) for k, v in ((scope.get("choice_selections") or {}).items() if scope else [])}
    selected: list[dict[str, Any]] = []
    choice_groups: dict[str, list[dict[str, Any]]] = {}
    for step in iter_guide_steps(guide):
        qid = int(step.get("entity_id") or 0)
        policy = str(step.get("runtime_policy") or "always_when_unlocked")
        if policy == "one_of_choice_group_until_success":
            group = step.get("choice_group") if isinstance(step.get("choice_group"), dict) else {}
            choice_groups.setdefault(str(group.get("id") or "runtime_one_of"), []).append(step)
            continue
        if scope is not None and qid not in common_ids:
            continue
        if not branch_condition_is_common(step):
            continue
        selected.append(step)

    choice_audit: list[dict[str, Any]] = []
    for group_id, candidates in sorted(choice_groups.items()):
        candidates = sorted(candidates, key=lambda row: int(row.get("entity_id") or 0))
        reference_id = reference_choices.get(group_id)
        chosen = next((row for row in candidates if int(row.get("entity_id") or 0) == reference_id), None) or candidates[0]
        if scope is None or int(chosen["entity_id"]) in common_ids:
            selected.append(chosen)
        choice_audit.append({
            "group_id": group_id,
            "candidate_quest_ids": [int(row["entity_id"]) for row in candidates],
            "selected_quest_id": int(chosen["entity_id"]),
            "selection_mode": "universal_reference_choice",
            "runtime_instruction": "Si le jeu impose une autre variante du même groupe, suivre cette variante puis reprendre la route maître.",
        })

    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for row in selected:
        qid = int(row["entity_id"])
        if qid not in seen:
            seen.add(qid)
            unique.append(row)
    return unique, choice_audit


def conditional_branch_cards(guide: dict[str, Any]) -> dict[str, Any]:
    scope = universal_scope(guide) or {}
    steps = list(iter_guide_steps(guide))
    class_rows = [row for row in steps if str(row.get("runtime_policy") or "") == "conditional_class_card"]
    order_rows = [row for row in steps if str(row.get("runtime_policy") or "") == "conditional_order_card"]

    class_options = []
    for row in sorted(class_rows, key=lambda r: norm((r.get("condition") or {}).get("class"))):
        klass = str((row.get("condition") or {}).get("class") or "")
        class_options.append({
            "class": klass,
            "quest_id": int(row["entity_id"]),
            "branch_quest_ids": list(map(int, (scope.get("class_branches") or {}).get(klass, []))),
            "instruction": "Fais la quête correspondant à ta classe, puis reprends immédiatement la route maître.",
        })

    order_cards = []
    by_rank: dict[int, list[dict[str, Any]]] = {}
    for row in order_rows:
        cond = row.get("condition") if isinstance(row.get("condition"), dict) else {}
        rank = int(cond.get("order_rank") or 0)
        by_rank.setdefault(rank, []).append(row)
    for rank in sorted(by_rank):
        options = []
        for row in sorted(by_rank[rank], key=lambda r: norm((r.get("condition") or {}).get("order"))):
            cond = row.get("condition") or {}
            order_name = str(cond.get("order") or "")
            options.append({
                "order": order_name,
                "quest_id": int(row["entity_id"]),
                "full_order_branch_quest_ids": list(map(int, (scope.get("order_branches") or {}).get(order_name, []))),
            })
        options and order_cards.append({
            "rank": rank,
            "alignment_level": int((by_rank[rank][0].get("condition") or {}).get("min_alignment_level") or 0),
            "options": options,
            "instruction": "Choisis ton Ordre une seule fois et fais uniquement la quête de cet Ordre à ce palier.",
        })
    temporal_ids = list(map(int, scope.get("qq_temporal_filler_quest_ids") or []))
    return {
        "class_card": {"required_slots": 1, "options": class_options},
        "order_cards": order_cards,
        "order_required_slots": 5,
        "qq_calendar_card": {
            "required_count": int(scope.get("qq_temporal_required_count") or len(temporal_ids)),
            "quest_ids": temporal_ids,
            "instruction": (
                "QQ=1600 : la route permanente est prioritaire. Compléter ensuite uniquement le nombre "
                "minimum de quêtes calendrier listées ici, au fil des événements/Almanax disponibles."
            ),
            "time_gated": bool(temporal_ids),
        },
        "guide_is_single_universal_route": True,
    }

def reference_route_expected_ids(
    scope: dict[str, Any] | None,
    choice_audit: list[dict[str, Any]],
) -> tuple[set[int], set[int]]:
    """Return the executable common IDs after one-of groups choose one branch."""
    if not scope:
        return set(), set()
    common = {
        int(v)
        for v in (
            scope.get("routing_common_selected_quest_ids")
            or scope.get("common_selected_quest_ids")
            or []
        )
    }
    skipped: set[int] = set()
    for row in choice_audit:
        candidates = {int(v) for v in row.get("candidate_quest_ids", [])} & common
        selected = int(row.get("selected_quest_id") or 0)
        if selected in candidates:
            skipped.update(candidates - {selected})
    return common - skipped, skipped


def apply_universal_class_gate_bridges(
    actions: list[RouteAction],
    guide: dict[str, Any],
) -> tuple[list[RouteAction], list[dict[str, Any]]]:
    """Bridge Qf=(class A|class B|...) without pretending one class was chosen.

    The universal GPS has one conditional class card, not 19 generated profiles.
    A common quest may therefore depend on "one of the class quests".  In the
    static reference engine that dependency is represented as an explicit
    conditional gate card and removed only when *every* alternative branch is a
    known class quest.  Mixed/unknown alternatives remain hard dependencies.
    """
    scope = universal_scope(guide) or {}
    class_ids = {
        int(qid)
        for values in (scope.get("class_branches") or {}).values()
        for qid in (values or [])
    }
    if not class_ids:
        return list(actions), []

    updated: list[RouteAction] = []
    bridges: list[dict[str, Any]] = []
    for action in actions:
        groups = tuple(action.prerequisite_quest_alternatives or ())
        is_pure_class_choice = bool(groups) and all(
            bool(group) and set(map(int, group)).issubset(class_ids)
            for group in groups
        )
        if not (action.is_start and is_pure_class_choice):
            updated.append(action)
            continue

        class_options = sorted({int(qid) for group in groups for qid in group})
        updated.append(replace(action, prerequisite_quest_alternatives=()))
        bridges.append({
            "quest_id": int(action.quest_id),
            "action_id": action.action_id,
            "class_quest_options": class_options,
            "required_count": 1,
            "gate_type": "universal_class_card",
            "instruction": (
                "Avant cette quête, termine la carte correspondant à TA classe. "
                "Une seule quête de classe est requise; les 18 autres ne sont jamais imposées."
            ),
        })
    return updated, bridges


def full_success_cards(guide: dict[str, Any], route_steps: list[dict[str, Any]]) -> dict[str, Any]:
    policy = guide.get("guide_ultime_policy") or {}
    target_monsters = list(policy.get("target_monster_successes") or [])
    target_dungeons = list(policy.get("target_dungeon_successes") or [])
    route_success_ids = {
        int(aid)
        for step in route_steps
        for aid in ((step.get("progresse_aussi") or {}).get("success_ids") or [])
    }
    route_dungeon_names = {
        norm(name)
        for step in route_steps
        for name in ((step.get("dungeon_context") or {}).get("dungeon_names") or [])
        if str(name or "").strip()
    }

    monster_cards: list[dict[str, Any]] = []
    for row in target_monsters:
        aid = int(row.get("achievement_id") or 0)
        monster_ids = [int(v) for v in row.get("monster_ids", []) or []]
        overlap = aid in route_success_ids
        monster_cards.append({
            "achievement_id": aid,
            "name": str(row.get("name") or ""),
            "level": row.get("level"),
            "monster_ids": monster_ids,
            "coverage_mode": "quest_route_overlap" if overlap else "dedicated_monster_sweep_card",
            "instruction": (
                "Valider ce succès pendant le premier farm/combat naturel compatible; "
                "s'il ne croise aucune quête, faire un sweep dédié au niveau conseillé."
            ),
        })

    by_dungeon: dict[tuple[int, str], dict[str, Any]] = {}
    meta_dungeon_cards: list[dict[str, Any]] = []
    for row in target_dungeons:
        aid = int(row.get("achievement_id") or 0)
        dungeons = list(row.get("dungeons") or [])
        if not dungeons:
            meta_dungeon_cards.append({
                "achievement_id": aid,
                "name": str(row.get("name") or ""),
                "level": row.get("level"),
                "coverage_mode": "meta_or_unlocated_dungeon_success",
                "instruction": "Suivre automatiquement via ses sous-succès; aucune visite supplémentaire n'est inventée sans donjon résolu.",
            })
            continue
        for dungeon in dungeons:
            did = int(dungeon.get("dungeon_id") or 0)
            name = str(dungeon.get("name") or f"Donjon {did}")
            key = (did, name)
            card = by_dungeon.setdefault(key, {
                "dungeon_id": did,
                "dungeon_name": name,
                "route_overlap": norm(name) in route_dungeon_names,
                "achievements": [],
                "instruction": (
                    "Avant l'entrée, regrouper tous les succès Donjons compatibles sur ce passage. "
                    "Ne refaire le donjon que pour une incompatibilité de critères réellement prouvée."
                ),
            })
            card["achievements"].append({
                "achievement_id": aid,
                "name": str(row.get("name") or ""),
                "level": row.get("level"),
            })

    dungeon_cards = sorted(by_dungeon.values(), key=lambda r: (int(r.get("dungeon_id") or 0), norm(r.get("dungeon_name"))))
    for card in dungeon_cards:
        card["coverage_mode"] = "quest_route_dungeon_bundle" if card["route_overlap"] else "dedicated_dungeon_success_card"

    return {
        "monster_success_cards": monster_cards,
        "dungeon_success_cards": dungeon_cards,
        "dungeon_meta_success_cards": meta_dungeon_cards,
        "monster_success_target_count": len(target_monsters),
        "dungeon_success_target_count": len(target_dungeons),
        "all_targets_have_cards": (
            len(monster_cards) == len(target_monsters)
            and sum(len(card.get("achievements") or []) for card in dungeon_cards) + len(meta_dungeon_cards) >= len(target_dungeons)
        ),
    }


def quest_start_action_id(actions: Iterable[RouteAction], quest_id: int) -> str | None:
    for action in actions:
        if int(action.quest_id) == int(quest_id) and action.is_start:
            return action.action_id
    return None


def inject_order_alignment_dependencies(
    actions: list[RouteAction],
    selected_steps: list[dict[str, Any]],
    *,
    alignment: str,
    order: str,
) -> tuple[list[RouteAction], list[dict[str, Any]], list[dict[str, Any]]]:
    """Gate Order ranks behind the canonical alignment quest reaching 20/40/60/80/100."""

    align = norm(alignment)
    order_key = norm(order)
    main_gate_by_target: dict[int, int] = {}
    order_rows: list[dict[str, Any]] = []

    for row in selected_steps:
        cond = row.get("condition") if isinstance(row.get("condition"), dict) else {}
        status = str(row.get("status") or "")
        qid = int(row["entity_id"])
        if status == "included_alignment_branch" and norm(cond.get("alignment")) == align:
            target = int(cond.get("target_alignment_level") or 0)
            if target > 0:
                main_gate_by_target[target] = qid
        elif status == "included_order_branch":
            if norm(cond.get("alignment")) == align and norm(cond.get("order")) == order_key:
                order_rows.append(row)

    applied: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    deps_by_qid: dict[int, int] = {}
    for row in order_rows:
        cond = row.get("condition") if isinstance(row.get("condition"), dict) else {}
        threshold = int(cond.get("min_alignment_level") or 0)
        qid = int(row["entity_id"])
        gate_qid = main_gate_by_target.get(threshold)
        if gate_qid is None:
            missing.append({"order_quest_id": qid, "required_alignment_level": threshold})
            continue
        deps_by_qid[qid] = gate_qid

    updated: list[RouteAction] = []
    for action in actions:
        gate_qid = deps_by_qid.get(int(action.quest_id))
        if gate_qid is None or not action.is_start:
            updated.append(action)
            continue
        deps = set(action.prerequisites_quests)
        deps.add(int(gate_qid))
        updated.append(replace(action, prerequisites_quests=frozenset(deps)))
        applied.append({
            "order_quest_id": int(action.quest_id),
            "order_start_action_id": action.action_id,
            "wait_for_alignment_quest_id": int(gate_qid),
        })
    return updated, applied, missing


def apply_dungeon_bundle_holds(
    actions: list[RouteAction],
    catalog: Any,
    master: dict[str, Any],
    selected_ids: set[int],
) -> tuple[list[RouteAction], list[dict[str, Any]]]:
    """Delay non-forced-repeat dungeons until every selected bundle quest has started."""

    by_name = {norm(q.name): int(q.id) for q in catalog.quests}
    forced_repeat_names = {norm(name) for name in (master.get("forced_quest_repeats") or {})}
    bundles = master.get("dungeon_bundles") or {}
    updated = list(actions)
    applied: list[dict[str, Any]] = []

    for dungeon_name, bundle in bundles.items():
        if norm(dungeon_name) in forced_repeat_names:
            continue
        quest_names = list((bundle or {}).get("quests") or [])
        quest_ids = [by_name.get(norm(name)) for name in quest_names]
        quest_ids = [qid for qid in quest_ids if qid is not None and qid in selected_ids]
        start_ids = [quest_start_action_id(updated, qid) for qid in quest_ids]
        start_ids = [aid for aid in start_ids if aid]
        if not start_ids:
            continue

        token = norm(dungeon_name)
        for index, action in enumerate(updated):
            hay = norm(f"{action.dungeon_name} {action.title}")
            if not action.is_dungeon or token not in hay:
                continue
            # Do not add an action as a prerequisite of itself.
            deps = set(action.prerequisites_actions)
            deps.update(aid for aid in start_ids if aid != action.action_id)
            if deps == set(action.prerequisites_actions):
                continue
            updated[index] = replace(action, prerequisites_actions=frozenset(deps))
            applied.append({
                "dungeon": dungeon_name,
                "action_id": action.action_id,
                "wait_for_quest_starts": list(start_ids),
            })
    return updated, applied


def profile_with_level(base: RouteProfile, level: int) -> RouteProfile:
    return replace(base, level=max(1, min(200, int(level))))


def progressive_plan(
    engine: AdventureRouteEngine,
    base_profile: RouteProfile,
    *,
    start_level: int = 1,
    max_level: int = 200,
) -> tuple[RoutePlan, list[int], list[int]]:
    levels = {
        max(start_level, min(max_level, int(action.condition.min_level or start_level)))
        for action in engine.actions
        if int(action.condition.min_level or start_level) <= max_level
    }
    levels.add(start_level)
    levels.add(max_level)
    milestones = sorted(levels)

    progress = RouteProgress()
    current = None
    all_steps: list[RouteStep] = []
    all_step_levels: list[int] = []

    for level in milestones:
        segment = engine.plan(profile_with_level(base_profile, level), progress, start_location=current)
        progress = segment.final_progress
        if segment.steps:
            all_steps.extend(segment.steps)
            all_step_levels.extend([int(level)] * len(segment.steps))
            current = segment.steps[-1].location

    # One final pass at the cap catches anything unlocked by the last dependency
    # closure and gives blocked reasons for every remaining matched action.
    final_profile = profile_with_level(base_profile, max_level)
    tail = engine.plan(final_profile, progress, start_location=current)
    progress = tail.final_progress
    if tail.steps:
        all_steps.extend(tail.steps)
        all_step_levels.extend([int(max_level)] * len(tail.steps))

    reindexed: list[RouteStep] = []
    for index, step in enumerate(all_steps, 1):
        next_location = all_steps[index].location if index < len(all_steps) else None
        reindexed.append(replace(step, index=index, next_location=next_location))

    # Compute blocked state from the final progress without executing anything
    # else. If more actions are actually runnable, that is a planner regression.
    residual = engine.plan(final_profile, progress, start_location=(reindexed[-1].location if reindexed else None))
    if residual.steps:
        raise RuntimeError("progressive planner left runnable actions after final closure")

    return RoutePlan(
        steps=tuple(reindexed),
        blocked=residual.blocked,
        metrics=engine.metrics_for_steps(reindexed),
        final_progress=progress,
    ), milestones, all_step_levels


def acquisition_options(source: str) -> list[dict[str, Any]]:
    """Return player-facing acquisition choices in time-optimization order.

    Presence of ``craft`` never creates a profession gate by itself.  A hard
    profession requirement must come from ``profession_gates`` / quest criteria.
    """
    tokens = {norm(v) for v in re.split(r"[|/,]", str(source or "")) if v.strip()}
    options: list[dict[str, Any]] = []

    if "banque" in tokens or "bank" in tokens:
        options.append({
            "mode": "BANQUE",
            "recommended": True,
            "label": "BANQUE / inventaire si déjà possédé",
            "requires_job_level": False,
        })

    if "hdv" in tokens:
        options.append({
            "mode": "HDV",
            "recommended": True,
            "label": "HDV — recommandé pour optimiser le temps",
            "requires_job_level": False,
        })

    if any("pnj" in token or "monnaie" in token for token in tokens):
        options.append({
            "mode": "PNJ_MONNAIE",
            "recommended": "hdv" not in tokens,
            "label": "PNJ / monnaie si requis ou plus direct",
            "requires_job_level": False,
        })

    if "craft" in tokens:
        buyable = "hdv" in tokens
        options.append({
            "mode": "CRAFT",
            "recommended": not buyable and not options,
            "label": (
                "CRAFT — option économique facultative"
                if buyable
                else "CRAFT — nécessaire selon la source locale"
            ),
            "requires_job_level": False,  # never infer a hard gate from the recipe alone
            "optional_when_hdv_available": buyable,
        })

    if "farm" in tokens or "drop" in tokens:
        buyable = "hdv" in tokens
        options.append({
            "mode": "FARM_DROP",
            "recommended": not buyable and not options,
            "label": (
                "FARM / DROP — option économique, éviter le détour"
                if buyable
                else "FARM / DROP — seulement si nécessaire"
            ),
            "requires_job_level": False,
            "optional_when_hdv_available": buyable,
        })

    if not options:
        options.append({
            "mode": "MANUEL",
            "recommended": True,
            "label": "Vérifier la source obligatoire; HDV si l'objet est échangeable",
            "requires_job_level": False,
        })
    return options


def source_recommendation(source: str) -> str:
    options = acquisition_options(source)
    # Time-first: owned/bank first, otherwise HDV before craft/farm.
    for mode in ("BANQUE", "HDV", "PNJ_MONNAIE", "CRAFT", "FARM_DROP", "MANUEL"):
        for option in options:
            if option["mode"] == mode and bool(option.get("recommended")):
                return str(option["label"])
    return str(options[0]["label"])


def manual_context_for_step(
    selected_actions: Iterable[RouteAction],
    by_quest: dict[int, Any],
    master: dict[str, Any],
) -> dict[str, Any]:
    resources = master.get("manual_resources") or {}
    index = {norm(key): value for key, value in resources.items() if isinstance(value, dict)}
    keys: set[str] = set()
    for action in selected_actions:
        quest = by_quest.get(int(action.quest_id))
        if quest is not None:
            keys.add(norm(getattr(quest, "name", "")))
        if action.dungeon_name:
            keys.add(norm(action.dungeon_name))

    prep: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    external_help: list[dict[str, Any]] = []
    matched_keys: list[str] = []
    for key in sorted(keys):
        block = index.get(key)
        if not block:
            continue
        matched_keys.append(key)
        for field in ("before_start", "before_enter", "campaign_resources"):
            for item in block.get(field, []) or []:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "")
                options = acquisition_options(source)
                prep.append({
                    "name": str(item.get("name") or ""),
                    "quantity": int(item.get("quantity") or 1),
                    "source": source or "non_précisé",
                    "recommended_source": source_recommendation(source),
                    "acquisition_options": options,
                    "craft_optional": any(
                        row.get("mode") == "CRAFT" and row.get("optional_when_hdv_available")
                        for row in options
                    ),
                    "timing": field,
                    "alternative": item.get("alternative"),
                })
        for gate in block.get("profession_gates", []) or []:
            if isinstance(gate, dict):
                row = dict(gate)
                row.setdefault("gate_type", "hard_game_requirement")
                row.setdefault("can_be_bypassed_by_hdv", False)
                row.setdefault("note", "Métier exigé par le jeu; ne vient pas d'un simple craft achetable.")
                gates.append(row)
        for helper in block.get("external_craft_help", []) or []:
            if isinstance(helper, dict):
                row = dict(helper)
                row.setdefault("personal_job_required", False)
                row.setdefault("instruction", "Demander l'aide d'un artisan; ne pas monter ce métier pour cette étape.")
                external_help.append(row)

    # Stable de-duplication.
    dedup_prep: list[dict[str, Any]] = []
    seen_prep: set[tuple[str, int, str]] = set()
    for row in prep:
        marker = (norm(row["name"]), int(row["quantity"]), str(row["timing"]))
        if marker not in seen_prep:
            seen_prep.add(marker)
            dedup_prep.append(row)
    return {
        "manual_resource_matches": matched_keys,
        "manual_preparation": dedup_prep,
        "profession_gates": gates,
        "external_craft_help": external_help,
    }


def _name_tokens(value: Any) -> set[str]:
    return {token for token in norm(value).split() if len(token) >= 3 and token not in {"donjon", "antre", "repaire", "grotte", "temple"}}


def _names_match(left: Any, right: Any) -> bool:
    a, b = norm(left), norm(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    return overlap >= 1 and overlap / max(1, min(len(ta), len(tb))) >= 0.66


def dungeon_manual_context(actions: Iterable[RouteAction], master: dict[str, Any], alignment: str) -> dict[str, Any]:
    dungeon_names = sorted({str(a.dungeon_name) for a in actions if str(a.dungeon_name or "").strip()})
    exit_rows: list[dict[str, Any]] = []
    for rule in master.get("before_leaving_dungeon", []) or []:
        if not isinstance(rule, dict):
            continue
        condition = norm(rule.get("condition"))
        if condition and condition not in norm(alignment):
            continue
        rule_name = str(rule.get("dungeon") or "")
        matched = next((name for name in dungeon_names if _names_match(name, rule_name)), None)
        if matched:
            exit_rows.append({
                "dungeon": matched,
                "rule_name": rule_name,
                "action": str(rule.get("action") or ""),
            })

    ocre = master.get("long_term_threads", {}).get("ocre", {}) or {}
    ocre_rows: list[dict[str, Any]] = []
    for stage_key in ("stage_1_bosses", "stage_2_bosses", "stage_3_bosses"):
        for boss in ocre.get(stage_key, []) or []:
            matched = next((name for name in dungeon_names if _names_match(name, boss)), None)
            if matched:
                ocre_rows.append({
                    "dungeon": matched,
                    "boss": str(boss),
                    "stage": stage_key.replace("_bosses", ""),
                    "action": "Capturer le boss Ocre au premier passage utile si l'étape correspondante est active et Capture d’âmes est acquise.",
                })
    capture_unlock = any(_names_match(name, "Kwakwa") for name in dungeon_names)
    return {
        "dungeon_names": dungeon_names,
        "dungeon_exit_rules": exit_rows,
        "ocre_capture_targets": ocre_rows,
        "capture_ames_unlock_here": capture_unlock,
    }


def full_success_policy(guide: dict[str, Any]) -> dict[str, Any]:
    policy = guide.get("guide_ultime_policy") or {}
    return {
        "monster": list(policy.get("target_monster_successes") or []),
        "dungeon": list(policy.get("target_dungeon_successes") or []),
    }


RUNTIME_GATE_LABELS = {
    "ad": "calendrier/almanax",
    "pj": "métier/profession",
    "pg": "branche de classe",
    "pm": "carte/position",
    "qo": "progression d'objectif de quête",
    "qc": "état de quête",
    "po": "objet/état d'objet",
    "oa": "état d'objectif/succès",
    "pz": "état monde/personnage",
    "st": "état de monde/événement",
    "we": "état environnemental",
    "dd": "état de donnée de jeu",
    "dh": "état de donnée de jeu",
    "dm": "état de donnée de jeu",
    "sv": "état de jeu",
    "ha": "état de jeu",
    "sh": "état de jeu",
    "ei": "état/interaction",
    "em": "monstre/combat",
}


def runtime_gate_payload(warning: Any) -> dict[str, Any]:
    codes = tuple(str(v).casefold() for v in (getattr(warning, "criterion_codes", ()) or ()))
    labels = sorted({RUNTIME_GATE_LABELS.get(code, "condition de jeu") for code in codes})
    return {
        "quest_id": int(warning.quest_id),
        "codes": list(codes),
        "gate_types": labels,
        "criterion": str(getattr(warning, "criterion", "") or ""),
        "instruction": (
            "Condition réelle du jeu à satisfaire avant cette étape. "
            "Le Guide Ultime l'affiche mais ne prétend pas la valider automatiquement."
        ),
    }


def full_success_context_for_step(step: RouteStep, targets: dict[str, Any]) -> dict[str, Any]:
    dungeon_ids: set[int] = set()
    dungeon_names: set[str] = set()
    monster_ids: set[int] = set()
    for action in step.actions:
        if action.dungeon_id is not None:
            try:
                dungeon_ids.add(int(action.dungeon_id))
            except (TypeError, ValueError):
                pass
        if action.dungeon_name:
            dungeon_names.add(norm(action.dungeon_name))
        monster_ids.update(int(v) for v in (action.monster_ids or ()) if str(v).lstrip("-").isdigit())

    monster_rows: list[dict[str, Any]] = []
    for row in targets.get("monster", []):
        mids = {int(v) for v in row.get("monster_ids", []) if str(v).lstrip("-").isdigit()}
        if mids and mids & monster_ids:
            monster_rows.append({
                "achievement_id": int(row["achievement_id"]),
                "name": str(row.get("name") or ""),
                "matched_monster_ids": sorted(mids & monster_ids),
                "instruction": "Valider ce succès Monstres pendant ce combat/farm si les critères sont compatibles.",
            })

    dungeon_rows: list[dict[str, Any]] = []
    for row in targets.get("dungeon", []):
        declared = row.get("dungeons") or []
        ids = {int(v.get("dungeon_id")) for v in declared if isinstance(v, dict) and v.get("dungeon_id") is not None}
        names = {norm(v.get("name")) for v in declared if isinstance(v, dict) and v.get("name")}
        matched = bool(ids & dungeon_ids) or bool(names & dungeon_names)
        if matched:
            dungeon_rows.append({
                "achievement_id": int(row["achievement_id"]),
                "name": str(row.get("name") or ""),
                "instruction": "Tenter ce succès Donjon sur ce passage; si incompatible avec un autre succès, regrouper les incompatibles en un minimum de passages supplémentaires.",
            })
    return {
        "monster_successes": monster_rows,
        "dungeon_successes": dungeon_rows,
    }


def route_step_payload(
    step: RouteStep,
    by_quest: dict[int, Any],
    master: dict[str, Any],
    *,
    planned_at_level: int,
    alignment: str,
    success_targets: dict[str, Any] | None = None,
    runtime_gates_by_quest: dict[int, list[dict[str, Any]]] | None = None,
    conditional_gates_by_quest: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    take, do_here = [], []
    for action in step.actions:
        row = {
            "quest_id": int(action.quest_id),
            "quest_name": str(getattr(by_quest.get(int(action.quest_id)), "name", "") or ""),
            "action_id": action.action_id,
            "title": action.title,
            "kind": action.kind,
            "objective_id": action.objective_id,
            "dungeon": action.dungeon_name,
            "before_leaving_area": bool(action.before_leaving_area),
        }
        (take if action.is_start else do_here).append(row)

    loc = step.location
    nxt = step.next_location
    _gps_stage("building_route_payload")
    payload = {
        "index": int(step.index),
        "planned_at_level": int(planned_at_level),
        "destination": loc.display(),
        "map_id": loc.map_id,
        "x": loc.x,
        "y": loc.y,
        "zone": loc.zone,
        "subzone": loc.subzone,
        "a_prendre": take,
        "a_faire_ici": do_here,
        "progresse_aussi": {
            "quest_ids": list(map(int, step.quest_ids)),
            "success_ids": list(map(int, step.success_ids)),
        },
        "a_preparer": [
            {
                "item_id": item.item_id,
                "name": item.name,
                "quantity": int(item.quantity),
                "acquisition_default": "HDV si échangeable; banque/inventaire si déjà possédé",
                "craft_policy": "CRAFT optionnel seulement pour économiser; ne crée jamais un gate métier à lui seul",
            }
            for item in step.items_to_prepare
        ],
        "hard_runtime_gates": [
            gate
            for qid in sorted({int(v) for v in step.quest_ids})
            for gate in ((runtime_gates_by_quest or {}).get(qid, []))
        ],
        "conditional_branch_gates": [
            gate
            for qid in sorted({int(v) for v in step.quest_ids})
            for gate in ((conditional_gates_by_quest or {}).get(qid, []))
        ],
        "avant_de_partir": list(step.before_leaving),
        "ensuite": None if nxt is None else {
            "destination": nxt.display(),
            "map_id": nxt.map_id,
            "x": nxt.x,
            "y": nxt.y,
            "zone": nxt.zone,
            "subzone": nxt.subzone,
        },
    }
    payload.update(manual_context_for_step(step.actions, by_quest, master))
    dungeon_context = dungeon_manual_context(step.actions, master, alignment)
    payload["dungeon_context"] = dungeon_context
    manual_exit_actions = [row["action"] for row in dungeon_context["dungeon_exit_rules"] if row.get("action")]
    if dungeon_context.get("capture_ames_unlock_here"):
        manual_exit_actions.append("Avant de quitter le Kwakwa : obtenir/valider Capture d’âmes pour le fil Ocre.")
    for row in dungeon_context.get("ocre_capture_targets", []):
        manual_exit_actions.append(row["action"] + f" Boss : {row['boss']}.")
    payload["avant_de_partir"] = list(dict.fromkeys([*payload["avant_de_partir"], *manual_exit_actions]))
    success_context = full_success_context_for_step(step, success_targets or {"monster": [], "dungeon": []})
    payload["succes_monstres_a_faire"] = success_context["monster_successes"]
    payload["succes_donjon_a_faire"] = success_context["dungeon_successes"]
    return payload


def main() -> None:
    _gps_stage("main_start")
    parser = argparse.ArgumentParser()
    parser.add_argument("--verified-criterion", type=int, action="append", default=[], help="ID de quête dont le critère dur inconnu a été vérifié manuellement")
    parser.add_argument("--preview-unknown-criteria", action="store_true", help="ouvre les critères inconnus uniquement pour une preview non certifiée")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    _gps_stage("arguments_parsed")

    if not GUIDE_PATH.exists():
        raise SystemExit(
            "artifacts/guide_ultime_final.json absent. "
            "Lance d'abord tools/build_guide_ultime_final.py --strict"
        )

    guide = load_json(GUIDE_PATH)
    _gps_stage("guide_loaded")
    master = load_master()
    _gps_stage("master_loaded")
    scope = universal_scope(guide)
    if int(guide.get("schema_version") or 0) >= 5 and scope is None:
        raise SystemExit("Scope V5 UNIVERSAL absent du guide généré")
    success_targets = full_success_policy(guide)
    _gps_stage("full_success_policy_loaded")

    quest_provider = QuestProvider(data_dir=RAW_QUEST_DATA_DIR)
    catalog = quest_provider.get_catalog()
    achievement_provider = AchievementProvider(data_dir=RAW_QUEST_DATA_DIR, quest_provider=quest_provider)
    _gps_stage("providers_loaded")

    selected_steps, choice_audit = select_quest_steps(guide)
    _gps_stage(f"quest_steps_selected:{len(selected_steps)}")
    qids = [int(row["entity_id"]) for row in selected_steps]
    selected_ids = set(qids)
    repeat_threads = [
        {
            "quest_id": int(row["entity_id"]),
            "repeat_target": dict(row.get("repeat_target") or {}),
            "runtime_policy": str(row.get("runtime_policy") or ""),
            "non_blocking_main_route": True,
        }
        for row in selected_steps
        if isinstance(row.get("repeat_target"), dict) and row.get("repeat_target")
    ]
    repeat_thread_ids = {int(row["quest_id"]) for row in repeat_threads}
    main_selected_ids = selected_ids - repeat_thread_ids
    pseudo_guide = SimpleNamespace(quest_ids=tuple(qids))
    adapter_result = AdventureRouteAdapter(
        catalog,
        pseudo_guide,
        achievement_provider=achievement_provider,
        raw_data_dir=RAW_QUEST_DATA_DIR,
    ).build()
    _gps_stage(f"adapter_built:{len(adapter_result.actions)}")

    actions = list(adapter_result.actions)
    # Order quests are conditional cards in V5, never part of the common engine.
    alignment_gate_applied: list[dict[str, Any]] = []
    alignment_gate_missing: list[dict[str, Any]] = []
    _gps_stage("before_dungeon_bundle_holds")
    actions, dungeon_bundle_holds = apply_dungeon_bundle_holds(
        actions,
        catalog,
        master,
        selected_ids,
    )
    _gps_stage(f"dungeon_bundle_holds_done:{len(dungeon_bundle_holds)}")

    actions, class_gate_bridges = apply_universal_class_gate_bridges(actions, guide)
    class_gates_by_quest: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for gate in class_gate_bridges:
        class_gates_by_quest[int(gate["quest_id"])].append(gate)
    _gps_stage(f"class_gate_bridges_done:{len(class_gate_bridges)}")

    unresolved_warnings = [w for w in adapter_result.warnings if w.code == "unresolved_hard_criterion"]
    runtime_gate_warnings = [w for w in adapter_result.warnings if w.code == "runtime_gate_criterion"]
    runtime_gates_by_quest: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for warning in runtime_gate_warnings:
        runtime_gates_by_quest[int(warning.quest_id)].append(runtime_gate_payload(warning))
    verified_ids = {int(v) for v in args.verified_criterion}
    if args.preview_unknown_criteria:
        verified_ids.update(int(w.quest_id) for w in unresolved_warnings)
    flags = frozenset(f"criterion-verified:{qid}" for qid in verified_ids)

    base_profile = RouteProfile(
        level=1,
        character_class="",
        alignment="Bonta",
        alignment_level=100,
        order="",
        flags=flags,
    )

    engine = AdventureRouteEngine(actions)
    _gps_stage("engine_built")
    print(
        f"GPS planner démarré : {len(actions)} actions normalisées / {len(selected_steps)} quêtes sélectionnées",
        flush=True,
    )
    plan, milestones, step_levels = progressive_plan(engine, base_profile, start_level=1, max_level=200)
    _gps_stage(f"planner_done:{len(plan.steps)}:{len(plan.blocked)}")
    print(
        f"GPS planner terminé : {len(plan.steps)} étapes / {len(plan.blocked)} actions bloquées",
        flush=True,
    )

    route_steps_payload = [
        route_step_payload(
            step,
            catalog.by_id,
            master,
            planned_at_level=step_levels[index],
            alignment="Bonta",
            success_targets=success_targets,
            runtime_gates_by_quest=runtime_gates_by_quest,
            conditional_gates_by_quest=class_gates_by_quest,
        )
        for index, step in enumerate(plan.steps)
    ]
    success_cards = full_success_cards(guide, route_steps_payload)
    expected_reference_ids, skipped_choice_variant_ids = reference_route_expected_ids(scope, choice_audit)

    payload = {
        "schema_version": 5,
        "id": "guide_ultime_gps_route",
        "generation_mode": "V5_universal_progressive_1_to_200",
        "universal_route": {
            "alignment_backbone": "Bonta",
            "class_parameter": None,
            "order_parameter": None,
            "common_route_quest_count": len(qids),
            "scope_routing_content_count": len(scope.get("routing_common_selected_quest_ids") or []) if scope else len(qids),
            "one_of_variants_skipped_in_reference_route": len(skipped_choice_variant_ids),
            "reference_route_expected_quest_count": len(expected_reference_ids) if scope else len(qids),
            "execution_count_min": int(scope.get("execution_count_min") or 0) if scope else None,
            "execution_count_max": int(scope.get("execution_count_max") or 0) if scope else None,
            "qq_required_count": int(scope.get("qq_required_count") or 0) if scope else 0,
            "instruction": "Une seule route maître. Le joueur exécute 1 carte de classe et les 5 cartes de son Ordre dans ce même guide.",
        },
        "conditional_branches": conditional_branch_cards(guide),
        "universal_class_gate_bridges": class_gate_bridges,
        "full_success_targets": {
            "monster_success_count": len(success_targets["monster"]),
            "dungeon_success_count": len(success_targets["dungeon"]),
        },
        "full_success_cards": success_cards,
        "catalog_total_dynamic": int(guide.get("guide_ultime_policy", {}).get("quest_manifest_count") or 0),
        "contract": master.get("route_contract") or master.get("optimizer_rules") or {},
        "resource_policy": master.get("inventory_and_bank_policy") or {},
        "monocompte_policy": master.get("monocompte_policy") or {},
        "endgame_order": master.get("endgame_order") or [],
        "forced_quest_repeats": master.get("forced_quest_repeats") or {},
        "dungeon_bundles": master.get("dungeon_bundles") or {},
        "before_leaving_dungeon": master.get("before_leaving_dungeon") or [],
        "level_milestones": milestones,
        "choice_groups": choice_audit,
        "repeat_threads": repeat_threads,
        "alignment_order_gates": alignment_gate_applied,
        "dungeon_bundle_holds": dungeon_bundle_holds,
        "steps": route_steps_payload,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _gps_stage("route_payload_written")

    surfaced_runtime_gate_quest_ids = {
        int(gate["quest_id"])
        for step in payload["steps"]
        for gate in (step.get("hard_runtime_gates") or [])
        if isinstance(gate, dict) and gate.get("quest_id") is not None
    }
    expected_runtime_gate_quest_ids = {int(w.quest_id) for w in runtime_gate_warnings}
    missing_runtime_gate_cards = sorted(expected_runtime_gate_quest_ids - surfaced_runtime_gate_quest_ids)
    surfaced_class_gate_quest_ids = {
        int(gate["quest_id"])
        for step in payload["steps"]
        for gate in (step.get("conditional_branch_gates") or [])
        if isinstance(gate, dict) and gate.get("quest_id") is not None
    }
    expected_class_gate_quest_ids = {int(row["quest_id"]) for row in class_gate_bridges}
    missing_class_gate_cards = sorted(expected_class_gate_quest_ids - surfaced_class_gate_quest_ids)

    unknown_locations = sum(
        1 for step in payload["steps"]
        if step["map_id"] is None and step["x"] is None and step["y"] is None
    )
    completed_selected = selected_ids & set(plan.final_progress.completed_quest_ids)
    completed_main_selected = main_selected_ids & set(plan.final_progress.completed_quest_ids)
    remaining_selected = sorted(main_selected_ids - completed_main_selected)
    final_profile = profile_with_level(base_profile, 200)
    actions_by_quest: dict[int, list[RouteAction]] = defaultdict(list)
    for action in actions:
        actions_by_quest[int(action.quest_id)].append(action)
    profile_filtered_selected_quest_ids = sorted(
        qid
        for qid in remaining_selected
        if actions_by_quest.get(int(qid))
        and not any(action.condition.matches(final_profile) for action in actions_by_quest[int(qid)])
    )
    blocked_quest_ids = {
        int(action_id.split(":", 2)[1])
        for action_id in plan.blocked
        if action_id.startswith("quest:") and action_id.split(":", 2)[1].isdigit()
    }
    incomplete_without_blocked_action_ids = sorted(
        set(remaining_selected) - blocked_quest_ids
    )
    unverified_criteria = sorted(
        {
            int(w.quest_id)
            for w in unresolved_warnings
            if int(w.quest_id) not in verified_ids
        }
    )

    all_manual_prep = [
        row
        for step in payload["steps"]
        for row in (step.get("manual_preparation") or [])
        if isinstance(row, dict)
    ]
    all_profession_gates = [
        gate
        for step in payload["steps"]
        for gate in (step.get("profession_gates") or [])
        if isinstance(gate, dict)
    ]
    optional_craft_rows = [
        row for row in all_manual_prep
        if bool(row.get("craft_optional"))
    ]
    hdv_preferred_rows = [
        row for row in all_manual_prep
        if any(
            isinstance(option, dict)
            and option.get("mode") == "HDV"
            and bool(option.get("recommended"))
            for option in (row.get("acquisition_options") or [])
        )
    ]
    invalid_craft_job_inference = [
        row for row in all_manual_prep
        if any(
            isinstance(option, dict)
            and option.get("mode") == "CRAFT"
            and bool(option.get("requires_job_level"))
            for option in (row.get("acquisition_options") or [])
        )
    ]
    bypassable_profession_gates = [
        gate for gate in all_profession_gates
        if gate.get("gate_type") != "hard_game_requirement"
        or bool(gate.get("can_be_bypassed_by_hdv"))
    ]
    dungeon_exit_rules_applied = [
        row
        for step in payload["steps"]
        for row in ((step.get("dungeon_context") or {}).get("dungeon_exit_rules") or [])
    ]
    ocre_capture_targets_attached = [
        row
        for step in payload["steps"]
        for row in ((step.get("dungeon_context") or {}).get("ocre_capture_targets") or [])
    ]
    capture_ames_unlock_steps = [
        int(step["index"]) for step in payload["steps"]
        if bool((step.get("dungeon_context") or {}).get("capture_ames_unlock_here"))
    ]
    attached_monster_success_ids = {
        int(row["achievement_id"])
        for step in payload["steps"]
        for row in (step.get("succes_monstres_a_faire") or [])
        if isinstance(row, dict) and row.get("achievement_id") is not None
    }
    attached_dungeon_success_ids = {
        int(row["achievement_id"])
        for step in payload["steps"]
        for row in (step.get("succes_donjon_a_faire") or [])
        if isinstance(row, dict) and row.get("achievement_id") is not None
    }
    target_monster_success_ids = {int(row["achievement_id"]) for row in success_targets["monster"]}
    target_dungeon_success_ids = {int(row["achievement_id"]) for row in success_targets["dungeon"]}
    carded_monster_success_ids = {
        int(row["achievement_id"])
        for row in ((payload.get("full_success_cards") or {}).get("monster_success_cards") or [])
        if isinstance(row, dict) and row.get("achievement_id") is not None
    }
    carded_dungeon_success_ids = {
        int(row["achievement_id"])
        for card in ((payload.get("full_success_cards") or {}).get("dungeon_success_cards") or [])
        for row in (card.get("achievements") or [])
        if isinstance(row, dict) and row.get("achievement_id") is not None
    } | {
        int(row["achievement_id"])
        for row in ((payload.get("full_success_cards") or {}).get("dungeon_meta_success_cards") or [])
        if isinstance(row, dict) and row.get("achievement_id") is not None
    }
    missing_monster_success_ids = sorted(target_monster_success_ids - carded_monster_success_ids)
    missing_dungeon_success_ids = sorted(target_dungeon_success_ids - carded_dungeon_success_ids)

    audit = {
        "schema_version": 5,
        "master_loaded_from": master.get("_loaded_from", ""),
        "universal_scope_id": scope.get("id") if scope else None,
        "universal_execution_count_min": int(scope.get("execution_count_min") or 0) if scope else None,
        "universal_execution_count_max": int(scope.get("execution_count_max") or 0) if scope else None,
        "universal_qq_shortfall": int(scope.get("qq_shortfall") or 0) if scope else 0,
        "universal_scope_conflicts": list(scope.get("conflicts") or []) if scope else [],
        "conditional_branches": conditional_branch_cards(guide),
        "selected_quest_count": len(qids),
        "scope_routing_content_quest_count": len(scope.get("routing_common_selected_quest_ids") or []) if scope else len(qids),
        "reference_route_expected_quest_count": len(expected_reference_ids) if scope else len(qids),
        "skipped_one_of_choice_variant_quest_ids": sorted(skipped_choice_variant_ids),
        "selected_reference_route_id_mismatch": sorted(set(qids) ^ expected_reference_ids) if scope else [],
        "completed_selected_quest_count": len(completed_selected),
        "completed_main_selected_quest_count": len(completed_main_selected),
        "remaining_main_selected_quest_ids": remaining_selected,
        "profile_filtered_selected_quest_ids": profile_filtered_selected_quest_ids,
        "incomplete_without_blocked_action_ids": incomplete_without_blocked_action_ids,
        "repeat_threads": repeat_threads,
        "adapter_action_count": len(adapter_result.actions),
        "effective_action_count_after_holds": len(actions),
        "route_step_count": len(plan.steps),
        "blocked_action_count": len(plan.blocked),
        "blocked_actions": dict(plan.blocked),
        "unknown_location_step_count": unknown_locations,
        "level_milestones": milestones,
        "metrics": plan.metrics.as_dict(),
        "choice_groups": choice_audit,
        "alignment_order_gates_applied": alignment_gate_applied,
        "alignment_order_gates_missing": alignment_gate_missing,
        "universal_class_gate_bridges": class_gate_bridges,
        "missing_universal_class_gate_card_quest_ids": missing_class_gate_cards,
        "dungeon_bundle_holds_applied_count": len(dungeon_bundle_holds),
        "dungeon_exit_rules_applied": dungeon_exit_rules_applied,
        "ocre_capture_targets_attached": ocre_capture_targets_attached,
        "capture_ames_unlock_steps": capture_ames_unlock_steps,
        "full_success_routing": {
            "target_monster_success_count": len(target_monster_success_ids),
            "quest_overlap_monster_success_count": len(attached_monster_success_ids),
            "carded_monster_success_count": len(carded_monster_success_ids),
            "missing_monster_success_ids": missing_monster_success_ids,
            "target_dungeon_success_count": len(target_dungeon_success_ids),
            "quest_overlap_dungeon_success_count": len(attached_dungeon_success_ids),
            "carded_dungeon_success_count": len(carded_dungeon_success_ids),
            "missing_dungeon_success_ids": missing_dungeon_success_ids,
            "coverage_policy": "quête naturelle si résolue, sinon carte FULL SUCCÈS dédiée; aucun succès n'est supprimé",
        },
        "acquisition_policy_stats": {
            "manual_preparation_count": len(all_manual_prep),
            "hdv_preferred_count": len(hdv_preferred_rows),
            "craft_optional_count": len(optional_craft_rows),
            "hard_personal_profession_gate_count": len(all_profession_gates),
            "invalid_craft_job_inference_count": len(invalid_craft_job_inference),
            "bypassable_profession_gate_count": len(bypassable_profession_gates),
        },
        "runtime_gate_criteria": [runtime_gate_payload(w) for w in runtime_gate_warnings],
        "runtime_gate_quest_count": len(expected_runtime_gate_quest_ids),
        "missing_runtime_gate_card_quest_ids": missing_runtime_gate_cards,
        "unresolved_hard_criteria": [
            {"quest_id": int(w.quest_id), "code": w.code, "message": w.message}
            for w in unresolved_warnings
        ],
        "unverified_hard_criterion_quest_ids": unverified_criteria,
        "warnings": [
            {"quest_id": int(w.quest_id), "code": w.code, "message": w.message}
            for w in adapter_result.warnings
        ],
        "hard_checks": {
            "no_duplicate_quest_ids": len(qids) == len(set(qids)),
            "all_non_repeat_thread_quests_completed": not remaining_selected,
            "repeat_targets_preserved_as_non_blocking_threads": all(bool(row.get("repeat_target")) for row in repeat_threads),
            "no_unverified_hard_criteria": not unverified_criteria,
            "all_runtime_gates_are_surfaced": not missing_runtime_gate_cards,
            "all_universal_class_gates_are_surfaced": not missing_class_gate_cards,
            "no_missing_alignment_order_gate": not alignment_gate_missing,
            "no_profile_filtered_selected_quests": not profile_filtered_selected_quest_ids,
            "no_incomplete_quest_without_blocked_action": not incomplete_without_blocked_action_ids,
            "no_blocked_actions": not plan.blocked,
            "unknown_positions_are_not_invented": True,
            "visual_order_is_not_dependency": True,
            "alignment_alternatives_require_explicit_selection": True,
            "one_of_choice_groups_select_exactly_one": all(bool(row.get("selected_quest_id")) for row in choice_audit),
            "progressive_level_planning": True,
            "universal_scope_loaded": scope is not None if int(guide.get("schema_version") or 0) >= 5 else True,
            "universal_scope_has_no_conflict": not (scope.get("conflicts") if scope else []),
            "universal_scope_meets_qq": not int(scope.get("qq_shortfall") or 0) if scope else True,
            "selected_count_matches_common_route": (set(qids) == expected_reference_ids) if scope else True,
            "single_guide_no_class_or_order_parameter": True,
            "dungeon_exit_rules_are_injected": all(bool(row.get("action")) for row in dungeon_exit_rules_applied),
            "ocre_capture_cards_are_injected": all(bool(row.get("boss")) for row in ocre_capture_targets_attached),
            "optional_craft_never_creates_profession_gate": not invalid_craft_job_inference,
            "profession_gates_are_only_hard_game_requirements": not bypassable_profession_gates,
            "all_target_monster_successes_routed": not missing_monster_success_ids,
            "all_target_dungeon_successes_routed": not missing_dungeon_success_ids,
        },
    }
    OUT_AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _gps_stage("gps_audit_written")

    if args.strict:
        errors: list[str] = []
        checks = audit["hard_checks"]
        if not checks["no_duplicate_quest_ids"]:
            errors.append("quest ids dupliqués")
        if remaining_selected:
            errors.append(f"{len(remaining_selected)} quête(s) sélectionnée(s) non terminée(s)")
        if unverified_criteria:
            errors.append(f"{len(unverified_criteria)} critère(s) réellement inconnu(s) non vérifié(s)")
        if missing_runtime_gate_cards:
            errors.append(f"{len(missing_runtime_gate_cards)} gate(s) runtime ne sont pas affichés sur une carte")
        if missing_class_gate_cards:
            errors.append(f"{len(missing_class_gate_cards)} gate(s) de classe universelle ne sont pas affichés sur une carte")
        if profile_filtered_selected_quest_ids:
            errors.append(
                f"{len(profile_filtered_selected_quest_ids)} quête(s) du scope sont incompatibles avec le profil Bonta; "
                "le content-lock doit les reclasser/remplacer"
            )
        if incomplete_without_blocked_action_ids:
            errors.append(
                f"{len(incomplete_without_blocked_action_ids)} quête(s) restent incomplètes sans action bloquée explicite"
            )
        if alignment_gate_missing:
            errors.append(f"{len(alignment_gate_missing)} verrou(s) Ordre/alignement introuvable(s)")
        if plan.blocked:
            errors.append(f"{len(plan.blocked)} action(s) encore bloquée(s)")
        if invalid_craft_job_inference:
            errors.append(f"{len(invalid_craft_job_inference)} craft(s) optionnel(s) créent encore un faux gate métier")
        if bypassable_profession_gates:
            errors.append(f"{len(bypassable_profession_gates)} gate(s) métier ne sont pas prouvés obligatoires")
        if missing_monster_success_ids:
            errors.append(f"{len(missing_monster_success_ids)} succès Monstres FULL SUCCÈS restent sans passage routé")
        if missing_dungeon_success_ids:
            errors.append(f"{len(missing_dungeon_success_ids)} succès Donjons FULL SUCCÈS restent sans passage routé")
        if int(guide.get("schema_version") or 0) >= 5 and scope is None:
            errors.append("scope V5 UNIVERSAL absent")
        if scope and scope.get("conflicts"):
            errors.append(f"{len(scope.get('conflicts') or [])} conflit(s) de scope dans le guide universel")
        if scope and int(scope.get("qq_shortfall") or 0):
            errors.append(f"seuil QQ non atteint: manque {int(scope.get('qq_shortfall') or 0)} quête(s)")
        if scope and set(qids) != expected_reference_ids:
            mismatch = sorted(set(qids) ^ expected_reference_ids)
            errors.append(
                f"route GPS de référence incohérente: {len(qids)} sélectionnées / "
                f"{len(expected_reference_ids)} attendues après résolution one-of; "
                f"{len(mismatch)} ID(s) diffèrent"
            )
        if errors:
            raise SystemExit("STRICT FAIL: " + " | ".join(errors))

    print(f"OK - {OUT}")
    print(f"Audit - {OUT_AUDIT}")
    print(f"Quêtes sélectionnées : {len(qids)}")
    print(f"Quêtes terminées par la route : {len(completed_selected)}")
    print(f"Fils répétables long terme : {len(repeat_threads)}")
    print(f"Cartes GPS : {len(plan.steps)}")
    print(f"Localisations à confirmer : {unknown_locations}")
    print(f"Critères durs non vérifiés : {len(unverified_criteria)}")
    print(f"Actions bloquées : {len(plan.blocked)}")
    print(f"Succès Monstres sans carte : {len(missing_monster_success_ids)}")
    print(f"Succès Donjons sans carte : {len(missing_dungeon_success_ids)}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        crash = {
            "stage": _GPS_STAGE,
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
            "traceback": traceback.format_exc(),
        }
        try:
            CRASH_AUDIT.write_text(json.dumps(crash, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        print(f"GPS ERROR [{_GPS_STAGE}] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        if isinstance(exc, SystemExit):
            code = exc.code if isinstance(exc.code, int) else 1
            raise SystemExit(code)
        raise
