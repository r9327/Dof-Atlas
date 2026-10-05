from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.constants import RAW_QUEST_DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.achievement_catalog_policy import RETAINED_TOP_CATEGORY_IDS
from app.modules.encyclopedia.models.achievement import (
    Achievement,
    AchievementCategory,
    AchievementObjective,
)
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.models.reward import Reward
from app.modules.encyclopedia.providers.achievement_provider import (
    AchievementProvider as BaseAchievementProvider,
    safe_int,
)
from app.quest_catalog import array_value, text_for
from app.quest_source_index import QuestSources


_DUMP_COMPACT_FLAG = "--dump-compact"


def _entity_ref_from_dict(value: object) -> EntityRef | None:
    if not isinstance(value, dict):
        return None
    entity_id = value.get("entity_id")
    if entity_id is None:
        return None
    return EntityRef(
        entity_type=str(value.get("entity_type") or ""),
        entity_id=entity_id,
        label=str(value.get("label") or ""),
        metadata=dict(value.get("metadata") or {}) if isinstance(value.get("metadata"), dict) else None,
    )


def _entity_refs_from_rows(values: object) -> tuple[EntityRef, ...]:
    if not isinstance(values, list):
        return ()
    refs: list[EntityRef] = []
    for value in values:
        ref = _entity_ref_from_dict(value)
        if ref is not None:
            refs.append(ref)
    return tuple(refs)


def _reward_from_dict(value: object) -> Reward | None:
    if not isinstance(value, dict):
        return None
    return Reward(
        kind=str(value.get("kind") or ""),
        name=str(value.get("name") or ""),
        quantity=value.get("quantity") if isinstance(value.get("quantity"), int) else None,
        entity_id=value.get("entity_id") if isinstance(value.get("entity_id"), int) else None,
        image_path=str(value.get("image_path") or ""),
        source_id=value.get("source_id") if isinstance(value.get("source_id"), int) else None,
        metadata=dict(value.get("metadata") or {}) if isinstance(value.get("metadata"), dict) else {},
    )


def _objective_from_dict(value: object) -> AchievementObjective | None:
    if not isinstance(value, dict):
        return None
    entity_refs = _entity_refs_from_rows(value.get("entity_refs"))
    entity_ref = _entity_ref_from_dict(value.get("entity_ref"))
    return AchievementObjective(
        id=int(value.get("id") or 0),
        achievement_id=int(value.get("achievement_id") or 0),
        text=str(value.get("text") or ""),
        criterion=str(value.get("criterion") or ""),
        order=int(value.get("order") or 0),
        objective_type=str(value.get("objective_type") or ""),
        required_quantity=(
            int(value["required_quantity"])
            if isinstance(value.get("required_quantity"), int)
            else None
        ),
        entity_ref=entity_ref,
        entity_refs=entity_refs,
    )


def _achievement_from_dict(value: dict[str, Any]) -> Achievement:
    objectives = tuple(
        objective
        for row in value.get("objectives", [])
        if (objective := _objective_from_dict(row)) is not None
    )
    rewards = tuple(
        reward
        for row in value.get("rewards", [])
        if (reward := _reward_from_dict(row)) is not None
    )
    return Achievement(
        id=int(value["id"]),
        original_id=int(value.get("original_id", value["id"])),
        name=str(value.get("name") or ""),
        description=str(value.get("description") or ""),
        category_id=int(value.get("category_id") or 0),
        category_name=str(value.get("category_name") or ""),
        subcategory_id=(
            int(value["subcategory_id"])
            if isinstance(value.get("subcategory_id"), int)
            else None
        ),
        subcategory_name=str(value.get("subcategory_name") or ""),
        level=int(value["level"]) if isinstance(value.get("level"), int) else None,
        points=int(value.get("points") or 0),
        icon_id=int(value["icon_id"]) if isinstance(value.get("icon_id"), int) else None,
        image_path=str(value.get("image_path") or ""),
        order=int(value.get("order") or 0),
        objective_ids=tuple(int(item) for item in value.get("objective_ids", []) if isinstance(item, int)),
        reward_ids=tuple(int(item) for item in value.get("reward_ids", []) if isinstance(item, int)),
        objectives=objectives,
        rewards=rewards,
        linked_quests=_entity_refs_from_rows(value.get("linked_quests")),
        linked_monsters=_entity_refs_from_rows(value.get("linked_monsters")),
        linked_dungeons=_entity_refs_from_rows(value.get("linked_dungeons")),
        linked_achievements=_entity_refs_from_rows(value.get("linked_achievements")),
        resolved_linked_quests=_entity_refs_from_rows(value.get("resolved_linked_quests")),
        resolved_linked_monsters=_entity_refs_from_rows(value.get("resolved_linked_monsters")),
        resolved_linked_dungeons=_entity_refs_from_rows(value.get("resolved_linked_dungeons")),
        search_text=str(value.get("search_text") or ""),
        raw=dict(value.get("raw") or {}) if isinstance(value.get("raw"), dict) else {},
    )


