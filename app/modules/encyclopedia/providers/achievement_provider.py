from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
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
from app.quest_catalog import array_value, doduda_rows, localized_name, normalize_text, read_json_file, text_for

QUEST_CRITERION_RE = re.compile(r"\bQf\s*[=><!]+\s*(\d+)", re.IGNORECASE)
MONSTER_CRITERION_RE = re.compile(r"\bEM\s*[=><!]+\s*(\d+)", re.IGNORECASE)
ACHIEVEMENT_CRITERION_RE = re.compile(r"\bOA\s*[=><!]+\s*(\d+)", re.IGNORECASE)
CRITERION_CODE_RE = re.compile(r"\b([A-Za-z]{1,3})\s*[=><!]+")

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

    def load_all(self) -> list[Achievement]:
        self._ensure_loaded()
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
            key=lambda category: (category.parent_id != 0, category.parent_id, category.order, normalize_text(category.name), category.id),
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
        language = read_json_file(self.data_dir / "languages" / "fr.json", {"entries": {}})
        entries = language.get("entries", {}) if isinstance(language, dict) else {}
        if not isinstance(entries, dict):
            entries = {}

        achievement_rows = doduda_rows(self.data_dir / "achievements.json")
        objective_rows = doduda_rows(self.data_dir / "achievement_objectives.json")
        reward_rows = doduda_rows(self.data_dir / "achievement_rewards.json")
        category_rows = doduda_rows(self.data_dir / "achievement_categories.json")
        quest_rows = doduda_rows(self.data_dir / "quests.json")
        monster_rows = doduda_rows(self.data_dir / "monsters.json")
        dungeon_rows = doduda_rows(self.data_dir / "dungeons.json")
        item_rows = doduda_rows(self.data_dir / "items.json")
        spell_rows = doduda_rows(self.data_dir / "spells.json")
        title_rows = doduda_rows(self.data_dir / "titles.json")
        emoticon_rows = doduda_rows(self.data_dir / "emoticons.json")
        ornament_rows = doduda_rows(self.data_dir / "ornaments.json")
        alteration_rows = doduda_rows(self.data_dir / "alterations.json")

        self._categories = self._load_categories(category_rows, entries)
        achievement_names = self._named_rows(achievement_rows, entries, "Succes")
        quest_names = self._named_rows(quest_rows, entries, "Quete")
        monster_names = self._named_rows(monster_rows, entries, "Monstre")
        dungeon_names = self._named_rows(dungeon_rows, entries, "Donjon")
        item_names = self._named_rows(item_rows, entries, "Objet")
        spell_names = self._named_rows(spell_rows, entries, "Sort")
        title_names = self._named_rows(title_rows, entries, "Titre")
        emoticon_names = self._named_rows(emoticon_rows, entries, "Emote")
        ornament_names = self._named_rows(ornament_rows, entries, "Ornement")
        alteration_names = self._named_rows(alteration_rows, entries, "Alteration")
        item_images = self._item_images(item_rows)

        objectives_by_achievement = self._objectives_by_achievement(
            objective_rows,
            achievement_rows,
            entries,
            quest_names,
            monster_names,
            achievement_names,
        )
        rewards_by_achievement = self._rewards_by_achievement(
            reward_rows,
            item_names,
            item_images,
            spell_names,
            title_names,
            emoticon_names,
            ornament_names,
            alteration_names,
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
            rewards = tuple(
                [
                    Reward(
                        kind="achievement_points",
                        name="Points de succès",
                        quantity=max(0, safe_int(row.get("points"), 0) or 0),
                        source_id=achievement_id,
                    ),
                    *rewards_by_achievement.get(achievement_id, ()),
                ]
            )
            objective_refs = [ref for objective in objectives for ref in objective.entity_refs]
            # Keep the historical direct-link contract for Guides/get_by_quest:
            # one primary entity per objective. The exhaustive Lot 7 catalogue
            # uses entity_refs and the resolved_* fields below.
            primary_refs = [objective.entity_ref for objective in objectives if objective.entity_ref is not None]
            quest_refs = tuple(self._unique_refs(ref for ref in primary_refs if ref.entity_type == "quest"))
            monster_refs = tuple(self._unique_refs(ref for ref in primary_refs if ref.entity_type == "monster"))
            achievement_refs = tuple(self._unique_refs(ref for ref in objective_refs if ref.entity_type == "achievement"))
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
                image_path=self._image_for_icon(safe_int(row.get("iconId")), ("achievements", "icons", "misc")),
                order=safe_int(row.get("order"), 0) or 0,
                objective_ids=tuple(int(value) for value in array_value(row.get("objectiveIds")) if safe_int(value) is not None),
                reward_ids=tuple(int(value) for value in array_value(row.get("rewardIds")) if safe_int(value) is not None),
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

        # Meta-achievements (OA criteria) inherit their linked content in the
        # exact objective order. This makes their content discoverable without
        # turning alternative criteria into additional completion checkboxes.
        direct_by_id = {achievement.id: achievement for achievement in achievements}
        resolved: dict[int, tuple[tuple[EntityRef, ...], tuple[EntityRef, ...], tuple[EntityRef, ...]]] = {}

        def resolve_links(
            achievement_id: int,
            visiting: frozenset[int] = frozenset(),
        ) -> tuple[tuple[EntityRef, ...], tuple[EntityRef, ...], tuple[EntityRef, ...]]:
            if achievement_id in resolved:
                return resolved[achievement_id]
            achievement = direct_by_id.get(achievement_id)
            if achievement is None or achievement_id in visiting:
                return (), (), ()
            all_objective_refs = [ref for objective in achievement.objectives for ref in objective.entity_refs]
            quests = [ref for ref in all_objective_refs if ref.entity_type == "quest"]
            monsters = [ref for ref in all_objective_refs if ref.entity_type == "monster"]
            dungeons = list(achievement.linked_dungeons)
            next_visiting = visiting | {achievement_id}
            for ref in achievement.linked_achievements:
                child_quests, child_monsters, child_dungeons = resolve_links(int(ref.entity_id), next_visiting)
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
            for position, achievement_id in enumerate(QUEST_GENERAL_PINNED_ACHIEVEMENT_IDS)
        }
        world_positions = {
            achievement_id: position
            for position, achievement_id in enumerate(QUEST_WORLD_ACHIEVEMENT_IDS)
        }

        def source_position(achievement: Achievement, source_category_id: int) -> int:
            declared = category_positions.get((source_category_id, achievement.id), 999999)
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
            source_category_id = safe_int(achievement.raw.get("categoryId"), achievement.category_id) or achievement.category_id
            return (
                self._category_order(achievement.category_id),
                self._category_order(achievement.subcategory_id or achievement.category_id),
                source_position(achievement, source_category_id),
                achievement.order,
                achievement.id,
            )

        self._achievements = sorted(
            achievements,
            key=achievement_sort_key,
        )
        self._by_id = {achievement.id: achievement for achievement in self._achievements}
        by_category = defaultdict(list)
        for achievement in self._achievements:
            by_category[achievement.category_id].append(achievement)
            if achievement.subcategory_id is not None:
                by_category[achievement.subcategory_id].append(achievement)
        self._by_category = defaultdict(list, {key: sorted(value, key=achievement_sort_key) for key, value in by_category.items()})
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
            {quest_id: sorted(values, key=lambda item: (item.order, normalize_text(item.name), item.id)) for quest_id, values in by_quest.items()},
        )

    def _load_categories(
        self,
        rows: dict[int, dict[str, Any]],
        entries: dict[str, Any],
    ) -> dict[int, AchievementCategory]:
        categories = {}
        for category_id, row in rows.items():
            categories[category_id] = AchievementCategory(
                id=category_id,
                name=text_for(entries, row.get("nameId"), f"Categorie {category_id}"),
                parent_id=safe_int(row.get("parentId"), 0) or 0,
                order=safe_int(row.get("order"), 0) or 0,
                achievement_ids=tuple(int(value) for value in array_value(row.get("achievementIds")) if safe_int(value) is not None),
            )
        return categories

    def _objectives_by_achievement(
        self,
        rows: dict[int, dict[str, Any]],
        achievement_rows: dict[int, dict[str, Any]],
        entries: dict[str, Any],
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
                    text=text_for(entries, row.get("nameId"), f"Objectif {objective_id}"),
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
                for value in array_value(achievement_rows.get(achievement_id, {}).get("objectiveIds"))
                if safe_int(value) is not None
            ]
            positions = {objective_id: position for position, objective_id in enumerate(declared)}
            ordered[achievement_id] = tuple(
                sorted(
                    objectives,
                    key=lambda objective: (positions.get(objective.id, 999999), objective.order, objective.id),
                )
            )
        return ordered

    def _rewards_by_achievement(
        self,
        rows: dict[int, dict[str, Any]],
        item_names: dict[int, str],
        item_images: dict[int, str],
        spell_names: dict[int, str],
        title_names: dict[int, str],
        emoticon_names: dict[int, str],
        ornament_names: dict[int, str],
        alteration_names: dict[int, str],
    ) -> dict[int, tuple[Reward, ...]]:
        result: dict[int, list[Reward]] = defaultdict(list)
        for reward_id, row in rows.items():
            achievement_id = safe_int(row.get("achievementId"))
            if achievement_id is None:
                continue
            rewards: list[Reward] = []
            experience_ratio = safe_int(row.get("experienceRatio"), 0) or 0
            kamas_ratio = safe_int(row.get("kamasRatio"), 0) or 0
            guild_points = safe_int(row.get("guildPoints"), 0) or 0
            if experience_ratio > 0:
                rewards.append(Reward("xp_ratio", "Expérience", experience_ratio, source_id=reward_id))
            if kamas_ratio > 0:
                rewards.append(Reward("kamas_ratio", "Kamas", kamas_ratio, source_id=reward_id))
            if guild_points > 0:
                rewards.append(Reward("guild_points", "Points de guilde", guild_points, source_id=reward_id))
            item_ids = [safe_int(value) for value in array_value(row.get("itemsReward"))]
            quantities = [safe_int(value, 1) or 1 for value in array_value(row.get("itemsQuantityReward"))]
            for index, item_id in enumerate(item_id for item_id in item_ids if item_id is not None):
                quantity = quantities[index] if index < len(quantities) else 1
                item_name = item_names.get(item_id, "")
                if not item_name or normalize_text(item_name) == normalize_text(f"Objet {item_id}"):
                    continue
                rewards.append(
                    Reward(
                        kind="item",
                        name=item_name,
                        quantity=quantity,
                        entity_id=item_id,
                        image_path=item_images.get(item_id, ""),
                        source_id=reward_id,
                    )
                )
            rewards.extend(self._entity_rewards("spell", row.get("spellsReward"), spell_names, "Sort", reward_id))
            rewards.extend(self._entity_rewards("title", row.get("titlesReward"), title_names, "Titre", reward_id))
            rewards.extend(self._entity_rewards("emote", row.get("emotesReward"), emoticon_names, "Emote", reward_id))
            rewards.extend(self._entity_rewards("ornament", row.get("ornamentsReward"), ornament_names, "Ornement", reward_id))
            rewards.extend(self._entity_rewards("alteration", row.get("alterationsReward"), alteration_names, "Alteration", reward_id))
            if rewards:
                result[achievement_id].extend(rewards)
        return {achievement_id: tuple(rewards) for achievement_id, rewards in result.items()}

    def _dungeon_links(
        self,
        dungeon_rows: dict[int, dict[str, Any]],
        dungeon_names: dict[int, str],
    ) -> dict[int, tuple[EntityRef, ...]]:
        result: dict[int, list[EntityRef]] = defaultdict(list)
        for dungeon_id, row in dungeon_rows.items():
            for achievement_id in array_value(row.get("achievements")):
                aid = safe_int(achievement_id)
                if aid is None:
                    continue
                result[aid].append(EntityRef("dungeon", dungeon_id, dungeon_names.get(dungeon_id, f"Donjon {dungeon_id}")))
        return {achievement_id: tuple(self._unique_refs(refs)) for achievement_id, refs in result.items()}

    def _named_rows(self, rows: dict[int, dict[str, Any]], entries: dict[str, Any], fallback: str) -> dict[int, str]:
        return {
            row_id: localized_name(row, entries, f"{fallback} {row_id}")
            for row_id, row in rows.items()
        }

    def _item_images(self, item_rows: dict[int, dict[str, Any]]) -> dict[int, str]:
        images: dict[int, str] = {}
        for item_id, row in item_rows.items():
            icon_id = safe_int(row.get("iconId"))
            path = self._image_for_icon(icon_id, ("items", "resources"))
            if path:
                images[item_id] = path
        return images

    def _entity_rewards(
        self,
        kind: str,
        value: Any,
        names: dict[int, str],
        fallback: str,
        source_id: int,
    ) -> list[Reward]:
        rewards = []
        for ident in array_value(value):
            entity_id = safe_int(ident)
            if entity_id is None:
                continue
            name = names.get(entity_id, "")
            if not name or normalize_text(name) == normalize_text(f"{fallback} {entity_id}"):
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
                matches.append((match.start(), EntityRef("quest", quest_id, quest_names[quest_id])))
        for match in MONSTER_CRITERION_RE.finditer(criterion):
            monster_id = safe_int(match.group(1))
            if monster_id is not None and monster_id in monster_names:
                matches.append((match.start(), EntityRef("monster", monster_id, monster_names[monster_id])))
        for match in ACHIEVEMENT_CRITERION_RE.finditer(criterion):
            achievement_id = safe_int(match.group(1))
            if achievement_id is not None and achievement_id in achievement_names:
                matches.append(
                    (
                        match.start(),
                        EntityRef("achievement", achievement_id, achievement_names[achievement_id]),
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

    def _image_for_icon(self, icon_id: int | None, folders: tuple[str, ...]) -> str:
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
                if path.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp", ".ico"}:
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
