from __future__ import annotations

import html
import re
from functools import lru_cache
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
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
from app.quest_catalog import (
    QuestObjective,
    QuestRecord,
    QuestReward,
    QuestSolutionBlock,
    build_image_index,
    doduda_rows,
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
COORD_RE = re.compile(r"\[(-?\d+)\s*,\s*(-?\d+)\]")
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
    total = len([step for step in guide.required_steps if step.counts_for_completion])
    if not total:
        return ""
    required = list(guide.required_steps)
    word = "quête" if total == 1 and all(step.step_type == "quest" for step in required) else "quêtes"
    if not all(step.step_type == "quest" for step in required):
        word = "étape" if total == 1 else "étapes"
    return f"{total} {word}"


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
        return f"{format_number(quantity)} XP"
    if reward.kind == "kamas":
        return f"{format_number(quantity)} Kamas"
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
        return f"x{format_number(quantity)} {reward.name}"
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


def quest_start_info(quest: QuestRecord) -> QuestStartInfo:
    source_info = getattr(quest, "source_info", {}) or {}
    launch = source_info.get("launch_position") if isinstance(source_info, dict) else {}
    launch = launch if isinstance(launch, dict) else {}
    source_meta = source_info.get("source_meta") if isinstance(source_info, dict) else {}
    source_meta = source_meta if isinstance(source_meta, dict) else {}

    npc = clean_text(source_meta.get("startNpc"))
    position = clean_text(launch.get("position")) or clean_text(source_meta.get("startCoords"))
    source_zone = clean_text(source_meta.get("zone"))
    zone = next(
        (value for value in quest.zones if source_zone and normalize_text(source_zone) in normalize_text(value)),
        source_zone or (quest.zones[0] if quest.zones else ""),
    )
    map_image_paths = _explicit_start_map_paths(source_meta)
    map_image_path = map_image_paths[0] if map_image_paths else ""
    for step in quest.steps:
        for objective in step.objectives:
            if not position and objective.map_label:
                position = objective.map_label
            if not zone and objective.zone:
                zone = objective.zone
            if not npc and objective.type_id in NPC_OBJECTIVE_TYPES and objective.image_label:
                npc = objective.image_label
            if position and zone and npc:
                break
        if position and zone and npc:
            break
    return QuestStartInfo(
        level=quest_level_text(quest),
        npc=npc,
        position=position,
        zone=zone,
        map_image_path=map_image_path,
        map_image_paths=map_image_paths,
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


def quest_solution_steps(quest: QuestRecord) -> tuple[SolutionStep, ...]:
    rows: list[SolutionStep] = []
    source_steps = getattr(quest, "source_solution_steps", None)
    local_objective_ids = list(_local_trackable_objective_ids(quest)) if source_steps else []
    local_objective_index = 0
    for step in source_steps or quest.steps:
        objectives = tuple(
            objective
            for objective in (solution_objective(objective) for objective in step.objectives)
            if objective is not None
        )
        if source_steps and objectives:
            aligned = []
            for objective in objectives:
                objective_id = None
                if local_objective_index < len(local_objective_ids):
                    objective_id = local_objective_ids[local_objective_index]
                    local_objective_index += 1
                aligned.append(replace(objective, objective_id=objective_id))
            objectives = tuple(aligned)
        description = clean_text(step.description)
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


def quest_solution_blocks(quest: QuestRecord) -> tuple[DisplaySolutionBlock, ...]:
    blocks = getattr(quest, "solution_blocks", None) or []
    rows: list[DisplaySolutionBlock] = []
    for block in blocks:
        if not isinstance(block, QuestSolutionBlock):
            continue
        content = clean_text(block.content)
        if block.block_type == "heading" and _is_artificial_step_title(content):
            continue
        image_path = str(block.image_path or "")
        if content and _looks_technical(content):
            content = ""
        if not content and not image_path:
            continue
        rows.append(
            DisplaySolutionBlock(
                block_type=str(block.block_type or "text"),
                content=content,
                position=str(block.position or ""),
                image_path=image_path,
                caption=clean_text(block.caption),
                data=dict(block.data or {}),
            )
        )
    return tuple(rows)


def _is_artificial_step_title(text: str) -> bool:
    key = normalize_text(str(text or "").rstrip(" :"))
    return bool(re.fullmatch(r"e?tape_\d+", key))


def _local_trackable_objective_ids(quest: QuestRecord) -> tuple[int, ...]:
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


def solution_objective(objective: QuestObjective) -> SolutionObjective | None:
    text = clean_text(objective.text)
    text = _clean_solution_instruction_text(text)
    if not text:
        return None
    if _looks_like_stat_table_row(text):
        return None
    if DISCOVER_MAP_RE.match(text):
        text = f"Rendez-vous en {objective.map_label}." if objective.map_label else ""
    elif objective.type_id in COMBAT_OBJECTIVE_TYPES and objective.image_label:
        text = f"Lancez le combat contre {objective.image_label}"
        if objective.map_label:
            text = f"{text} en {objective.map_label}"
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
        position=objective.map_label,
    )


def _clean_solution_instruction_text(text: str) -> str:
    text = MINIMAP_PLACEHOLDER_RE.sub("", clean_text(text))
    return re.sub(r"\s+", " ", text).strip()


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


def first_position_from_quest(quest: QuestRecord) -> str:
    info = quest_start_info(quest)
    if info.position:
        return info.position
    for step in quest.steps:
        for objective in step.objectives:
            if objective.map_label:
                return objective.map_label
    return ""


def travel_command(position: str) -> str:
    match = COORD_RE.search(str(position or ""))
    if not match:
        return ""
    return f"/travel {int(match.group(1))},{int(match.group(2))}"


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
    text = html.unescape(str(value or ""))

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


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


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


def _local_item_image_path(item_id: int | None) -> str:
    if item_id is None:
        return ""
    return _local_item_image_index().get(int(item_id), "")


@lru_cache(maxsize=1)
def _local_item_image_index() -> dict[int, str]:
    image_index = build_image_index(DATA_DIR / "images")
    rows: dict[int, str] = {}
    for item_id, row in doduda_rows(RAW_QUEST_DATA_DIR / "items.json").items():
        icon_id = safe_int(row.get("iconId"))
        if icon_id is None:
            continue
        path = image_index.get(str(icon_id), "")
        if path:
            rows[int(item_id)] = path
    return rows


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


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