class MemoryBoundAchievementProvider(BaseAchievementProvider):
    """Rich retained Success runtime with reconstructible bulk data off-heap."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._catalog_loading = False
        super().__init__(*args, **kwargs)

    def _reset_sources(self) -> None:
        cache_root = self._sources.cache_root
        try:
            self._sources.close()
        finally:
            self._sources = QuestSources(cache_root)
            self._entries = None

    def _image_for_icon(self, icon_id: int | None, folders: tuple[str, ...]) -> str:
        if self._catalog_loading:
            return ""
        return super()._image_for_icon(icon_id, folders)

    def _objectives_by_achievement(
        self,
        rows,
        achievement_rows,
        entries,
        quest_names: dict[int, str],
        monster_names: dict[int, str],
        achievement_names: dict[int, str],
    ) -> dict[int, tuple[AchievementObjective, ...]]:
        """Keep graph refs for every Success, rich objective text only when retained.

        The compact subprocess used to build the complete rich objective payload
        for all game achievements and then immediately erase most of it. That
        transient duplication was the dominant process-tree peak. Non-retained
        domains only need objective IDs/order and entity refs until link
        resolution; their text and criterion are never emitted to Atlas.
        """

        retained_ids = {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
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
            achievement_row = achievement_rows.get(achievement_id, {})
            source_category_id = safe_int(achievement_row.get("categoryId"), 0) or 0
            keep_rich_payload = self._top_category_id(source_category_id) in retained_ids
            result[achievement_id].append(
                AchievementObjective(
                    id=objective_id,
                    achievement_id=achievement_id,
                    text=(
                        text_for(entries, row.get("nameId"), f"Objectif {objective_id}")
                        if keep_rich_payload
                        else ""
                    ),
                    criterion=criterion if keep_rich_payload else "",
                    order=safe_int(row.get("order"), 0) or 0,
                    objective_type=(
                        self._objective_type(criterion) if keep_rich_payload else ""
                    ),
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

    def _trim_catalogue_payload(self) -> None:
        retained_ids = {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
        for achievement in self._achievements:
            raw = achievement.raw if isinstance(achievement.raw, dict) else {}
            source_category_id = raw.get("categoryId")
            object.__setattr__(
                achievement,
                "raw",
                ({"categoryId": source_category_id} if source_category_id is not None else {}),
            )

            # Atlas exposes only the retained Success domains in the catalogue.
            # Other Successes stay as lightweight identities so cross-links keep
            # resolving without pinning documentary objectives and descriptions.
            if int(achievement.category_id) not in retained_ids:
                object.__setattr__(achievement, "description", "")
                object.__setattr__(achievement, "objectives", ())
                object.__setattr__(achievement, "rewards", ())
                object.__setattr__(achievement, "linked_monsters", ())
                object.__setattr__(achievement, "linked_dungeons", ())
                object.__setattr__(achievement, "linked_achievements", ())
                object.__setattr__(achievement, "resolved_linked_monsters", ())
                object.__setattr__(achievement, "resolved_linked_dungeons", ())

        self._linked_quests = {}
        self._linked_monsters = {}
        self._linked_dungeons = {}
        self._linked_achievements = {}
        self._image_indexes.clear()

    def _load_in_process(self) -> None:
        self._catalog_loading = True
        try:
            super()._load()
        finally:
            self._catalog_loading = False
        self._trim_catalogue_payload()
        self._reset_sources()

    def _load_from_compact_subprocess(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
                _DUMP_COMPACT_FLAG,
            ],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        categories: dict[int, AchievementCategory] = {}
        achievements: list[Achievement] = []
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or "")
            value = row.get("value")
            if kind == "category" and isinstance(value, dict):
                category = AchievementCategory(
                    id=int(value["id"]),
                    name=str(value.get("name") or ""),
                    parent_id=int(value.get("parent_id") or 0),
                    order=int(value.get("order") or 0),
                    achievement_ids=tuple(
                        int(item)
                        for item in value.get("achievement_ids", [])
                        if isinstance(item, int)
                    ),
                )
                categories[category.id] = category
            elif kind == "achievement" and isinstance(value, dict):
                achievements.append(_achievement_from_dict(value))

        stderr = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait(timeout=10)
        if return_code != 0:
            raise RuntimeError(
                "Extraction compacte des succès impossible"
                + (f": {stderr.strip()}" if stderr.strip() else "")
            )
        if not achievements:
            raise RuntimeError("Extraction compacte des succès vide")

        self._categories = categories
        self._achievements = achievements
        self._by_id = {achievement.id: achievement for achievement in achievements}
        by_category: dict[int, list[Achievement]] = defaultdict(list)
        by_quest: dict[int, list[Achievement]] = defaultdict(list)
        for achievement in achievements:
            by_category[achievement.category_id].append(achievement)
            if achievement.subcategory_id is not None:
                by_category[achievement.subcategory_id].append(achievement)
            for ref in achievement.linked_quests:
                try:
                    by_quest[int(ref.entity_id)].append(achievement)
                except (TypeError, ValueError):
                    continue
        self._by_category = defaultdict(list, by_category)
        self._by_quest = defaultdict(list, by_quest)
        self._linked_quests = {}
        self._linked_monsters = {}
        self._linked_dungeons = {}
        self._linked_achievements = {}
        self._image_indexes.clear()
        self._reset_sources()

    def _load(self) -> None:
        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if bool(getattr(sys, "frozen", False)) or current_data_dir != default_data_dir:
            self._load_in_process()
            return
        self._load_from_compact_subprocess()

    def prepare_detail_sources(self) -> None:
        if self._detail_sources_ready:
            return
        try:
            super().prepare_detail_sources()
        finally:
            self._reset_sources()

    def get_detail_by_id(self, achievement_id: int):
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            return self._detail_cache

        self._entries = self._sources.mapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            required=True,
        )
        try:
            return super().get_detail_by_id(achievement_id)
        finally:
            self._reset_sources()

    def get_linked_quests(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_quests) if achievement is not None else []

    def get_linked_monsters(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_monsters) if achievement is not None else []

    def get_linked_dungeons(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_dungeons) if achievement is not None else []

    def get_linked_achievements(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_achievements) if achievement is not None else []


def _dump_compact_default_catalogue() -> int:
    provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
    provider._load_in_process()
    for category in provider._categories.values():
        print(
            json.dumps(
                {"kind": "category", "value": asdict(category)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    for achievement in provider._achievements:
        print(
            json.dumps(
                {"kind": "achievement", "value": asdict(achievement)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__" and _DUMP_COMPACT_FLAG in sys.argv:
    raise SystemExit(_dump_compact_default_catalogue())


__all__ = ["MemoryBoundAchievementProvider"]
