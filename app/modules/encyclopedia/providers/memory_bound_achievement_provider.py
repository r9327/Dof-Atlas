from __future__ import annotations

import hashlib
import json
import re
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
from app.quest_source_index import JsonSourceMapping, QuestSources


_DUMP_COMPACT_FLAG = "--dump-compact"
_DUMP_DETAIL_FLAG = "--dump-detail"
_SPACE_RE = re.compile(r"\s*")


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


def _entity_ref_to_dict(ref: EntityRef) -> dict[str, object]:
    return {
        "entity_type": str(ref.entity_type),
        "entity_id": ref.entity_id,
        "label": str(ref.label or ""),
    }


def _compact_objective_dict(objective: AchievementObjective) -> dict[str, object]:
    objective_type = str(objective.objective_type or "")
    keep_text = objective_type.strip().casefold() == "critère pr"
    return {
        "id": int(objective.id),
        "achievement_id": int(objective.achievement_id),
        "text": str(objective.text or "") if keep_text else "",
        "criterion": str(objective.criterion or ""),
        "order": int(objective.order or 0),
        "objective_type": objective_type,
        "required_quantity": objective.required_quantity,
        "entity_ref": (
            {
                "entity_type": str(objective.entity_ref.entity_type),
                "entity_id": objective.entity_ref.entity_id,
                "label": "",
            }
            if objective.entity_ref is not None
            else None
        ),
        "entity_refs": [
            {
                "entity_type": str(ref.entity_type),
                "entity_id": ref.entity_id,
                "label": "",
            }
            for ref in objective.entity_refs
        ],
    }


def _compact_achievement_dict(achievement: Achievement) -> dict[str, object]:
    raw = achievement.raw if isinstance(achievement.raw, dict) else {}
    source_category_id = raw.get("categoryId")
    return {
        "id": int(achievement.id),
        "original_id": int(achievement.original_id),
        "name": str(achievement.name or ""),
        "description": "",
        "category_id": int(achievement.category_id),
        "category_name": str(achievement.category_name or ""),
        "subcategory_id": achievement.subcategory_id,
        "subcategory_name": str(achievement.subcategory_name or ""),
        "level": achievement.level,
        "points": int(achievement.points or 0),
        "icon_id": achievement.icon_id,
        "image_path": str(achievement.image_path or ""),
        "order": int(achievement.order or 0),
        "objective_ids": list(achievement.objective_ids),
        "reward_ids": list(achievement.reward_ids),
        "objectives": [
            _compact_objective_dict(objective)
            for objective in achievement.objectives
        ],
        "rewards": [],
        "linked_quests": [_entity_ref_to_dict(ref) for ref in achievement.linked_quests],
        "linked_monsters": [_entity_ref_to_dict(ref) for ref in achievement.linked_monsters],
        "linked_dungeons": [_entity_ref_to_dict(ref) for ref in achievement.linked_dungeons],
        "linked_achievements": [_entity_ref_to_dict(ref) for ref in achievement.linked_achievements],
        "resolved_linked_quests": [],
        "resolved_linked_monsters": [],
        "resolved_linked_dungeons": [],
        "search_text": str(achievement.search_text or ""),
        "raw": (
            {"categoryId": source_category_id}
            if source_category_id is not None
            else {}
        ),
    }


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


