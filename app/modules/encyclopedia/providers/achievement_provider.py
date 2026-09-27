from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from threading import current_thread
from time import perf_counter
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.models.achievement import (
    Achievement,
    AchievementCategory,
    AchievementObjective,
)
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.models.reward import Reward
from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.achievement_catalog_policy import (
    QUEST_GENERAL_PINNED_ACHIEVEMENT_IDS,
    QUEST_GENERAL_SUBCATEGORY_ID,
    QUEST_WORLD_ACHIEVEMENT_IDS,
    QUEST_WORLD_SUBCATEGORY_ID,
    RETAINED_TOP_CATEGORY_IDS,
)
from app.quest_catalog import array_value, localized_name, normalize_text, text_for
from app.quest_source_index import QuestSources

QUEST_CRITERION_RE = re.compile(r"\bQf\s*[=><!]+\s*(\d+)", re.IGNORECASE)
MONSTER_CRITERION_RE = re.compile(r"\bEM\s*[=><!]+\s*(\d+)", re.IGNORECASE)
ACHIEVEMENT_CRITERION_RE = re.compile(r"\bOA\s*[=><!]+\s*(\d+)", re.IGNORECASE)
CRITERION_CODE_RE = re.compile(r"\b([A-Za-z]{1,3})\s*[=><!]+")
_DETAIL_SOURCE_FILES = (
    "achievement_rewards.json",
    "items.json",
    "spells.json",
    "titles.json",
    "emoticons.json",
    "ornaments.json",
    "alterations.json",
)


def safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class AchievementProvider:
    def __init__(
        self,
        data_dir: Path = RAW_QUEST_DATA_DIR,
        quest_provider: QuestProvider | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.quest_provider = quest_provider or QuestProvider(data_dir=data_dir)
        self._loaded = False
        self._achievements: list[Achievement] = []
        self._by_id: dict[int, Achievement] = {}
        self._categories: dict[int, AchievementCategory] = {}
        self._by_category: dict[int, list[Achievement]] = defaultdict(list)
        self._linked_quests: dict[int, tuple[EntityRef, ...]] = {}
        self._linked_monsters: dict[int, tuple[EntityRef, ...]] = {}
        self._linked_dungeons: dict[int, tuple[EntityRef, ...]] = {}
        self._linked_achievements: dict[int, tuple[EntityRef, ...]] = {}
        self._by_quest: dict[int, list[Achievement]] = defaultdict(list)
        self._image_indexes: dict[tuple[str, ...], dict[int, str]] = {}
        self._sources = QuestSources(ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1")
        self._entries: Mapping[str, Any] | None = None
        self._detail_sources_ready = False
        self._detail_cache_id: int | None = None
        self._detail_cache: Achievement | None = None
        self._last_detail_thread_name = ""
        self._last_detail_ms = 0.0

    @property
    def detail_sources_ready(self) -> bool:
        return self._detail_sources_ready

    @property
    def last_detail_thread_name(self) -> str:
        return self._last_detail_thread_name

    @property
    def last_detail_ms(self) -> float:
        return self._last_detail_ms

    def load_all(self) -> list[Achievement]:
        self._ensure_loaded()
        # The Success runtime calls load_all() from DofusAtlasAchievementStage.
        # Build only byte-offset indexes for documentary reward sources here so
        # get_detail_by_id() never has to index monolithic JSON on the Qt thread.
        self.prepare_detail_sources()
        return list(self._achievements)

    def load_retained(self) -> list[Achievement]:
        self._ensure_loaded()
        return [
            achievement
            for achievement in self._achievements
            if achievement.category_id in RETAINED_TOP_CATEGORY_IDS
        ]

    def get_by_id(self, achievement_id: int) -> Achievement | None:
        self._ensure_loaded()
        return self._by_id.get(int(achievement_id))

    def get_detail_by_id(self, achievement_id: int) -> Achievement | None:
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        achievement = self._by_id.get(achievement_id)
        if achievement is None:
            return None
        if not self._detail_sources_ready:
            raise RuntimeError(
                "Sources de détail Succès non préparées ; load_all() doit être exécuté "
                "hors du thread UI avant l'ouverture d'un détail."
            )
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            return self._detail_cache

        started = perf_counter()
        rewards = [
            Reward(
                kind="achievement_points",
                name="Points de succès",
                quantity=max(0, achievement.points),
                source_id=achievement.id,
            )
        ]
        reward_rows = self._sources.rows(self.data_dir / "achievement_rewards.json")
        try:
            for reward_id in achievement.reward_ids:
                row = reward_rows.get(int(reward_id))
                if isinstance(row, dict):
                    rewards.extend(self._rewards_from_row(int(reward_id), row))
        finally:
            self._sources.close()

        detail = replace(achievement, rewards=tuple(rewards))
        self._detail_cache_id = achievement_id
        self._detail_cache = detail
        self._last_detail_thread_name = current_thread().name
        self._last_detail_ms = round((perf_counter() - started) * 1000.0, 3)
        return detail

    def prepare_detail_sources(self) -> None:
        if self._detail_sources_ready:
            return
        for filename in _DETAIL_SOURCE_FILES:
            path = self.data_dir / filename
            if path.is_file():
                len(self._sources.rows(path))
        self._detail_sources_ready = True

    def search(self, query: str, limit: int | None = None) -> list[Achievement]:
        self._ensure_loaded()
        needle = normalize_text(query)
        if not needle:
            results = list(self._achievements)
        else:
            tokens = [token for token in needle.split("_") if token]
            results = [
                achievement
                for achievement in self._achievements
                if all(token in achievement.search_text for token in tokens)
            ]
        return results[:limit] if limit is not None else results

    def get_categories(self) -> list[AchievementCategory]:
        self._ensure_loaded()
        return sorted(
            self._categories.values(),
            key=lambda category: (
                category.parent_id != 0,
                category.parent_id,
                category.order,
                normalize_text(category.name),
                category.id,
            ),
        )

    def get_retained_categories(self) -> list[AchievementCategory]:
        self._ensure_loaded()
        categories = {
            category.id: category
            for category in self.get_categories()
            if category.id in RETAINED_TOP_CATEGORY_IDS
        }
        return [
            categories[category_id]
            for category_id in RETAINED_TOP_CATEGORY_IDS
            if category_id in categories
        ]

    def is_retained(self, achievement_id: int) -> bool:
        achievement = self.get_by_id(int(achievement_id))
        return achievement is not None and achievement.category_id in RETAINED_TOP_CATEGORY_IDS

    def get_by_category(self, category_id: int) -> list[Achievement]:
        self._ensure_loaded()
        return list(self._by_category.get(int(category_id), []))

    def get_linked_quests(self, achievement_id: int) -> list[EntityRef]:
        self._ensure_loaded()
        return list(self._linked_quests.get(int(achievement_id), ()))

    def get_linked_monsters(self, achievement_id: int) -> list[EntityRef]:
        self._ensure_loaded()
        return list(self._linked_monsters.get(int(achievement_id), ()))

    def get_linked_dungeons(self, achievement_id: int) -> list[EntityRef]:
        self._ensure_loaded()
        return list(self._linked_dungeons.get(int(achievement_id), ()))

    def get_linked_achievements(self, achievement_id: int) -> list[EntityRef]:
        self._ensure_loaded()
        return list(self._linked_achievements.get(int(achievement_id), ()))

    def get_by_quest(self, quest_id: int) -> list[Achievement]:
        self._ensure_loaded()
        return list(self._by_quest.get(int(quest_id), []))

    def get_subcategories(self, parent_id: int) -> list[AchievementCategory]:
        self._ensure_loaded()
        return [
            category
            for category in self.get_categories()
            if category.parent_id == int(parent_id)
        ]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self) -> None:
        entries = self._sources.mapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            required=True,
        )
        self._entries = entries

        achievement_rows = self._sources.rows(self.data_dir / "achievements.json")
        self._categories = self._load_categories(
            self._sources.rows(self.data_dir / "achievement_categories.json"),
            entries,
        )
        achievement_names = self._named_rows(achievement_rows, entries, "Succes")
        quest_names = self._named_rows(
            self._sources.rows(self.data_dir / "quests.json"),
            entries,
            "Quete",
        )
        monster_names = self._named_rows(
            self._sources.rows(self.data_dir / "monsters.json"),
            entries,
            "Monstre",
        )
        dungeon_rows = self._sources.rows(self.data_dir / "dungeons.json")
        dungeon_names = self._named_rows(dungeon_rows, entries, "Donjon")

        objectives_by_achievement = self._objectives_by_achievement(
            self._sources.rows(self.data_dir / "achievement_objectives.json"),
            achievement_rows,
            entries,
            quest_names,
            monster_names,
            achievement_names,
        )
        dungeon_links = self._dungeon_links(dungeon_rows, dungeon_names)

        achievements: list[Achievement] = []
        by_category: dict[int, list[Achievement]] = defaultdict(list)
        linked_quests: dict[int, tuple[EntityRef, ...]] = {}
        linked_monsters: dict[int, tuple[EntityRef, ...]] = {}
        linked_dungeons: dict[int, tuple[EntityRef, ...]] = {}
        linked_achievements: dict[int, tuple[EntityRef, ...]] = {}

        for achievement_id, row in achievement_rows.items():
            category_id = safe_int(row.get("categoryId"), 0) or 0
            category_name, subcategory_id, subcategory_name = self._category_labels(category_id)
            objectives = tuple(objectives_by_achievement.get(achievement_id, ()))
            # Keep the cheap derived points reward for backwards compatibility.
            # Documentary rewards from achievement_rewards/items/... stay cold.
            rewards = (
                Reward(
                    kind="achievement_points",
                    name="Points de succès",
                    quantity=max(0, safe_int(row.get("points"), 0) or 0),
                    source_id=achievement_id,
                ),
            )
            objective_refs = [ref for objective in objectives for ref in objective.entity_refs]
            primary_refs = [
                objective.entity_ref
                for objective in objectives
                if objective.entity_ref is not None
            ]
            quest_refs = tuple(
                self._unique_refs(ref for ref in primary_refs if ref.entity_type == "quest")
            )
            monster_refs = tuple(
                self._unique_refs(ref for ref in primary_refs if ref.entity_type == "monster")
            )
            achievement_refs = tuple(
                self._unique_refs(
                    ref for ref in objective_refs if ref.entity_type == "achievement"
                )
            )
            dungeon_refs = tuple(dungeon_links.get(achievement_id, ()))
            name = text_for(entries, row.get("nameId"), f"Succes {achievement_id}")
            description = text_for(entries, row.get("descriptionId"), "")
            search_values = [
                name,
                description,
                category_name,
                subcategory_name,
                " ".join(ref.label for ref in quest_refs),
            ]
            achievement = Achievement(
                id=achievement_id,
                original_id=achievement_id,
                name=name,
                description=description,
                category_id=self._top_category_id(category_id),
                category_name=category_name,
                subcategory_id=subcategory_id,
                subcategory_name=subcategory_name,
                level=safe_int(row.get("level")),
                points=safe_int(row.get("points"), 0) or 0,
                icon_id=safe_int(row.get("iconId")),
                image_path=self._image_for_icon(
                    safe_int(row.get("iconId")),
                    ("achievements", "icons", "misc"),
                ),
                order=safe_int(row.get("order"), 0) or 0,
                objective_ids=tuple(
                    int(value)
                    for value in array_value(row.get("objectiveIds"))
                    if safe_int(value) is not None
                ),
                reward_ids=tuple(
                    int(value)
                    for value in array_value(row.get("rewardIds"))
                    if safe_int(value) is not None
                ),
                objectives=objectives,
                rewards=rewards,
                linked_quests=quest_refs,
                linked_monsters=monster_refs,
                linked_dungeons=dungeon_refs,
                linked_achievements=achievement_refs,
                search_text=normalize_text(" ".join(search_values)),
                raw=dict(row),
            )
            achievements.append(achievement)
            by_category[achievement.category_id].append(achievement)
            if achievement.subcategory_id is not None:
                by_category[achievement.subcategory_id].append(achievement)
            linked_quests[achievement.id] = quest_refs
            linked_monsters[achievement.id] = monster_refs
            linked_dungeons[achievement.id] = dungeon_refs
            linked_achievements[achievement.id] = achievement_refs

        direct_by_id = {achievement.id: achievement for achievement in achievements}
        resolved: dict[
            int,
            tuple[
                tuple[EntityRef, ...],
                tuple[EntityRef, ...],
                tuple[EntityRef, ...],
            ],
        ] = {}

        def resolve_links(
            achievement_id: int,
            visiting: frozenset[int] = frozenset(),
        ) -> tuple[tuple[EntityRef, ...], tuple[EntityRef, ...], tuple[EntityRef, ...]]:
            if achievement_id in resolved:
                return resolved[achievement_id]
            achievement = direct_by_id.get(achievement_id)
            if achievement is None or achievement_id in visiting:
                return (), (), ()
            all_objective_refs = [
                ref for objective in achievement.objectives for ref in objective.entity_refs
            ]
            quests = [
                ref for ref in all_objective_refs if ref.entity_type == "quest"
            ]
            monsters = [
                ref for ref in all_objective_refs if ref.entity_type == "monster"
            ]
            dungeons = list(achievement.linked_dungeons)
            next_visiting = visiting | {achievement_id}
            for ref in achievement.linked_achievements:
                child_quests, child_monsters, child_dungeons = resolve_links(
                    int(ref.entity_id),
                    next_visiting,
                )
                quests.extend(child_quests)
                monsters.extend(child_monsters)
                dungeons.extend(child_dungeons)
            value = (
                tuple(self._unique_refs(quests)),
                tuple(self._unique_refs(monsters)),
                tuple(self._unique_refs(dungeons)),
            )
            resolved[achievement_id] = value
            return value

        expanded_achievements: list[Achievement] = []
        for achievement in achievements:
            quest_refs, monster_refs, dungeon_refs = resolve_links(achievement.id)
            search_text = normalize_text(
                " ".join(
                    (
                        achievement.name,
                        achievement.description,
                        achievement.category_name,
                        achievement.subcategory_name,
                        " ".join(ref.label for ref in quest_refs),
                        " ".join(ref.label for ref in monster_refs),
                        " ".join(ref.label for ref in dungeon_refs),
                    )
                )
            )
            expanded_achievements.append(
                replace(
                    achievement,
                    resolved_linked_quests=quest_refs,
                    resolved_linked_monsters=monster_refs,
                    resolved_linked_dungeons=dungeon_refs,
                    search_text=search_text,
                )
            )

        achievements = expanded_achievements
        category_positions = {
            (category.id, achievement_id): position
            for category in self._categories.values()
            for position, achievement_id in enumerate(category.achievement_ids)
        }

        general_pinned_positions = {
            achievement_id: position
            for position, achievement_id in enumerate(
                QUEST_GENERAL_PINNED_ACHIEVEMENT_IDS
            )
        }
        world_positions = {
            achievement_id: position
            for position, achievement_id in enumerate(QUEST_WORLD_ACHIEVEMENT_IDS)
        }

        def source_position(achievement: Achievement, source_category_id: int) -> int:
            declared = category_positions.get(
                (source_category_id, achievement.id),
                999999,
            )
            if source_category_id == QUEST_GENERAL_SUBCATEGORY_ID:
                pinned = general_pinned_positions.get(achievement.id)
                if pinned is not None:
                    return pinned
                return len(general_pinned_positions) + declared
            if source_category_id == QUEST_WORLD_SUBCATEGORY_ID:
                world = world_positions.get(achievement.id)
                if world is not None:
                    return world
                return len(world_positions) + declared
            return declared

        def achievement_sort_key(achievement: Achievement) -> tuple[Any, ...]:
            source_category_id = (
                safe_int(achievement.raw.get("categoryId"), achievement.category_id)
                or achievement.category_id
            )
            return (
                self._category_order(achievement.category_id),
                self._category_order(
                    achievement.subcategory_id or achievement.category_id
                ),
                source_position(achievement, source_category_id),
                achievement.order,
                achievement.id,
            )

        self._achievements = sorted(achievements, key=achievement_sort_key)
        self._by_id = {
            achievement.id: achievement for achievement in self._achievements
        }
        by_category = defaultdict(list)
        for achievement in self._achievements:
            by_category[achievement.category_id].append(achievement)
            if achievement.subcategory_id is not None:
                by_category[achievement.subcategory_id].append(achievement)
        self._by_category = defaultdict(
            list,
            {
                key: sorted(value, key=achievement_sort_key)
                for key, value in by_category.items()
            },
        )
        self._linked_quests = linked_quests
        self._linked_monsters = linked_monsters
        self._linked_dungeons = linked_dungeons
        self._linked_achievements = linked_achievements
        by_quest: dict[int, list[Achievement]] = defaultdict(list)
        for achievement in self._achievements:
            for ref in achievement.linked_quests:
                by_quest[int(ref.entity_id)].append(achievement)
        self._by_quest = defaultdict(
            list,
            {
                quest_id: sorted(
                    values,
                    key=lambda item: (item.order, normalize_text(item.name), item.id),
                )
                for quest_id, values in by_quest.items()
            },
        )
        self._sources.close()

    def _load_categories(
        self,
        rows: Mapping[int, dict[str, Any]],
        entries: Mapping[str, Any],
    ) -> dict[int, AchievementCategory]:
        categories = {}
        for category_id, row in rows.items():
            categories[category_id] = AchievementCategory(
                id=category_id,
                name=text_for(
                    entries,
                    row.get("nameId"),
                    f"Categorie {category_id}",
                ),
                parent_id=safe_int(row.get("parentId"), 0) or 0,
                order=safe_int(row.get("order"), 0) or 0,
                achievement_ids=tuple(
                    int(value)
                    for value in array_value(row.get("achievementIds"))
                    if safe_int(value) is not None
                ),
            )
        return categories

    def _objectives_by_achievement(
        self,
        rows: Mapping[int, dict[str, Any]],
        achievement_rows: Mapping[int, dict[str, Any]],
        entries: Mapping[str, Any],
        quest_names: dict[int, str],
        monster_names: dict[int, str],
        achievement_names: dict[int, str],
    ) -> dict[int, tuple[AchievementObjective, ...]]:
        result: dict[int, list[AchievementObjective]] = defaultdict(list)
        for objective_id, row in rows.items():
            achievement_id = safe_int(row.get("achievementId"))
            if achievement_id is None:
                continue
            criterion = str(row.get("criterion") or "")
            entity_refs = self._objective_entity_refs(
                criterion,
                quest_names,
                monster_names,
                achievement_names,
            )
            result[achievement_id].append(
                AchievementObjective(
                    id=objective_id,
                    achievement_id=achievement_id,
                    text=text_for(
                        entries,
                        row.get("nameId"),
                        f"Objectif {objective_id}",
                    ),
                    criterion=criterion,
                    order=safe_int(row.get("order"), 0) or 0,
                    objective_type=self._objective_type(criterion),
                    required_quantity=1,
                    entity_ref=entity_refs[0] if entity_refs else None,
                    entity_refs=entity_refs,
                )
            )
        ordered: dict[int, tuple[AchievementObjective, ...]] = {}
        for achievement_id, objectives in result.items():
            declared = [
                int(value)
                for value in array_value(
                    achievement_rows.get(achievement_id, {}).get("objectiveIds")
                )
                if safe_int(value) is not None
            ]
            positions = {
                objective_id: position
                for position, objective_id in enumerate(declared)
            }
            ordered[achievement_id] = tuple(
                sorted(
                    objectives,
                    key=lambda objective: (
                        positions.get(objective.id, 999999),
                        objective.order,
                        objective.id,
                    ),
                )
            )
        return ordered

    def _rewards_from_row(
        self,
        reward_id: int,
        row: dict[str, Any],
    ) -> list[Reward]:
        rewards: list[Reward] = []
        experience_ratio = safe_int(row.get("experienceRatio"), 0) or 0
        kamas_ratio = safe_int(row.get("kamasRatio"), 0) or 0
        guild_points = safe_int(row.get("guildPoints"), 0) or 0
        if experience_ratio > 0:
            rewards.append(
                Reward(
                    "xp_ratio",
                    "Expérience",
                    experience_ratio,
                    source_id=reward_id,
                )
            )
        if kamas_ratio > 0:
            rewards.append(
                Reward(
                    "kamas_ratio",
                    "Kamas",
                    kamas_ratio,
                    source_id=reward_id,
                )
            )
        if guild_points > 0:
            rewards.append(
                Reward(
                    "guild_points",
                    "Points de guilde",
                    guild_points,
                    source_id=reward_id,
                )
            )

        item_ids = [safe_int(value) for value in array_value(row.get("itemsReward"))]
        quantities = [
            safe_int(value, 1) or 1
            for value in array_value(row.get("itemsQuantityReward"))
        ]
        item_rows = self._sources.rows(self.data_dir / "items.json")
        entries = self._entries or {}
        for index, item_id in enumerate(
            item_id for item_id in item_ids if item_id is not None
        ):
            item_row = item_rows.get(item_id)
            if not isinstance(item_row, dict):
                continue
            item_name = localized_name(item_row, entries, f"Objet {item_id}")
            if not item_name or normalize_text(item_name) == normalize_text(
                f"Objet {item_id}"
            ):
                continue
            quantity = quantities[index] if index < len(quantities) else 1
            rewards.append(
                Reward(
                    kind="item",
                    name=item_name,
                    quantity=quantity,
                    entity_id=item_id,
                    image_path=self._image_for_icon(
                        safe_int(item_row.get("iconId")),
                        ("items", "resources"),
                    ),
                    source_id=reward_id,
                )
            )

        rewards.extend(
            self._entity_rewards(
                "spell",
                row.get("spellsReward"),
                "spells.json",
                "Sort",
                reward_id,
            )
        )
        rewards.extend(
            self._entity_rewards(
                "title",
                row.get("titlesReward"),
                "titles.json",
                "Titre",
                reward_id,
            )
        )
        rewards.extend(
            self._entity_rewards(
                "emote",
                row.get("emotesReward"),
                "emoticons.json",
                "Emote",
                reward_id,
            )
        )
        rewards.extend(
            self._entity_rewards(
                "ornament",
                row.get("ornamentsReward"),
                "ornaments.json",
                "Ornement",
                reward_id,
            )
        )
        rewards.extend(
            self._entity_rewards(
                "alteration",
                row.get("alterationsReward"),
                "alterations.json",
                "Alteration",
                reward_id,
            )
        )
        return rewards

    def _dungeon_links(
        self,
        dungeon_rows: Mapping[int, dict[str, Any]],
        dungeon_names: dict[int, str],
    ) -> dict[int, tuple[EntityRef, ...]]:
        result: dict[int, list[EntityRef]] = defaultdict(list)
        for dungeon_id, row in dungeon_rows.items():
            for achievement_id in array_value(row.get("achievements")):
                aid = safe_int(achievement_id)
                if aid is None:
                    continue
                result[aid].append(
                    EntityRef(
                        "dungeon",
                        dungeon_id,
                        dungeon_names.get(
                            dungeon_id,
                            f"Donjon {dungeon_id}",
                        ),
                    )
                )
        return {
            achievement_id: tuple(self._unique_refs(refs))
            for achievement_id, refs in result.items()
        }

    def _named_rows(
        self,
        rows: Mapping[int, dict[str, Any]],
        entries: Mapping[str, Any],
        fallback: str,
    ) -> dict[int, str]:
        return {
            row_id: localized_name(row, entries, f"{fallback} {row_id}")
            for row_id, row in rows.items()
        }

    def _entity_rewards(
        self,
        kind: str,
        value: Any,
        filename: str,
        fallback: str,
        source_id: int,
    ) -> list[Reward]:
        rewards = []
        path = self.data_dir / filename
        if not path.is_file():
            return rewards
        rows = self._sources.rows(path)
        entries = self._entries or {}
        for ident in array_value(value):
            entity_id = safe_int(ident)
            if entity_id is None:
                continue
            row = rows.get(entity_id)
            if not isinstance(row, dict):
                continue
            name = localized_name(row, entries, f"{fallback} {entity_id}")
            if not name or normalize_text(name) == normalize_text(
                f"{fallback} {entity_id}"
            ):
                continue
            rewards.append(
                Reward(
                    kind=kind,
                    name=name,
                    quantity=1,
                    entity_id=entity_id,
                    source_id=source_id,
                )
            )
        return rewards

    def _objective_entity_refs(
        self,
        criterion: str,
        quest_names: dict[int, str],
        monster_names: dict[int, str],
        achievement_names: dict[int, str],
    ) -> tuple[EntityRef, ...]:
        matches: list[tuple[int, EntityRef]] = []
        for match in QUEST_CRITERION_RE.finditer(criterion):
            quest_id = safe_int(match.group(1))
            if quest_id is not None and quest_id in quest_names:
                matches.append(
                    (
                        match.start(),
                        EntityRef("quest", quest_id, quest_names[quest_id]),
                    )
                )
        for match in MONSTER_CRITERION_RE.finditer(criterion):
            monster_id = safe_int(match.group(1))
            if monster_id is not None and monster_id in monster_names:
                matches.append(
                    (
                        match.start(),
                        EntityRef("monster", monster_id, monster_names[monster_id]),
                    )
                )
        for match in ACHIEVEMENT_CRITERION_RE.finditer(criterion):
            achievement_id = safe_int(match.group(1))
            if achievement_id is not None and achievement_id in achievement_names:
                matches.append(
                    (
                        match.start(),
                        EntityRef(
                            "achievement",
                            achievement_id,
                            achievement_names[achievement_id],
                        ),
                    )
                )
        matches.sort(key=lambda value: value[0])
        return tuple(self._unique_refs(ref for _position, ref in matches))

    def _objective_type(self, criterion: str) -> str:
        if QUEST_CRITERION_RE.search(criterion):
            return "Quête"
        if MONSTER_CRITERION_RE.search(criterion):
            return "Monstre"
        if ACHIEVEMENT_CRITERION_RE.search(criterion):
            return "Succès"
        match = CRITERION_CODE_RE.search(criterion)
        return f"Critère {match.group(1)}" if match else ""

    def _category_labels(self, category_id: int) -> tuple[str, int | None, str]:
        category = self._categories.get(category_id)
        if category is None:
            return f"Categorie {category_id}", None, ""
        parent = self._categories.get(category.parent_id)
        if parent is None or category.parent_id == 0:
            return category.name, None, ""
        return parent.name, category.id, category.name

    def _top_category_id(self, category_id: int) -> int:
        category = self._categories.get(category_id)
        if category is None or category.parent_id == 0:
            return category_id
        return category.parent_id

    def _category_order(self, category_id: int) -> int:
        category = self._categories.get(category_id)
        return category.order if category is not None else 9999

    def _image_for_icon(
        self,
        icon_id: int | None,
        folders: tuple[str, ...],
    ) -> str:
        if icon_id is None:
            return ""
        return self._local_image_index(folders).get(int(icon_id), "")

    def _local_image_index(self, folders: tuple[str, ...]) -> dict[int, str]:
        if folders in self._image_indexes:
            return self._image_indexes[folders]
        index: dict[int, str] = {}
        for folder in folders:
            root = DATA_DIR / "images" / folder
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.suffix.casefold() not in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".ico",
                }:
                    continue
                ident = safe_int(path.stem)
                if ident is None:
                    continue
                index.setdefault(ident, str(path))
        self._image_indexes[folders] = index
        return index

    def _unique_refs(self, refs: Any) -> list[EntityRef]:
        unique: dict[tuple[str, int], EntityRef] = {}
        for ref in refs:
            if not isinstance(ref, EntityRef):
                continue
            unique.setdefault((ref.entity_type, ref.entity_id), ref)
        return list(unique.values())
