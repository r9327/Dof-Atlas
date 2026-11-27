from __future__ import annotations

import html
import re
from functools import lru_cache
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable

from app.core.item_artwork import (
    item_icon_index, item_icon_path,
)
from app.core.map_coordinates import (
    BRACKETED_POSITION_RE as COORD_RE,
    canonical_declared_coordinate,
    quest_launch_instruction,
    quest_launch_position_evidence,
    travel_command_from_position,
)
from app.core.numbers import format_grouped_int, optional_int as _safe_int
from app.modules.encyclopedia.models import (
    Achievement,
    EntityRef,
    Guide,
    GuideActivity,
    GuideRequiredItem,
    GuideStep,
)
from app.modules.encyclopedia.providers import AchievementProvider
from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.modules.encyclopedia.services.guide_progress_wording import guide_progress_noun
from app.quest_catalog import (
    QuestObjective,
    QuestRecord,
    QuestReward,
    QuestSolutionBlock,
    normalize_text,
    resolve_local_asset_path,
    safe_int,
)


ITEM_OBJECTIVE_TYPES = {2, 3, 17}
COMBAT_OBJECTIVE_TYPES = {6, 7}
NPC_OBJECTIVE_TYPES = {1, 9, 10}
TECHNICAL_CRITERION_RE = re.compile(
    r"\b(?:Qf|Qa|Qo|Ps|Pa|Pz|Po|EM|PL|BT|Sc|SC|ST|OA|HA|AN)\s*[=<>!]",
    re.IGNORECASE,
)
KAMAS_REWARD_RE = re.compile(r"^(\d[\d\s]*)\s*(?:k|kamas)\b", re.IGNORECASE)
SOURCE_QUANTITY_REWARD_RE = re.compile(r"^(?:x\s*)?\d+\s*x?\s+.+", re.IGNORECASE)
SOURCE_REWARD_SENTENCE_RE = re.compile(
    r"^(?:note\b|la qu[eê]te\b|vous pouvez\b|la prochaine\b|rendez-vous\b|retournez\b|parlez\b|allez\b|pour obtenir\b)",
    re.IGNORECASE,
)
MARKUP_RE = re.compile(r"\{\{[^{}:]+(?:::[^{}]+)?\}\}")
DISCOVER_MAP_RE = re.compile(r"^Découvrir la carte\s*:\s*\d+", re.IGNORECASE)
ARTIFICIAL_STEP_TITLE_RE = re.compile(r"^(?:É|E)tape\s+\d+$", re.IGNORECASE)
MINIMAP_PLACEHOLDER_RE = re.compile(r"\s*Mini-carte\s+L[’']aperçu de la carte sera affiché ici sur le site\.?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DisplayItem:
    item_id: int | None
    name: str
    quantity: int | None = None
    image_path: str = ""
    consumed: bool = True
    preparable: bool = False


@dataclass(frozen=True, slots=True)
class DisplayReward:
    kind: str
    name: str
    quantity: int | None = None
    image_path: str = ""


@dataclass(frozen=True, slots=True)
class QuestStartInfo:
    level: str = ""
    npc: str = ""
    position: str = ""
    zone: str = ""
    map_image_path: str = ""
    map_image_paths: tuple[str, ...] = ()
    declared_launch_position: str = ""
    declared_launch_npc: str = ""
    launch_status: str = "NO_DECLARED_START"
    launch_instruction: str = ""


@dataclass(frozen=True, slots=True)
class QuestRelatedInfo:
    previous: tuple[EntityRef, ...] = ()
    next: tuple[EntityRef, ...] = ()
    series: tuple[EntityRef, ...] = ()
    achievements: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SolutionObjective:
    text: str
    objective_id: int | None = None
    image_path: str = ""
    item_id: int | None = None
    quantity: int = 0
    combat: bool = False
    position: str = ""


@dataclass(frozen=True, slots=True)
class SolutionStep:
    title: str
    description: str
    objectives: tuple[SolutionObjective, ...] = ()


@dataclass(frozen=True, slots=True)
class DisplaySolutionBlock:
    block_type: str
    content: str = ""
    position: str = ""
    image_path: str = ""
    caption: str = ""
    data: dict[str, object] = field(default_factory=dict)


ACTIVITY_LABELS = {
    "quest": "Quêtes",
    "solo_fight": "Solo",
    "group_fight": "Groupe",
    "tactical_fight": "Combat tactique",
    "dungeon": "Donjon",
    "farm": "Farm",
    "boss": "Boss",
    "dreams": "Songes",
    "slab": "Dalle",
}


def guide_level_text(guide: Guide) -> str:
    minimum = _positive_level(guide.recommended_level_min)
    maximum = _positive_level(guide.recommended_level_max)
    if minimum is not None and maximum is not None and minimum != maximum:
        return f"Niveaux {minimum} à {maximum}"
    if minimum is not None and maximum is not None:
        return f"Niveau {minimum}"
    if minimum is not None:
        return f"Niveau {minimum} et plus"
    return ""


def quest_level_text(quest: QuestRecord) -> str:
    minimum = _positive_level(quest.level_min)
    if minimum is not None:
        return f"Niveau minimum : {minimum}"
    return ""


def guide_step_count_text(guide: Guide) -> str:
    total = sum(1 for step in guide.required_steps if step.counts_for_completion)
    return f"{total} {guide_progress_noun(guide, total)}" if total else ""


def guide_prerequisites(
    guide: Guide,
    graph: QuestGraphService | None = None,
    catalog_by_id: dict[int, QuestRecord] | None = None,
) -> tuple[str, ...]:
    guide_keys = _guide_step_keys(guide)
    guide_quest_ids = set(guide.quest_ids)
    lines: list[str] = []
    for step in guide.steps:
        for ref in step.prerequisites:
            if (ref.entity_type, ref.entity_id) not in guide_keys:
                _add_unique_line(lines, ref.label)
    first_quest = next(
        (
            step
            for step in guide.steps
            if step.step_type == "quest" and step.entity_id is not None and step.counts_for_completion
        ),
        None,
    )
    if first_quest is not None and catalog_by_id is not None:
        quest = catalog_by_id.get(int(first_quest.entity_id))
        if quest is not None:
            for line in quest.prerequisites:
                _add_unique_line(lines, clean_requirement_line(line))
    if first_quest is not None and graph is not None:
        for quest_id in graph.previous_ids(int(first_quest.entity_id)):
            if quest_id in guide_quest_ids:
                continue
            quest = graph.catalog.by_id.get(int(quest_id))
            if quest is not None:
                _add_unique_line(lines, quest.name)
    return tuple(lines[:8])


def step_prerequisites(
    guide: Guide,
    step: GuideStep,
    graph: QuestGraphService | None = None,
    catalog_by_id: dict[int, QuestRecord] | None = None,
) -> tuple[str, ...]:
    lines: list[str] = []
    for ref in step.prerequisites:
        _add_unique_line(lines, ref.label)
    if step.step_type == "quest" and step.entity_id is not None and catalog_by_id is not None:
        quest = catalog_by_id.get(int(step.entity_id))
        if quest is not None:
            for line in quest.prerequisites:
                _add_unique_line(lines, clean_requirement_line(line))
    if step.step_type == "quest" and step.entity_id is not None and graph is not None:
        for quest_id in graph.previous_ids(int(step.entity_id)):
            quest = graph.catalog.by_id.get(int(quest_id))
            if quest is not None:
                _add_unique_line(lines, quest.name)
    return tuple(lines[:10])


def guide_items(guide: Guide) -> tuple[DisplayItem, ...]:
    return _merge_items(
        item
        for part in guide.parts
        for item in (*part.required_items, *tuple(item for chapter in part.chapters for item in chapter.required_items), *tuple(item for chapter in part.chapters for series in chapter.series for item in series.required_items))
    )


def quest_items(
    guide: Guide,
    quest: QuestRecord,
) -> tuple[DisplayItem, ...]:
    guide_rows = _merge_items(item for item in _raw_required_items(guide) if item.quest_id == quest.id)
    objective_rows = quest_items_from_objectives(quest)
    return _merge_display_items([*guide_rows, *objective_rows])


def quest_items_from_objectives(quest: QuestRecord) -> tuple[DisplayItem, ...]:
    rows: list[DisplayItem] = []
    for step in quest.steps:
        for objective in step.objectives:
            if objective.item_id is None:
                continue
            if int(objective.type_id or 0) not in ITEM_OBJECTIVE_TYPES:
                continue
            if _is_alteration_objective(objective):
                continue
            rows.append(
                DisplayItem(
                    item_id=int(objective.item_id),
                    name=objective.image_label or clean_text(objective.text),
                    quantity=max(1, int(objective.item_quantity)) if int(objective.item_quantity or 0) > 0 else None,
                    image_path=objective.image_path or _local_item_image_path(objective.item_id),
                    consumed=True,
                    preparable=False,
                )
            )
    source_info = getattr(quest, "source_info", {}) or {}
    if isinstance(source_info, dict):
        for item in source_info.get("required_items", []) or []:
            if not isinstance(item, dict):
                continue
            name = clean_text(item.get("name", ""))
            if not name:
                continue
            rows.append(
                DisplayItem(
                    item_id=_safe_int(item.get("item_id")),
                    name=name,
                    quantity=_safe_int(item.get("quantity")),
                    image_path=str(item.get("image_path") or "") or _local_item_image_path(_safe_int(item.get("item_id"))),
                    consumed=bool(item.get("consumed")) if item.get("consumed") is not None else True,
                    preparable=bool(item.get("preparable")),
                )
            )
    return _merge_display_items(rows)


def guide_activities(guide: Guide) -> tuple[str, ...]:
    activities = [
        activity
        for part in guide.parts
        for activity in (
            *part.activities,
            *tuple(activity for chapter in part.chapters for activity in chapter.activities),
            *tuple(activity for chapter in part.chapters for series in chapter.series for activity in series.activities),
        )
    ]
    return activity_labels(activities)


def quest_activity_labels(
    guide: Guide | None,
    quest: QuestRecord,
    step: GuideStep | None = None,
) -> tuple[str, ...]:
    labels = list(_guide_activity_labels_for_quest(guide, quest, step))
    source_labels = _source_preparation_labels(quest)
    if source_labels:
        for label in source_labels:
            _add_unique_line(labels, label)
        return tuple(labels)

    block_labels = _solution_block_preparation_labels(quest)
    if block_labels:
        for label in block_labels:
            _add_unique_line(labels, label)
        return tuple(labels)

    for info in quest.info:
        clean = clean_text(info)
        if not clean or _looks_technical(clean) or normalize_text(clean).startswith("aucun_combat"):
            continue
        local_label = _local_preparation_label(clean)
        if local_label:
            _add_unique_line(labels, local_label)
    return tuple(labels)


def _guide_activity_labels_for_quest(
    guide: Guide | None,
    quest: QuestRecord,
    step: GuideStep | None = None,
) -> tuple[str, ...]:
    if guide is None:
        return ()
    activities = [
        activity
        for part in guide.parts
        for activity in (
            *part.activities,
            *tuple(activity for chapter in part.chapters for activity in chapter.activities),
            *tuple(activity for chapter in part.chapters for series in chapter.series for activity in series.activities),
        )
        if activity.quest_id == quest.id or (step is not None and activity.quest_id == step.entity_id)
    ]
    return activity_labels(activities)


def _source_preparation_labels(quest: QuestRecord) -> tuple[str, ...]:
    source_info = getattr(quest, "source_info", {}) or {}
    if not isinstance(source_info, dict):
        return ()
    labels: list[str] = []
    for value in source_info.get("preparation", []) or []:
        label = _normalize_preparation_label(str(value or ""))
        if label:
            _add_unique_line(labels, label)
    return tuple(labels)


def _solution_block_preparation_labels(quest: QuestRecord) -> tuple[str, ...]:
    group_count = 0
    solo_count = 0
    tactical_count = 0
    dungeon_count = 0
    farm_labels: list[str] = []
    for block in getattr(quest, "solution_blocks", ()) or ():
        if not isinstance(block, QuestSolutionBlock):
            continue
        content = clean_text(block.content)
        key = normalize_text(content)
        data = block.data if isinstance(block.data, dict) else {}
        is_fight = block.block_type == "combat" and str(data.get("interaction") or "") == "fight"
        if bool(data.get("dungeon")):
            dungeon_count += 1
        if bool(data.get("tactical")) or "combat_tactique" in key or "sorte_de_combat_tactique" in key:
            tactical_count += 1
        if is_fight:
            if bool(data.get("group")) or "plusieurs" in key or "realisable_en_groupe" in key:
                group_count += 1
            elif not bool(data.get("dungeon")):
                solo_count += 1
        if bool(data.get("farm")) or "drop" in key or "taux_de_drop" in key:
            label = _drop_preparation_label(content)
            if label:
                _add_unique_line(farm_labels, label)
    labels: list[str] = []
    if solo_count:
        _add_unique_line(labels, _count_label(solo_count, "combat solo", "combats solo"))
    if group_count:
        _add_unique_line(labels, _count_label(group_count, "combat en groupe", "combats en groupe"))
    if tactical_count:
        _add_unique_line(labels, _count_label(tactical_count, "combat tactique", "combats tactiques"))
    if dungeon_count:
        _add_unique_line(labels, _count_label(dungeon_count, "Donjon", "Donjons"))
    for label in farm_labels:
        _add_unique_line(labels, label)
    return tuple(labels)


def _local_preparation_label(text: str) -> str:
    key = normalize_text(text)
    count_match = re.search(r"\b(\d+)\s+objectif", text, re.IGNORECASE)
    count = safe_int(count_match.group(1)) if count_match else None
    if "donjon" in key:
        return _count_label(1, "Donjon", "Donjons")
    if "combat_de_groupe" in key or "quete_de_groupe" in key or "groupe" in key:
        return _count_label(count or 1, "combat en groupe", "combats en groupe")
    if "combat" in key:
        return _count_label(count or 1, "combat", "combats")
    return ""


def _normalize_preparation_label(value: str) -> str:
    text = clean_text(value).rstrip(".")
    if not text or _looks_technical(text):
        return ""
    dungeon_match = re.match(r"^(\d+)\s*x\s+Donjon\s+(.+)$", text, re.IGNORECASE)
    if dungeon_match:
        count = safe_int(dungeon_match.group(1)) or 1
        name = clean_text(dungeon_match.group(2)).rstrip(".")
        return f"{count} x Donjon : {name}" if name else _count_label(count, "Donjon", "Donjons")
    count_match = re.match(r"^(\d+)\s*x\s+combats?\b(.*)$", text, re.IGNORECASE)
    if count_match:
        count = safe_int(count_match.group(1)) or 1
        suffix = normalize_text(count_match.group(2))
        wave = " à vagues" if "vagues" in suffix else ""
        if "tactique" in suffix:
            return _count_label(count, f"combat{wave} tactique", f"combats{wave} tactiques")
        if "groupe" in suffix:
            return _count_label(count, f"combat{wave} en groupe", f"combats{wave} en groupe")
        if "seul" in suffix or "solo" in suffix:
            return _count_label(count, f"combat{wave} solo", f"combats{wave} solo")
        return _count_label(count, f"combat{wave}", f"combats{wave}")
    drop = _drop_preparation_label(text)
    return drop or text


def _drop_preparation_label(text: str) -> str:
    clean = clean_text(text).rstrip(".")
    key = normalize_text(clean)
    if "drop" not in key:
        return ""
    rate_match = re.search(r"(\d+)\s*%", clean)
    if "monstres" in key and "zone" in key:
        return f"Drop : combats de zone à {rate_match.group(1)}%" if rate_match else "Drop : combats de zone"
    return clean


def _count_label(count: int, singular: str, plural: str) -> str:
    count = max(1, int(count or 1))
    return f"{count} x {singular if count == 1 else plural}"


def activity_labels(activities: Iterable[GuideActivity]) -> tuple[str, ...]:
    labels: list[str] = []
    for activity in activities:
        label = ACTIVITY_LABELS.get(activity.activity_type)
        if label:
            _add_unique_line(labels, label)
    return tuple(labels)


def guide_rewards(
    guide: Guide,
    achievement_provider: AchievementProvider | None = None,
    quests: Iterable[QuestRecord] = (),
) -> tuple[DisplayReward, ...]:
    rows: list[DisplayReward] = []
    if guide.reward_item is not None:
        rows.append(
            DisplayReward(
                kind="item",
                name=guide.reward_item.name,
                quantity=1,
                image_path=guide.reward_item.image_path,
            )
        )
    if achievement_provider is not None:
        for achievement in guide_achievements(guide, achievement_provider):
            rows.extend(display_rewards_from_achievement(achievement))
    guide_rows = list(_dedupe_rewards(rows))
    quest_rows: list[DisplayReward] = []
    for quest in quests:
        quest_rows.extend(quest_rewards(quest))
        xp = sum(
            int(reward.quantity or 0)
            for reward in quest.rewards
            if str(getattr(reward, "kind", "") or "") in {"xp", "xp_ratio"}
        )
        if xp > 0:
            quest_rows.append(DisplayReward(kind="xp", name="Expérience", quantity=xp))
    aggregated = _aggregate_global_rewards(guide_rows, quest_rows)
    primary_name = normalize_text(guide.reward_item.name) if guide.reward_item is not None else ""
    kind_order = {
        "xp": 1,
        "kamas": 2,
        "achievement_points": 3,
        "title": 4,
        "ornament": 4,
        "emote": 4,
        "spell": 4,
        "job": 4,
        "alteration": 4,
        "item": 5,
        "source": 6,
    }
    return tuple(
        sorted(
            aggregated,
            key=lambda reward: (
                0
                if primary_name and normalize_text(reward.name) == primary_name
                else kind_order.get(reward.kind, 7),
                normalize_text(reward.name),
            ),
        )
    )


def quest_rewards(
    quest: QuestRecord,
    achievements: Iterable[Achievement] = (),
) -> tuple[DisplayReward, ...]:
    # Linked achievements describe the surrounding guide/success context. Their
    # rewards are not quest rewards and must not be injected into every quest.
    _ = achievements
    rows = [display_reward_from_quest(reward) for reward in quest.rewards]
    rows = [row for row in rows if row is not None]
    source_info = getattr(quest, "source_info", {}) or {}
    if isinstance(source_info, dict):
        required_names = {
            normalize_text(str(item.get("name") or ""))
            for item in source_info.get("required_items", []) or []
            if isinstance(item, dict)
        }
        resolved_reward_names = {normalize_text(row.name) for row in rows if row.name}
        has_resolved_kamas = any(row.kind == "kamas" for row in rows)
        for reward in source_info.get("rewards", []) or []:
            text = clean_text(reward)
            source_reward = display_reward_from_source_text(text)
            if source_reward is None:
                continue
            key = normalize_text(reward_label(source_reward))
            if any(name and name in key for name in required_names):
                continue
            if has_resolved_kamas and source_reward.kind == "kamas":
                continue
            if any(name and name in key for name in resolved_reward_names):
                continue
            rows.append(source_reward)
    return _dedupe_rewards(rows)


def guide_achievements(
    guide: Guide,
    achievement_provider: AchievementProvider,
) -> tuple[Achievement, ...]:
    ids: list[int] = []
    for ref in guide.context_entities:
        if ref.entity_type == "achievement":
            ids.append(int(ref.entity_id))
    for part in guide.parts:
        for chapter in part.chapters:
            for series in chapter.series:
                if series.achievement_id is not None:
                    ids.append(int(series.achievement_id))
    achievements: list[Achievement] = []
    seen: set[int] = set()
    for achievement_id in ids:
        if achievement_id in seen:
            continue
        seen.add(achievement_id)
        achievement = achievement_provider.get_by_id(achievement_id)
        if achievement is not None:
            achievements.append(achievement)
    return tuple(achievements)


def display_reward_from_quest(reward: QuestReward) -> DisplayReward | None:
    kind = str(getattr(reward, "kind", "") or "item")
    if kind in {"xp", "xp_ratio"}:
        return None
    name = clean_text(getattr(reward, "name", "") or "")
    if _looks_technical(name):
        return None
    if kind == "kamas" and int(getattr(reward, "quantity", 0) or 0) <= 0:
        return None
    return DisplayReward(
        kind=kind,
        name=name,
        quantity=getattr(reward, "quantity", None),
        image_path=str(getattr(reward, "image_path", "") or ""),
    )


def display_reward_from_source_text(text: str) -> DisplayReward | None:
    text = clean_text(text)
    key = normalize_text(text)
    if not text or _looks_technical(text) or "xp" in key or "experience" in key:
        return None
    kamas_match = KAMAS_REWARD_RE.match(text)
    if kamas_match:
        quantity = safe_int(kamas_match.group(1).replace(" ", ""))
        return DisplayReward(kind="kamas", name="Kamas", quantity=quantity) if quantity is not None else None
    if len(text) > 90 or SOURCE_REWARD_SENTENCE_RE.match(text) or "." in text:
        return None
    if SOURCE_QUANTITY_REWARD_RE.match(text):
        return DisplayReward(kind="source", name=text)
    if len(text.split()) <= 5:
        return DisplayReward(kind="source", name=text)
    return None


def display_rewards_from_achievement(achievement: Achievement) -> list[DisplayReward]:
    rows: list[DisplayReward] = []
    for reward in achievement.rewards:
        kind = str(getattr(reward, "kind", "") or "")
        if kind in {"xp", "xp_ratio", "kamas_ratio", "guild_points"}:
            continue
        quantity = getattr(reward, "quantity", None)
        if kind == "achievement_points" and int(quantity or 0) <= 0:
            continue
        rows.append(
            DisplayReward(
                kind=kind,
                name=str(getattr(reward, "name", "") or ""),
                quantity=quantity,
                image_path=str(getattr(reward, "image_path", "") or ""),
            )
        )
    return rows


def reward_label(reward: DisplayReward) -> str:
    quantity = int(reward.quantity or 0)
    if reward.kind == "xp":
        return f"{format_grouped_int(quantity)} XP"
    if reward.kind == "kamas":
        return f"{format_grouped_int(quantity)} Kamas"
    if reward.kind == "achievement_points":
        return f"{quantity} points de succès"
    prefixes = {
        "job": "Métier",
        "spell": "Sort",
        "title": "Titre",
        "emote": "Émote",
        "ornament": "Ornement",
        "alteration": "Altération",
    }
    prefix = prefixes.get(reward.kind)
    if prefix:
        return f"{prefix} : {reward.name}"
    if quantity > 1:
        return f"x{format_grouped_int(quantity)} {reward.name}"
    return reward.name


def _aggregate_global_rewards(
    guide_rows: Iterable[DisplayReward],
    quest_rows: Iterable[DisplayReward],
) -> tuple[DisplayReward, ...]:
    """Aggregate every guide reward while keeping the primary rewards first."""
    merged: dict[tuple[str, str], DisplayReward] = {}
    order: list[tuple[str, str]] = []

    def add(reward: DisplayReward, *, aggregate: bool) -> None:
        name = clean_text(reward.name)
        if not name:
            return
        key = (reward.kind, normalize_text(name))
        previous = merged.get(key)
        if previous is None:
            order.append(key)
            merged[key] = DisplayReward(
                kind=reward.kind,
                name=name,
                quantity=reward.quantity,
                image_path=reward.image_path,
            )
            return
        quantity = previous.quantity
        if aggregate and (previous.quantity is not None or reward.quantity is not None):
            quantity = int(previous.quantity or 0) + int(reward.quantity or 0)
        merged[key] = DisplayReward(
            kind=previous.kind,
            name=previous.name,
            quantity=quantity,
            image_path=_preferred_reward_image(previous.image_path, reward.image_path),
        )

    for reward in guide_rows:
        add(reward, aggregate=False)
    for reward in quest_rows:
        add(reward, aggregate=True)
    return tuple(merged[key] for key in order)


def _canonical_source_coordinate(value: object) -> str:
    """Only exact numeric coordinates enter the shared copyable start field."""

    return canonical_declared_coordinate(clean_text(value))


def _documented_quest_position(quest: QuestRecord) -> str:
    """First explicit imported walkthrough coordinate, never inferred prose.

    This is an objective/solution waypoint, NOT a verified quest launch map.
    The reader labels it accordingly when no independent launch source exists.
    """
    for step in getattr(quest, "source_solution_steps", ()) or ():
        for objective in getattr(step, "objectives", ()) or ():
            position = _canonical_source_coordinate(
                getattr(objective, "map_label", ""),
            )
            if position:
                return position
    for block in getattr(quest, "solution_blocks", ()) or ():
        position = _canonical_source_coordinate(
            getattr(block, "position", ""),
        )
        if position:
            return position
    return ""


def quest_start_info(
    quest: QuestRecord, *, include_map_images: bool = True,
) -> QuestStartInfo:
    source_info = getattr(quest, "source_info", {}) or {}
    source_meta = source_info.get("source_meta") if isinstance(source_info, dict) else {}
    source_meta = source_meta if isinstance(source_meta, dict) else {}

    npc = clean_text(source_meta.get("startNpc"))
    # Normalize local source coordinates once: Guide copy links and /travel
    # expect [x,y], regardless of whitespace or zero-padding in the source.
    # A placeholder must not suppress a valid second source or objective hint.
    position, start_status, _declarations = quest_launch_position_evidence(source_info)
    launch_instruction = quest_launch_instruction(source_info)
    declared_launch_position = (
        position if start_status in {"NATIVE_START_DECLARED", "LOCAL_START_DECLARED"} else ""
    )
    declared_launch_npc = npc
    source_zone = clean_text(source_meta.get("zone"))
    zone = next(
        (value for value in quest.zones if source_zone and normalize_text(source_zone) in normalize_text(value)),
        source_zone or (quest.zones[0] if quest.zones else ""),
    )
    # Route generation needs only NPC, position and zone; avoid thousands of
    # filesystem image existence checks that never affect the GPS itinerary.
    map_image_paths = (
        _explicit_start_map_paths(source_meta)
        if include_map_images and start_status != "DOCUMENTED_START"
        else ()
    )
    map_image_path = map_image_paths[0] if map_image_paths else ""
    for step in quest.steps:
        for objective in step.objectives:
            if not position and objective.map_label:
                # Imported objective hints are not proven launch positions.
                # Normalize them before rendering a copyable coordinate.
                position = _canonical_source_coordinate(objective.map_label)
            if not zone and objective.zone:
                zone = objective.zone
            if not npc and objective.type_id in NPC_OBJECTIVE_TYPES and objective.image_label:
                npc = objective.image_label
            if position and zone and npc:
                break
        if position and zone and npc:
            break
    if not position:
        # The visible Quest sheet previously omitted perfectly valid GPS
        # metadata from source walkthrough objectives/blocks. Display the
        # first such waypoint as unconfirmed objective, not false start.
        position = _documented_quest_position(quest)
    return QuestStartInfo(
        level=quest_level_text(quest),
        npc=npc,
        position=position,
        zone=zone,
        map_image_path=map_image_path,
        map_image_paths=map_image_paths,
        declared_launch_position=declared_launch_position,
        declared_launch_npc=declared_launch_npc,
        launch_status=start_status,
        launch_instruction=launch_instruction,
    )


def _explicit_start_map_path(source_meta: dict[str, object]) -> str:
    paths = _explicit_start_map_paths(source_meta)
    return paths[0] if paths else ""


def _explicit_start_map_paths(source_meta: dict[str, object]) -> tuple[str, ...]:
    raw_paths = source_meta.get("startMapImages")
    candidates = list(raw_paths) if isinstance(raw_paths, list) else []
    if source_meta.get("startMapImage"):
        candidates.insert(0, source_meta["startMapImage"])
    paths: list[str] = []
    for value in candidates:
        candidate = resolve_local_asset_path(value)
        if candidate and Path(candidate).is_file() and candidate not in paths:
            paths.append(candidate)
    return tuple(paths)


def quest_solution_steps(
    quest: QuestRecord, *, prefer_source: bool = True,
) -> tuple[SolutionStep, ...]:
    rows: list[SolutionStep] = []
    source_steps = getattr(quest, "source_solution_steps", None) if prefer_source else None
    source_to_local = _verified_source_objective_ids(quest) if source_steps else {}
    for step in source_steps or quest.steps:
        projected_rows = [
            (raw_objective, projected)
            for raw_objective in step.objectives
            if (projected := solution_objective(raw_objective)) is not None
        ]
        objectives = tuple(
            replace(projected, objective_id=source_to_local.get(id(raw_objective)))
            if source_steps else projected
            for raw_objective, projected in projected_rows
        )
        # Fallback steps follow the same documentary visibility contract as
        # explicit blocks; raw protocol criteria and mini-map placeholders
        # must not appear as false instructions in the reader or source audit.
        description = documentary_instruction_text(step.description)
        if not description and not objectives and not step.name:
            continue
        title = clean_text(step.name)
        if ARTIFICIAL_STEP_TITLE_RE.match(title):
            title = ""
        rows.append(
            SolutionStep(
                title=title,
                description=description,
                objectives=objectives,
            )
        )
    return tuple(rows)


def meaningful_quest_instruction(value: str) -> bool:
    """An objective number, heading or waypoint is not actionable text."""
    return bool(
        value and not _canonical_source_coordinate(value)
        and not re.fullmatch(r"(?:Objectif|Étape|Etape)\s+\d+", value, re.IGNORECASE)
    )


def quest_blocks_have_instructions(blocks: Iterable[DisplaySolutionBlock]) -> bool:
    """A heading, illustration or bare waypoint is not an instruction."""
    return any(
        meaningful_quest_instruction(block.content)
        and block.block_type not in {"image", "heading", "title", "subtitle", "section_heading"}
        for block in blocks
    )


def quest_fallback_instruction_steps(quest: QuestRecord) -> tuple[SolutionStep, ...]:
    """Reuse real local objectives; skip title-only and empty placeholders."""
    def meaningful(steps: Iterable[SolutionStep]) -> tuple[SolutionStep, ...]:
        return tuple(
            step for step in steps
            if meaningful_quest_instruction(step.description)
            or any(meaningful_quest_instruction(objective.text) for objective in step.objectives)
        )

    steps = meaningful(quest_solution_steps(quest))
    if not steps and getattr(quest, "source_solution_steps", None):
        # An imported array containing only placeholders must not hide the
        # actual native game objectives. Their IDs and text remain canonical.
        return meaningful(quest_solution_steps(quest, prefer_source=False))
    return steps


def quest_solution_blocks(quest: QuestRecord) -> tuple[DisplaySolutionBlock, ...]:
    blocks = getattr(quest, "solution_blocks", None) or []
    rows: list[DisplaySolutionBlock] = []
    for block in blocks:
        if not isinstance(block, QuestSolutionBlock):
            continue
        content = documentary_instruction_text(block.content)
        if block.block_type == "heading" and _is_artificial_step_title(content):
            continue
        image_path = str(block.image_path or "")
        # A documentary block may carry a real map coordinate separately
        # from its text. Normalize it before the UI ever offers /travel.
        position = _canonical_source_coordinate(block.position)
        textual = block.block_type not in {
            "image", "heading", "title", "subtitle", "section_heading",
        }
        if not content and not image_path and not (position and textual):
            continue
        rows.append(
            DisplaySolutionBlock(
                block_type=str(block.block_type or "text"),
                content=content,
                position=position,
                image_path=image_path,
                caption=clean_text(block.caption),
                data=dict(block.data or {}),
            )
        )
    return tuple(rows)


def _is_artificial_step_title(text: str) -> bool:
    key = normalize_text(str(text or "").rstrip(" :"))
    return bool(re.fullmatch(r"e?tape_\d+", key))


def trackable_quest_objective_ids(quest: QuestRecord) -> tuple[int, ...]:
    """Collect real documentary objectives once for view and progress services."""
    ids: list[int] = []
    seen: set[int] = set()
    for quest_step in quest.steps:
        for raw_objective in quest_step.objectives:
            objective = solution_objective(raw_objective)
            if objective is None or objective.objective_id is None:
                continue
            objective_id = int(objective.objective_id)
            if objective_id not in seen:
                seen.add(objective_id)
                ids.append(objective_id)
    return tuple(ids)


def _local_trackable_objective_ids(quest: QuestRecord) -> tuple[int, ...]:
    """Compatibility alias for established source-objective matching."""
    return trackable_quest_objective_ids(quest)


def _verified_source_objective_ids(quest: QuestRecord) -> dict[int, int]:
    """Map only uniquely matching source instructions to local progress IDs.

    Enriched walkthroughs are documentary, not a guaranteed one-to-one copy
    of gameplay objectives. Positional matching can silently check the wrong
    quest objective when the source inserts, omits or reorders an instruction.
    Unmatched and ambiguous rows deliberately remain read-only.
    """

    trackable = frozenset(_local_trackable_objective_ids(quest))
    if not trackable:
        return {}
    local = [
        objective
        for step in quest.steps
        for objective in step.objectives
        if objective.id in trackable
    ]
    source = [
        objective
        for step in quest.source_solution_steps
        for objective in step.objectives
        if solution_objective(objective) is not None
    ]

    def matches(left: QuestObjective, right: QuestObjective) -> bool:
        left_text = normalize_text(documentary_instruction_text(left.text))
        right_text = normalize_text(documentary_instruction_text(right.text))
        if not left_text or left_text != right_text:
            return False
        left_combat = left.is_combat or left.type_id in COMBAT_OBJECTIVE_TYPES
        right_combat = right.is_combat or right.type_id in COMBAT_OBJECTIVE_TYPES
        if bool(left_combat) != bool(right_combat):
            return False
        if (
            left.item_id is not None and right.item_id is not None
            and left.item_id != right.item_id
        ):
            # The same instruction can refer to different inventory items.
            # Conflicting verified item IDs must never share completion state.
            return False
        left_pos = _canonical_source_coordinate(left.map_label)
        right_pos = _canonical_source_coordinate(right.map_label)
        # A verified mismatch is evidence against identity, not permission
        # to attach a different local objective's completion state.
        return not (left_pos and right_pos and left_pos != right_pos)

    tentative: dict[int, int] = {}
    for source_objective in source:
        candidates = [
            objective.id for objective in local
            if matches(source_objective, objective)
        ]
        if len(candidates) == 1:
            tentative[id(source_objective)] = candidates[0]

    usage: dict[int, int] = {}
    for objective_id in tentative.values():
        usage[objective_id] = usage.get(objective_id, 0) + 1
    return {
        source_id: objective_id
        for source_id, objective_id in tentative.items()
        if usage[objective_id] == 1
    }


def solution_objective(objective: QuestObjective) -> SolutionObjective | None:
    text = documentary_instruction_text(objective.text)
    if not text:
        return None
    if _looks_like_stat_table_row(text):
        return None
    position = _canonical_source_coordinate(objective.map_label)
    if DISCOVER_MAP_RE.match(text):
        # Doduda can supply the documentary "Découvrir la carte : <id>"
        # without usable coordinates. Keep the real objective text, but
        # provide no copyable travel target until a valid map is known.
        # Dropping the row also loses a real progression objective.
        text = f"Rendez-vous en {position}." if position else text
    elif objective.type_id in COMBAT_OBJECTIVE_TYPES and objective.image_label:
        text = f"Lancez le combat contre {objective.image_label}"
        if position:
            text = f"{text} en {position}"
        text += "."
    if not text or _looks_technical(text):
        return None
    return SolutionObjective(
        text=text,
        objective_id=objective.id,
        image_path=objective.image_path,
        item_id=objective.item_id,
        quantity=max(0, int(objective.item_quantity or 0)),
        combat=objective.is_combat,
        position=position,
    )


def _clean_solution_instruction_text(text: str) -> str:
    """Avoid redundant cleanup while preserving legacy nested HTML decoding.

    solution_objective already calls clean_text. Decode again only if there are
    still entity/markup markers; the old double pass was meaningful for nested
    escapes such as &amp;lt;. Most plain instructions need no more regex work.
    """
    if "&" in text or "{{" in text or "<" in text:
        text = clean_text(text)
    if "mini-carte" not in text.casefold():
        return text
    text = MINIMAP_PLACEHOLDER_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def documentary_instruction_text(value: object) -> str:
    """Keep only documentary instructions that will actually appear in a Quest.

    The local coverage audit and the runtime must agree: boilerplate
    mini-map placeholders and raw technical criteria are not instructions.
    Normal source text (including a map objective without GPS) remains intact.
    """

    text = _clean_solution_instruction_text(clean_text(value))
    return "" if _looks_technical(text) else text


def _looks_like_stat_table_row(text: str) -> bool:
    tokens = str(text or "").replace("\u202f", " ").split()
    numeric_tokens = [token for token in tokens if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?%?", token)]
    percent_count = text.count("%")
    return percent_count >= 3 and len(numeric_tokens) >= 6 and not COORD_RE.search(text)


def related_quests(
    guide: Guide,
    quest: QuestRecord,
    graph: QuestGraphService,
    active_step: GuideStep | None = None,
) -> QuestRelatedInfo:
    guide_ids = set(guide.quest_ids)
    previous = []
    next_rows = []
    for quest_id in graph.previous_ids(quest.id):
        record = graph.catalog.by_id.get(int(quest_id))
        if record is not None:
            previous.append(EntityRef("quest", record.id, record.name))
    for quest_id in graph.next_ids(quest.id):
        record = graph.catalog.by_id.get(int(quest_id))
        if record is not None:
            next_rows.append(EntityRef("quest", record.id, record.name))
    series = []
    if active_step is not None:
        for part in guide.parts:
            for chapter in part.chapters:
                for guide_series in chapter.series:
                    if any(step.id == active_step.id for step in guide_series.steps):
                        for step in guide_series.steps:
                            if step.step_type == "quest" and step.entity_id is not None and int(step.entity_id) in guide_ids:
                                series.append(EntityRef("quest", int(step.entity_id), step.display_title))
                        break
    return QuestRelatedInfo(
        previous=tuple(_unique_refs(previous[:4])),
        next=tuple(_unique_refs(next_rows[:4])),
        series=tuple(_unique_refs(series[:12])),
        achievements=tuple(graph.achievement_names(quest.id)[:6]),
    )


def first_position_from_quest(
    quest: QuestRecord, *, start_info: QuestStartInfo | None = None,
) -> str:
    # Guide routing needs coordinates, not start-map artwork: avoid probing
    # image files for every candidate Quest when choosing its first waypoint.
    info = start_info if start_info is not None else quest_start_info(
        quest, include_map_images=False,
    )
    position = _canonical_source_coordinate(info.position)
    if position:
        return position
    for step in quest.steps:
        for objective in step.objectives:
            position = _canonical_source_coordinate(objective.map_label)
            if position:
                return position
    # Keep the Guide route and the Quest sheet on the exact same explicit
    # imported coordinate, even when callers supply an older start_info.
    return _documented_quest_position(quest)


def travel_command(position: str) -> str:
    return travel_command_from_position(position) or ""


def quest_requirement_target(line: str) -> str:
    """Extract an explicitly named Quest prerequisite, not a guessed relation."""
    key = normalize_text(clean_text(line))
    for prefix in ("quete_terminee_", "quete_active_"):
        if key.startswith(prefix):
            return key[len(prefix):]
    return ""


def resolve_quest_requirement(line: str, source, *, owner=None) -> int | None:
    """Use the catalogue-owned index; preserve lightweight custom providers."""
    target = quest_requirement_target(line)
    if not target or source is None:
        return None
    resolver = getattr(source, "requirement_name_id", None)
    if callable(resolver):
        return resolver(target)
    # Small injected providers/catalogues used by compatibility hosts may not
    # expose the catalogue API. Keep their local index scoped to the host.
    from app.quest_catalog import build_quest_requirement_name_index
    getter = getattr(source, "list_quests", None)
    rows = getattr(source, "quests", None)
    if rows is None:
        if not callable(getter):
            return None
        rows = getter()
    stamp = (id(source), id(rows), len(rows))
    cached = getattr(owner, "_compat_requirement_index", None) if owner is not None else None
    if cached is None or cached[0] != stamp:
        cached = (stamp, build_quest_requirement_name_index(rows))
        if owner is not None:
            owner._compat_requirement_index = cached
    return cached[1].get(target)


def clean_requirement_line(value: str) -> str:
    text = clean_text(value)
    normalized = re.sub(r"^Quete terminee\s*:\s*", "", text, flags=re.IGNORECASE)
    normalized = re.sub(r"^Qu[eê]te termin[ée]e\s*:\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^Terminer\s+[\"“”']?(.+?)[\"“”']?$", r"\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^Quete active\s*:\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^Qu[eê]te active\s*:\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^Succes requis\s*:\s*", "Succès requis : ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^Niveau\s+(\d+)\+$", r"Niveau \1 et plus", normalized)
    return "" if _looks_technical(normalized) else normalized


def clean_text(value: object) -> str:
    """Normalize repeated Guide/Quest labels without retaining entire chapters.

    Guide cards reuse the same objective and NPC labels across many route
    positions. Cache only short, immutable text values; do not pin long
    walkthrough descriptions or objects in the process for the entire session.
    """
    raw = str(value or "")
    return _cached_clean_text(raw) if len(raw) <= 512 else _normalize_clean_text(raw)


@lru_cache(maxsize=2048)
def _cached_clean_text(raw: str) -> str:
    return _normalize_clean_text(raw)


def _normalize_clean_text(raw: str) -> str:
    text = html.unescape(raw)

    def replace_markup(match: re.Match[str]) -> str:
        content = match.group(0)[2:-2]
        if "::" in content:
            return content.rsplit("::", 1)[1]
        return ""

    text = MARKUP_RE.sub(replace_markup, text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _positive_level(value: int | None) -> int | None:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _guide_step_keys(guide: Guide) -> set[tuple[str, int]]:
    return {
        (step.step_type, int(step.entity_id))
        for step in guide.steps
        if step.entity_id is not None
    }


def _raw_required_items(guide: Guide) -> tuple[GuideRequiredItem, ...]:
    return tuple(
        item
        for part in guide.parts
        for item in (
            *part.required_items,
            *tuple(item for chapter in part.chapters for item in chapter.required_items),
            *tuple(item for chapter in part.chapters for series in chapter.series for item in series.required_items),
        )
    )


def _merge_items(items: Iterable[GuideRequiredItem]) -> tuple[DisplayItem, ...]:
    return _merge_display_items(
        DisplayItem(
            item_id=item.item_id,
            name=item.name,
            quantity=max(1, int(item.quantity)) if int(item.quantity or 0) > 0 else None,
            image_path=item.image_path or _local_item_image_path(item.item_id),
            consumed=item.consumed,
            preparable=True,
        )
        for item in items
        if item.name or item.item_id is not None
    )


def _merge_display_items(items: Iterable[DisplayItem]) -> tuple[DisplayItem, ...]:
    merged: dict[tuple[str, str, bool, bool], DisplayItem] = {}
    for item in items:
        name = clean_text(item.name)
        if not name:
            continue
        key = (str(item.item_id or normalize_text(name)), name.casefold(), bool(item.consumed), bool(item.preparable))
        if key in merged:
            previous = merged[key]
            quantity = None
            if previous.quantity is not None and item.quantity is not None:
                quantity = max(1, previous.quantity) + max(1, item.quantity)
            merged[key] = DisplayItem(
                item_id=previous.item_id or item.item_id,
                name=previous.name,
                quantity=quantity,
                image_path=previous.image_path or item.image_path,
                consumed=previous.consumed,
                preparable=previous.preparable,
            )
        else:
            merged[key] = DisplayItem(
                item_id=item.item_id,
                name=name,
                quantity=max(1, item.quantity) if item.quantity is not None else None,
                image_path=item.image_path or _local_item_image_path(item.item_id),
                consumed=item.consumed,
                preparable=item.preparable,
            )
    return tuple(sorted(merged.values(), key=lambda item: normalize_text(item.name)))


# Historical public/internal callers all share one owned index in app.core.
local_item_image_path = item_icon_path
_local_item_image_path = item_icon_path
_local_item_image_index = item_icon_index


def _dedupe_rewards(rewards: Iterable[DisplayReward]) -> tuple[DisplayReward, ...]:
    merged: dict[tuple[str, str], DisplayReward] = {}
    for reward in rewards:
        name = clean_text(reward.name)
        if not name:
            continue
        key = (reward.kind, normalize_text(name))
        if key in merged:
            previous = merged[key]
            quantity = previous.quantity
            if reward.kind in {"kamas", "achievement_points"}:
                quantity = int(previous.quantity or 0) + int(reward.quantity or 0)
            elif previous.quantity is not None or reward.quantity is not None:
                quantity = max(int(previous.quantity or 0), int(reward.quantity or 0)) or None
            merged[key] = DisplayReward(
                kind=previous.kind,
                name=previous.name,
                quantity=quantity,
                image_path=_preferred_reward_image(previous.image_path, reward.image_path),
            )
        else:
            merged.setdefault(
                key,
                DisplayReward(
                    kind=reward.kind,
                    name=name,
                    quantity=reward.quantity,
                    image_path=reward.image_path,
                ),
            )
    return tuple(sorted(merged.values(), key=lambda reward: normalize_text(reward.name)))


def _preferred_reward_image(first: str, second: str) -> str:
    first = str(first or "")
    second = str(second or "")
    if not first:
        return second
    if not second:
        return first
    if "\\archive\\unmatched\\" in first.replace("/", "\\") and "\\archive\\unmatched\\" not in second.replace("/", "\\"):
        return second
    return first


def _add_unique_line(lines: list[str], value: str) -> None:
    text = clean_requirement_line(value)
    key = normalize_text(text)
    if text and key and key not in {normalize_text(line) for line in lines}:
        lines.append(text)


def _unique_refs(refs: Iterable[EntityRef]) -> list[EntityRef]:
    result: dict[tuple[str, int], EntityRef] = {}
    for ref in refs:
        result.setdefault((ref.entity_type, ref.entity_id), ref)
    return list(result.values())


def _is_alteration_objective(objective: QuestObjective) -> bool:
    text = normalize_text(f"{objective.image_label} {objective.text}")
    return "alteration" in text or "alterations" in text


def _looks_technical(text: str) -> bool:
    return bool(TECHNICAL_CRITERION_RE.search(str(text or "")))