class _SelectedEntriesMapping(JsonSourceMapping):
    """Offset mapping for only the localization IDs used by the compact catalogue."""

    def __init__(self, path: Path, cache_root: Path, selected_keys: set[str]) -> None:
        self._selected_keys = frozenset(str(key) for key in selected_keys)
        key_digest = hashlib.sha256(
            "\0".join(sorted(self._selected_keys)).encode("utf-8")
        ).hexdigest()
        super().__init__(
            path,
            cache_root,
            f"entries:selected:{key_digest}",
            doduda=False,
            required=True,
        )

    def _build_offsets(self, _field):
        if not self._selected_keys:
            return {}

        data = self.path.read_bytes().decode("utf-8")
        marker = re.search(r'"entries"\s*:\s*\{', data)
        if marker is None:
            self._source_failure("champ requis absent (entries)")
            return {}

        decoder = json.JSONDecoder()
        cursor = marker.end()
        byte_cursor = len(data[:cursor].encode("utf-8"))
        previous = cursor
        offsets: dict[str, tuple[int, int]] = {}
        remaining = set(self._selected_keys)

        while remaining:
            cursor = _SPACE_RE.match(data, cursor).end()
            if data[cursor:cursor + 1] == "}":
                break
            key, cursor = decoder.raw_decode(data, cursor)
            cursor = _SPACE_RE.match(data, cursor).end()
            if data[cursor:cursor + 1] != ":":
                raise ValueError("Missing JSON member separator")
            cursor = _SPACE_RE.match(data, cursor + 1).end()
            byte_cursor += len(data[previous:cursor].encode("utf-8"))
            start = byte_cursor
            _value, value_end = decoder.raw_decode(data, cursor)
            byte_cursor += len(data[cursor:value_end].encode("utf-8"))
            key_text = str(key)
            if key_text in remaining:
                offsets[key_text] = (start, byte_cursor)
                remaining.remove(key_text)
            previous = value_end
            cursor = _SPACE_RE.match(data, value_end).end()
            if data[cursor:cursor + 1] == ",":
                cursor += 1
            elif data[cursor:cursor + 1] != "}":
                raise ValueError("Missing JSON member delimiter")
        return offsets


class _CompactAchievementSources(QuestSources):
    def __init__(
        self,
        cache_root: Path,
        language_path: Path,
        selected_text_ids: set[str],
    ) -> None:
        super().__init__(cache_root)
        self._language_path = Path(language_path).resolve(strict=False)
        self._selected_text_ids = set(selected_text_ids)

    def mapping(self, path, field, *, doduda=False, required=None):
        path = Path(path)
        if (
            not doduda
            and str(field) == "entries"
            and path.resolve(strict=False) == self._language_path
        ):
            if required is None:
                required = True
            key = (path, field, doduda, bool(required))
            if key not in self._mappings:
                self._mappings[key] = _SelectedEntriesMapping(
                    path,
                    self.cache_root,
                    self._selected_text_ids,
                )
            return self._mappings[key]
        return super().mapping(path, field, doduda=doduda, required=required)


def _collect_compact_text_ids(data_dir: Path, cache_root: Path) -> set[str]:
    """Collect localization IDs before loading the rich Success graph.

    Raw game rows are scanned one source at a time so their offset dictionaries
    do not accumulate. The large language file can then keep offsets only for
    strings that the compact catalogue actually references.
    """

    selected: set[str] = set()
    category_parents: dict[int, int] = {}
    achievement_categories: dict[int, int] = {}
    retained = {int(value) for value in RETAINED_TOP_CATEGORY_IDS}

    def add_text_id(value: object) -> None:
        ident = safe_int(value)
        if ident is not None and ident >= 0:
            selected.add(str(ident))

    def scan(filename: str, visitor) -> None:
        sources = QuestSources(cache_root)
        try:
            for ident, row in sources.rows(data_dir / filename).items():
                visitor(int(ident), row)
        finally:
            sources.close()

    def visit_category(category_id: int, row: dict[str, Any]) -> None:
        category_parents[category_id] = safe_int(row.get("parentId"), 0) or 0
        add_text_id(row.get("nameId"))

    scan("achievement_categories.json", visit_category)

    def top_category(category_id: int) -> int:
        parent_id = category_parents.get(int(category_id), 0)
        return parent_id if parent_id else int(category_id)

    def visit_achievement(achievement_id: int, row: dict[str, Any]) -> None:
        achievement_categories[achievement_id] = safe_int(row.get("categoryId"), 0) or 0
        add_text_id(row.get("nameId"))
        add_text_id(row.get("descriptionId"))

    scan("achievements.json", visit_achievement)

    def visit_named_row(_row_id: int, row: dict[str, Any]) -> None:
        add_text_id(row.get("nameId"))

    for filename in ("quests.json", "monsters.json", "dungeons.json"):
        scan(filename, visit_named_row)

    def visit_objective(_objective_id: int, row: dict[str, Any]) -> None:
        achievement_id = safe_int(row.get("achievementId"))
        if achievement_id is None:
            return
        category_id = achievement_categories.get(achievement_id, 0)
        if top_category(category_id) in retained:
            add_text_id(row.get("nameId"))

    scan("achievement_objectives.json", visit_objective)
    return selected


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

    def release_catalogue(self) -> None:
        """Drop reconstructible Success runtime data while keeping the provider reusable."""

        self._loaded = False
        self._achievements = []
        self._by_id = {}
        self._categories = {}
        self._by_category = defaultdict(list)
        self._linked_quests = {}
        self._linked_monsters = {}
        self._linked_dungeons = {}
        self._linked_achievements = {}
        self._by_quest = defaultdict(list)
        self._image_indexes.clear()
        self._detail_cache_id = None
        self._detail_cache = None
        self._detail_sources_ready = False
        self._reset_sources()

    def _image_for_icon(self, icon_id: int | None, folders: tuple[str, ...]) -> str:
        if self._catalog_loading:
            return ""
        return super()._image_for_icon(icon_id, folders)

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
        cache_root = self._sources.cache_root
        selected_text_ids = _collect_compact_text_ids(self.data_dir, cache_root)
        self._sources.close()
        self._sources = _CompactAchievementSources(
            cache_root,
            self.data_dir / "languages" / "fr.json",
            selected_text_ids,
        )
        self._entries = None
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

    def load_all(self) -> list[Achievement]:
        self._ensure_loaded()
        # Rich reward/document indexes are now detail-only and live in the
        # disposable detail subprocess for the default runtime.
        return list(self._achievements)

    def prepare_detail_sources(self) -> None:
        if self._detail_sources_ready:
            return
        try:
            super().prepare_detail_sources()
        finally:
            self._reset_sources()

    def _get_detail_in_process(self, achievement_id: int):
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            return self._detail_cache
        if not self._detail_sources_ready:
            self.prepare_detail_sources()
        self._entries = self._sources.mapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            required=True,
        )
        try:
            return BaseAchievementProvider.get_detail_by_id(self, achievement_id)
        finally:
            self._reset_sources()

    def get_detail_by_id(self, achievement_id: int):
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            return self._detail_cache

        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if (
            not bool(getattr(sys, "frozen", False))
            and current_data_dir == default_data_dir
            and _DUMP_DETAIL_FLAG not in sys.argv
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
                    _DUMP_DETAIL_FLAG,
                    str(achievement_id),
                ],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                check=True,
            )
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            if not lines:
                return None
            payload = json.loads(lines[-1])
            if not isinstance(payload, dict):
                return None
            detail = _achievement_from_dict(payload)
            self._detail_cache_id = achievement_id
            self._detail_cache = detail
            return detail

        return self._get_detail_in_process(achievement_id)

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
                {"kind": "achievement", "value": _compact_achievement_dict(achievement)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    return 0


def _dump_default_detail(achievement_id: int) -> int:
    provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
    provider._load_in_process()
    provider._loaded = True
    detail = provider._get_detail_in_process(int(achievement_id))
    if detail is None:
        return 2
    print(
        json.dumps(
            asdict(detail),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__" and _DUMP_COMPACT_FLAG in sys.argv:
    raise SystemExit(_dump_compact_default_catalogue())

if __name__ == "__main__" and _DUMP_DETAIL_FLAG in sys.argv:
    try:
        detail_id = int(sys.argv[sys.argv.index(_DUMP_DETAIL_FLAG) + 1])
    except (ValueError, IndexError):
        raise SystemExit(2)
    raise SystemExit(_dump_default_detail(detail_id))


__all__ = ["MemoryBoundAchievementProvider"]
