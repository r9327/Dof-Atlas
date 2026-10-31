from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from collections import OrderedDict, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from threading import current_thread
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.constants import RAW_QUEST_DATA_DIR, ROOT_DIR
from app.core.cache_write_lock import exclusive_cache_write_lock as _achievement_compact_write_lock
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
from app.quest_source_index import QuestSources, SelectedJsonValueMapping
from app.core.text import normalize_key as normalize_text


_DUMP_COMPACT_FLAG = "--dump-compact"
_DUMP_DETAIL_FLAG = "--dump-detail"
_BUILD_COMPACT_CACHE_FLAG = "--build-compact-cache"
_ENSURE_COMPACT_CACHE_FLAG = "--ensure-compact-cache"
_SPACE_RE = re.compile(r"\s*")
ACHIEVEMENT_COMPACT_CACHE = (
    ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_catalogue_v1.jsonl"
)
_ACHIEVEMENT_COMPACT_SCHEMA = 5
_ACHIEVEMENT_COMPACT_SOURCES = (
    "achievements.json",
    "achievement_categories.json",
    "achievement_objectives.json",
    "quests.json",
    "monsters.json",
    "dungeons.json",
    "languages/fr.json",
)


def _utf8_subprocess_env() -> dict[str, str]:
    """Keep JSON worker streams independent from the Windows ANSI code page."""

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _achievement_compact_source_signature(data_dir: Path) -> list[list[object]]:
    signature: list[list[object]] = []
    for relative in _ACHIEVEMENT_COMPACT_SOURCES:
        path = data_dir / relative
        try:
            stat = path.stat()
        except OSError:
            signature.append([relative, -1, -1, -1, -1])
            continue
        signature.append([
            relative, int(stat.st_size), int(stat.st_mtime_ns),
            int(stat.st_ctime_ns), int(stat.st_ino),
        ])
    return signature


def _achievement_compact_index_path(path: Path = ACHIEVEMENT_COMPACT_CACHE) -> Path:
    return path.with_suffix(path.suffix + ".idx.json")


def _achievement_compact_cache_valid(
    path: Path = ACHIEVEMENT_COMPACT_CACHE,
    *,
    data_dir: Path = RAW_QUEST_DATA_DIR,
) -> bool:
    try:
        with path.open("r", encoding="utf-8") as stream:
            meta = json.loads(stream.readline())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(meta, dict)
        and meta.get("kind") == "meta"
        and type(meta.get("schema_version")) is int
        and meta["schema_version"] == _ACHIEVEMENT_COMPACT_SCHEMA
        and meta.get("source_signature") == _achievement_compact_source_signature(data_dir)
        and _achievement_compact_index_path(path).is_file()
    )


def ensure_achievement_compact_cache(
    *,
    data_dir: Path = RAW_QUEST_DATA_DIR,
    path: Path = ACHIEVEMENT_COMPACT_CACHE,
) -> int:
    """Materialize compact Success summaries during controlled preload."""

    if _achievement_compact_cache_valid(path, data_dir=data_dir):
        try:
            index_payload = json.loads(
                _achievement_compact_index_path(path).read_text(encoding="utf-8")
            )
            if isinstance(index_payload, dict):
                count = index_payload.get("achievement_count")
                retained = index_payload.get("retained_count")
                retained_ids = index_payload.get("retained_ids")
                offsets = index_payload.get("offsets")
                with path.open("r", encoding="utf-8") as stream:
                    source_meta = json.loads(stream.readline())
                source_marker = source_meta.get("cache_generation")
                index_marker = index_payload.get("cache_generation")
                same_generation = (
                    (source_marker is None and index_marker is None)
                    or (isinstance(source_marker, str) and bool(source_marker)
                        and source_marker == index_marker)
                )
                if (same_generation
                        and type(count) is int and count > 0
                        and type(retained) is int and 0 < retained <= count
                        and isinstance(retained_ids, list)
                        and len(retained_ids) == retained
                        and all(type(value) is int for value in retained_ids)
                        and len(set(retained_ids)) == retained
                        and isinstance(offsets, dict)
                        and len(offsets) == retained
                        and set(offsets) == {str(value) for value in retained_ids}
                        and all(
                            isinstance(span, list) and len(span) == 2
                            and type(span[0]) is int and span[0] >= 0
                            and type(span[1]) is int and span[1] > 0
                            for span in offsets.values()
                        )):
                    return count
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        # The JSONL header can be valid while its sidecar is corrupt. A zero
        # result incorrectly certified an unbuilt cache instead of repairing it.
    if bool(getattr(sys, "frozen", False)):
        return 0
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
            _BUILD_COMPACT_CACHE_FLAG,
            str(path),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_utf8_subprocess_env(),
        timeout=90,
        check=True,
        # No transient console/conhost for captured disposable Windows workers.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("La génération du cache compact Succès n'a produit aucun résultat")
    payload = json.loads(lines[-1])
    return max(0, int(payload.get("achievement_count") or 0))



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
    """Compact one objective in the disposable worker before crossing process boundaries."""

    objective_type = str(objective.objective_type or "")
    keep_text = objective_type.strip().casefold() == "critère pr"
    return {
        "id": int(objective.id),
        "type": objective_type,
        "criterion": str(objective.criterion or ""),
        "text": str(objective.text or "") if keep_text else "",
        "refs": [
            [str(ref.entity_type), ref.entity_id]
            for ref in objective.entity_refs
        ],
    }


def _progress_objective_row(objective: AchievementObjective) -> list[object]:
    """Primitive auto-progress contract; rich objective models stay off-heap."""

    compact = _compact_objective_dict(objective)
    return [
        compact["id"],
        compact["type"],
        compact["criterion"],
        compact["text"],
        compact["refs"],
    ]

def _progress_objectives_from_rows(values: object) -> tuple[tuple[object, ...], ...]:
    if not isinstance(values, list):
        return ()
    output: list[tuple[object, ...]] = []
    for raw in values:
        if not isinstance(raw, list) or len(raw) != 5:
            continue
        try:
            objective_id = int(raw[0])
        except (TypeError, ValueError):
            continue
        refs: list[tuple[str, int]] = []
        if isinstance(raw[4], list):
            for raw_ref in raw[4]:
                if not isinstance(raw_ref, list) or len(raw_ref) != 2:
                    continue
                try:
                    entity_id = int(raw_ref[1])
                except (TypeError, ValueError):
                    continue
                refs.append((str(raw_ref[0] or ""), entity_id))
        output.append(
            (
                objective_id,
                str(raw[1] or ""),
                str(raw[2] or ""),
                str(raw[3] or ""),
                tuple(refs),
            )
        )
    return tuple(output)


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
        # Full objective models are detail-only. Auto-progress keeps a primitive
        # contract beside the summaries so thousands of dataclass/ref objects
        # never enter Atlas' long-lived heap.
        "objectives": [],
        "progress_objectives": [
            _progress_objective_row(objective)
            for objective in achievement.objectives
        ],
        "rewards": [],
        "linked_quests": [_entity_ref_to_dict(ref) for ref in achievement.linked_quests],
        "linked_monsters": [_entity_ref_to_dict(ref) for ref in achievement.linked_monsters],
        "linked_dungeons": [_entity_ref_to_dict(ref) for ref in achievement.linked_dungeons],
        "linked_achievements": [_entity_ref_to_dict(ref) for ref in achievement.linked_achievements],
        "resolved_linked_quests": (
            [_entity_ref_to_dict(ref) for ref in achievement.resolved_linked_quests]
            if int(achievement.category_id) in {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
            else []
        ),
        "resolved_linked_monsters": (
            [_entity_ref_to_dict(ref) for ref in achievement.resolved_linked_monsters]
            if int(achievement.category_id) in {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
            else []
        ),
        "resolved_linked_dungeons": (
            [_entity_ref_to_dict(ref) for ref in achievement.resolved_linked_dungeons]
            if int(achievement.category_id) in {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
            else []
        ),
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
                self._mappings[key] = SelectedJsonValueMapping(
                    path,
                    "entries",
                    self._selected_text_ids,
                    required=bool(required),
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
        self._progress_objectives: dict[int, str] = {}
        self._compat_cache_id: int | None = None
        self._compat_cache: Achievement | None = None
        self._compact_external_index: dict[int, tuple[int, int]] | None = None
        self._compact_retained_ids: tuple[int, ...] = ()
        self._compact_retained_set: frozenset[int] = frozenset()
        self._compact_category_ids: dict[int, tuple[int, ...]] = {}
        self._compact_quest_link_cache: OrderedDict[int, tuple[int, ...]] = OrderedDict()
        self._compact_quest_link_stamp: tuple[int, int, int, int] | None = None
        # Optional precomputed relations in newer disposable sidecars.
        # None preserves the validated JSONL scan for historical caches.
        self._compact_quest_ids_by_quest: dict[int, tuple[int, ...]] | None = None
        self._compact_quest_map_stamp: tuple[int, int, int, int] | None = None
        self._compact_quest_sidecar_stamp: tuple[int, int, int, int] | None = None
        self._compact_summary_cache: OrderedDict[int, Achievement] = OrderedDict()
        # One active rich detail + two previous ones. Reopening a Success must
        # not spend another 5s rebuilding a disposable detail worker.
        self._recent_rich_details: OrderedDict[int, Achievement] = OrderedDict()
        self._last_detail_cache_source = "cold"
        # The previous cold event survives hot/recent hits, so Doctor can
        # measure the worker cost even when Qt renders from an already warm
        # detail after the stage signal.
        self._last_cold_detail_breakdown: dict[str, object] = {}
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
        self._recent_rich_details.clear()
        self._last_detail_cache_source = "cold"
        self._last_cold_detail_breakdown = {}
        self._detail_sources_ready = False
        self._progress_objectives = {}
        self._compat_cache_id = None
        self._compat_cache = None
        self._compact_external_index = None
        self._compact_retained_ids = ()
        self._compact_retained_set = frozenset()
        self._compact_category_ids = {}
        self._compact_quest_link_cache.clear()
        self._compact_quest_link_stamp = None
        self._compact_quest_ids_by_quest = None
        self._compact_quest_map_stamp = None
        self._compact_quest_sidecar_stamp = None
        self._compact_summary_cache.clear()
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

    def _finish_in_process_catalogue(self) -> None:
        self._trim_catalogue_payload()
        # A rebuilt catalogue invalidates previously hydrated rich details.
        self._detail_cache_id = None
        self._detail_cache = None
        self._recent_rich_details.clear()
        self._last_detail_cache_source = "cold"
        self._last_cold_detail_breakdown = {}
        self._progress_objectives = {
            int(achievement.id): json.dumps(
                [
                    _progress_objective_row(objective)
                    for objective in achievement.objectives
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for achievement in self._achievements
            if achievement.objectives
        }
        self._reset_sources()

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
        self._finish_in_process_catalogue()

    def _load_disposable_worker_fast(self) -> None:
        """Build compact Success data with one source pass in a disposable process.

        The long-lived Atlas path still uses selected localization values to keep
        its allocator high-water low.  A startup worker can instead keep the
        language byte-offset table for its short lifetime and avoid scanning the
        achievement/quest/monster sources once just to discover text IDs.
        """

        # Guide/Quest warmup runs first and has already prepared the canonical
        # byte-offset source indexes. Reuse that disposable cache namespace
        # instead of rebuilding the same offsets under achievement_sources_v1.
        shared_source_offsets = (
            ROOT_DIR / ".cache" / "dofus_atlas" / "quest_details_v1" / "source_offsets"
        )
        self._sources.close()
        self._sources = QuestSources(shared_source_offsets)
        self._entries = None
        self._catalog_loading = True
        try:
            super()._load()
        finally:
            self._catalog_loading = False
        self._finish_in_process_catalogue()

    def _install_compact_rows(
        self,
        categories: dict[int, AchievementCategory],
        achievements: list[Achievement],
        progress_objectives: dict[int, str],
    ) -> None:
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
        self._compact_quest_ids_by_quest = None
        self._compact_quest_map_stamp = None
        self._compact_quest_sidecar_stamp = None
        self._progress_objectives = progress_objectives
        # Compatibility subprocess may replace the whole catalogue in the
        # same provider. Never retain rich detail objects from older sources.
        self._detail_cache_id = None
        self._detail_cache = None
        self._recent_rich_details.clear()
        self._last_cold_detail_breakdown = {}
        self._last_detail_cache_source = "cold"
        self._linked_quests = {}
        self._linked_monsters = {}
        self._linked_dungeons = {}
        self._linked_achievements = {}
        self._image_indexes.clear()
        self._reset_sources()

    def _consume_compact_row(
        self,
        row: dict[str, object],
        categories: dict[int, AchievementCategory],
        achievements: list[Achievement],
        progress_objectives: dict[int, str],
        *,
        retained_only: bool,
    ) -> bool:
        kind = str(row.get("kind") or "")
        if kind == "external_start" and retained_only:
            return False
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
            achievement = _achievement_from_dict(value)
            if retained_only and int(achievement.category_id) not in {
                int(item) for item in RETAINED_TOP_CATEGORY_IDS
            }:
                return True
            achievements.append(achievement)
            raw_progress = value.get("progress_objectives")
            if isinstance(raw_progress, list) and raw_progress:
                progress_objectives[int(achievement.id)] = json.dumps(
                    raw_progress,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        return True

    def _load_from_compact_cache(self) -> None:
        if not _achievement_compact_cache_valid(
            ACHIEVEMENT_COMPACT_CACHE,
            data_dir=self.data_dir,
        ):
            raise RuntimeError("Cache compact Succès absent ou périmé")

        # The JSONL and its offset sidecar are published separately. Detect
        # concurrent replacement before installing an incoherent catalogue.
        def fingerprint(path: Path) -> tuple[int, int, int, int]:
            stat = path.stat()
            return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino

        source_path = ACHIEVEMENT_COMPACT_CACHE
        sidecar_path = _achievement_compact_index_path(source_path)
        source_generation = fingerprint(source_path)
        sidecar_generation = fingerprint(sidecar_path)
        try:
            index_payload = json.loads(
                sidecar_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Index compact Succès absent ou invalide") from exc

        categories: dict[int, AchievementCategory] = {}
        source_marker: object = None
        with ACHIEVEMENT_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    continue
                kind = str(row.get("kind") or "")
                if kind == "meta":
                    source_marker = row.get("cache_generation")
                    continue
                if kind == "achievement":
                    break
                value = row.get("value")
                if kind != "category" or not isinstance(value, dict):
                    continue
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

        raw_offsets = index_payload.get("offsets") if isinstance(index_payload, dict) else {}
        offsets: dict[int, tuple[int, int]] = {}
        if isinstance(raw_offsets, dict):
            for raw_id, span in raw_offsets.items():
                if not isinstance(span, list) or len(span) != 2:
                    continue
                try:
                    offsets[int(raw_id)] = (int(span[0]), int(span[1]))
                except (TypeError, ValueError):
                    continue

        def id_tuple_map(value: object) -> dict[int, tuple[int, ...]]:
            output: dict[int, tuple[int, ...]] = {}
            if not isinstance(value, dict):
                return output
            for raw_key, raw_ids in value.items():
                if not isinstance(raw_ids, list):
                    continue
                try:
                    key = int(raw_key)
                except (TypeError, ValueError):
                    continue
                ids: list[int] = []
                for raw_id in raw_ids:
                    try:
                        ids.append(int(raw_id))
                    except (TypeError, ValueError):
                        continue
                output[key] = tuple(ids)
            return output

        retained_ids = tuple(
            int(value)
            for value in (index_payload.get("retained_ids") or ())
            if isinstance(value, int)
        )
        if not categories or not retained_ids:
            raise RuntimeError("Index compact Succès incomplet")
        index_marker = index_payload.get("cache_generation")
        # Old schema-5 pairs had no marker and remain readable. A newly
        # published pair must carry the SAME non-empty generation token.
        if (source_marker is not None or index_marker is not None) and (
            not isinstance(source_marker, str) or not source_marker
            or source_marker != index_marker
        ):
            raise RuntimeError("Cache compact Succès et index de générations différentes")
        if (fingerprint(source_path) != source_generation
                or fingerprint(sidecar_path) != sidecar_generation):
            raise RuntimeError("Cache compact Succès remplacé pendant le chargement")

        self._categories = categories
        self._achievements = []
        self._by_id = {}
        self._by_category = defaultdict(list)
        self._by_quest = defaultdict(list)
        self._linked_quests = {}
        self._linked_monsters = {}
        self._linked_dungeons = {}
        self._linked_achievements = {}
        self._progress_objectives = {}
        self._compact_external_index = offsets
        self._compact_retained_ids = retained_ids
        self._compact_retained_set = frozenset(retained_ids)
        self._compact_category_ids = id_tuple_map(index_payload.get("by_category"))
        relation_rows = index_payload.get("by_quest")
        relation_count = index_payload.get("by_quest_ref_count")
        relation_map: dict[int, tuple[int, ...]] | None = None
        if isinstance(relation_rows, dict) and type(relation_count) is int:
            candidate: dict[int, tuple[int, ...]] = {}
            retained_set = set(retained_ids)
            observed = 0
            for raw_quest, raw_achievements in relation_rows.items():
                if (not isinstance(raw_quest, str)
                        or not 0 < len(raw_quest) <= 20
                        or not raw_quest.isascii() or not raw_quest.isdecimal()
                        or str(int(raw_quest)) != raw_quest
                        or not isinstance(raw_achievements, list)
                        or not raw_achievements
                        or any(type(ident) is not int or ident not in retained_set
                               for ident in raw_achievements)
                        or len(set(raw_achievements)) != len(raw_achievements)):
                    break
                candidate[int(raw_quest)] = tuple(raw_achievements)
                observed += len(raw_achievements)
            else:
                if observed == relation_count:
                    relation_map = candidate
        self._compact_quest_ids_by_quest = relation_map
        self._compact_quest_map_stamp = source_generation if relation_map is not None else None
        self._compact_quest_sidecar_stamp = (
            sidecar_generation if relation_map is not None else None
        )
        self._compact_quest_link_cache.clear()
        self._compact_quest_link_stamp = None
        self._compact_summary_cache.clear()
        self._detail_cache_id = None
        self._detail_cache = None
        self._recent_rich_details.clear()
        self._last_detail_cache_source = "cold"
        self._last_cold_detail_breakdown = {}
        self._image_indexes.clear()
        self._reset_sources()

    def _load_from_compact_subprocess(self) -> None:
        """Compatibility fallback used only when controlled preload did not build the cache."""

        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as error_output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.modules.encyclopedia.providers.memory_bound_achievement_provider",
                    _DUMP_COMPACT_FLAG,
                ],
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=error_output,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_utf8_subprocess_env(),
            )
            try:
                categories: dict[int, AchievementCategory] = {}
                achievements: list[Achievement] = []
                progress_objectives: dict[int, str] = {}
                assert process.stdout is not None
                retained_ids = {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
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
                        category_id = safe_int(value.get("category_id"), 0) or 0
                        if int(category_id) not in retained_ids:
                            continue
                        achievement = _achievement_from_dict(value)
                        achievements.append(achievement)
                        raw_progress = value.get("progress_objectives")
                        if isinstance(raw_progress, list) and raw_progress:
                            progress_objectives[int(achievement.id)] = json.dumps(
                                raw_progress,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )

                return_code = process.wait(timeout=10)
                if return_code != 0:
                    error_output.seek(0)
                    stderr = error_output.read(8192)
                    raise RuntimeError(
                        "Extraction compacte des succès impossible"
                        + (f": {stderr.strip()}" if stderr.strip() else "")
                    )
                if not achievements:
                    raise RuntimeError("Extraction compacte des succès vide")
                self._install_compact_rows(categories, achievements, progress_objectives)
            finally:
                try:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                finally:
                    if process.stdout is not None:
                        process.stdout.close()

    def _load(self) -> None:
        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if current_data_dir != default_data_dir:
            self._load_in_process()
            return
        if _achievement_compact_cache_valid(
            ACHIEVEMENT_COMPACT_CACHE,
            data_dir=self.data_dir,
        ):
            try:
                # Packaged Windows can consume the compact Success catalogue.
                # Avoid materializing the full raw graph in the UI heap.
                self._load_from_compact_cache()
                return
            except (OSError, UnicodeError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                logging.getLogger(__name__).warning(
                    "Success compact cache rejected; rebuilding from sources: %s", exc,
                )
        if bool(getattr(sys, "frozen", False)):
            # The frozen executable cannot launch a Python -m child.
            self._load_in_process()
            return
        self._load_from_compact_subprocess()

    def _compact_value_by_id(self, achievement_id: int) -> dict[str, object] | None:
        achievement_id = int(achievement_id)
        if self._compact_external_index is None:
            try:
                payload = json.loads(
                    _achievement_compact_index_path(ACHIEVEMENT_COMPACT_CACHE).read_text(encoding="utf-8")
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                self._compact_external_index = {}
            else:
                raw_offsets = payload.get("offsets") if isinstance(payload, dict) else {}
                index: dict[int, tuple[int, int]] = {}
                if isinstance(raw_offsets, dict):
                    for raw_id, span in raw_offsets.items():
                        if not isinstance(span, list) or len(span) != 2:
                            continue
                        try:
                            index[int(raw_id)] = (int(span[0]), int(span[1]))
                        except (TypeError, ValueError):
                            continue
                self._compact_external_index = index

        span = self._compact_external_index.get(achievement_id)
        if span is not None:
            start, length = span
            if start >= 0 and length > 0:
                try:
                    with ACHIEVEMENT_COMPACT_CACHE.open("rb") as stream:
                        # Corrupt offsets must never trigger a negative seek
                        # or read(-1), which reads the *entire* compact file.
                        stream.seek(0, 2)
                        total = stream.tell()
                        if start <= total and length <= total - start:
                            stream.seek(start)
                            row = json.loads(stream.read(length))
                            value = row.get("value") if isinstance(row, dict) else None
                            if (isinstance(row, dict)
                                    and row.get("kind") == "achievement"
                                    and isinstance(value, dict)
                                    and type(value.get("id")) is int
                                    and value["id"] == achievement_id):
                                return value
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
            # A malformed sidecar span may be repaired asynchronously. Keep
            # a bounded-stream fallback rather than hiding a real achievement.

        # Non-retained Successes are compatibility/cross-link lookups only.
        # A retained Success with an invalid offset also needs the fallback.
        # Stream the compact file on this exceptional path without retaining
        # an extra global table.
        retained_target = achievement_id in getattr(
            self, "_compact_retained_set", frozenset()
        )
        try:
            with ACHIEVEMENT_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
                external = False
                for raw_line in stream:
                    line = raw_line.strip()
                    if not line:
                        continue
                    # External compatibility lookups used to decode every
                    # heavyweight retained summary just to reach the boundary.
                    # Keep the canonical marker parsed, but skip the rest.
                    if (not external and not retained_target
                            and '"external_start"' not in line):
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        continue
                    kind = str(row.get("kind") or "")
                    if kind == "external_start":
                        external = True
                        continue
                    # The retained section is relevant only if the retained
                    # offset was missing or corrupt; otherwise skip it.
                    if not external and not retained_target:
                        continue
                    if kind != "achievement":
                        continue
                    value = row.get("value")
                    if not isinstance(value, dict):
                        continue
                    if type(value.get("id")) is not int:
                        continue
                    if value["id"] == achievement_id:
                        return value
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        return None

    def _load_external_summary(self, achievement_id: int) -> Achievement | None:
        value = self._compact_value_by_id(int(achievement_id))
        return _achievement_from_dict(value) if value is not None else None

    def _summary_by_id(self, achievement_id: int) -> Achievement | None:
        achievement_id = int(achievement_id)
        summary = self._by_id.get(achievement_id)
        if summary is not None:
            return summary
        cached = self._compact_summary_cache.get(achievement_id)
        if cached is not None:
            self._compact_summary_cache.move_to_end(achievement_id)
            return cached
        summary = self._load_external_summary(achievement_id)
        if summary is None:
            return None
        self._compact_summary_cache[achievement_id] = summary
        self._compact_summary_cache.move_to_end(achievement_id)
        while len(self._compact_summary_cache) > 32:
            self._compact_summary_cache.popitem(last=False)
        return summary

    def compact_name_index(self) -> dict[str, tuple[int, str]]:
        """Stream the compact Success catalogue into a tiny normalized name/id index."""

        if not _achievement_compact_cache_valid(
            ACHIEVEMENT_COMPACT_CACHE,
            data_dir=self.data_dir,
        ):
            return {}
        result: dict[str, tuple[int, str]] = {}
        try:
            before = ACHIEVEMENT_COMPACT_CACHE.stat()
            generation = (
                before.st_size, before.st_mtime_ns,
                before.st_ctime_ns, before.st_ino,
            )
            with ACHIEVEMENT_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
                for raw_line in stream:
                    line = raw_line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict) or row.get("kind") != "achievement":
                        continue
                    value = row.get("value")
                    if not isinstance(value, dict):
                        continue
                    achievement_id = value.get("id")
                    name = str(value.get("name") or "").strip()
                    key = normalize_text(name)
                    if type(achievement_id) is int and key and key not in result:
                        result[key] = (achievement_id, name)
            after = ACHIEVEMENT_COMPACT_CACHE.stat()
            if (after.st_size, after.st_mtime_ns,
                    after.st_ctime_ns, after.st_ino) != generation:
                return {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}
        return result

    def retained_count(self) -> int:
        self._ensure_loaded()
        if self._compact_retained_ids:
            return len(self._compact_retained_ids)
        return sum(
            1
            for achievement in self._achievements
            if int(achievement.category_id) in {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
        )

    def count_by_category(self, category_id: int) -> int:
        self._ensure_loaded()
        if self._compact_category_ids:
            return len(self._compact_category_ids.get(int(category_id), ()))
        return len(self._by_category.get(int(category_id), ()))

    def catalogue_ids(self, category_id: int | None = None) -> tuple[int, ...]:
        """Return retained Success IDs without materializing Achievement objects."""

        self._ensure_loaded()
        if self._compact_retained_ids:
            if category_id is None:
                return tuple(self._compact_retained_ids)
            return tuple(self._compact_category_ids.get(int(category_id), ()))
        if category_id is None:
            return tuple(
                int(achievement.id)
                for achievement in self._achievements
                if self.is_retained(int(achievement.id))
            )
        return tuple(
            int(achievement.id)
            for achievement in self._by_category.get(int(category_id), ())
            if self.is_retained(int(achievement.id))
        )

    def catalogue_row_by_id(
        self,
        achievement_id: int,
    ) -> tuple[int, str, int | None, int] | None:
        """Return one primitive list row; rich Success objects stay cold."""

        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if (
            self._compact_retained_set
            and achievement_id in self._compact_retained_set
            and self._compact_external_index is not None
        ):
            span = self._compact_external_index.get(achievement_id)
            if span is not None:
                start, length = span
                if start >= 0 and length > 0:
                    try:
                        with ACHIEVEMENT_COMPACT_CACHE.open("rb") as stream:
                            # A broken offset must never cause read(-1) or a
                            # multi-megabyte read from the compact catalogue.
                            stream.seek(0, 2)
                            total = stream.tell()
                            if start <= total and length <= total - start:
                                stream.seek(start)
                                payload = json.loads(stream.read(length))
                                value = payload.get("value") if isinstance(payload, dict) else None
                                if (isinstance(payload, dict)
                                        and payload.get("kind") == "achievement"
                                        and isinstance(value, dict)
                                        and type(value.get("id")) is int
                                        and value["id"] == achievement_id):
                                    return (
                                        achievement_id,
                                        str(value.get("name") or ""),
                                        safe_int(value.get("level")),
                                        int(value.get("points") or 0),
                                    )
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        pass
                # A broken primitive offset is not an absent Success:
                # delegate to the existing summary fallback below.

        summary = self._summary_by_id(achievement_id)
        if summary is None or not self.is_retained(achievement_id):
            return None
        return (
            achievement_id,
            str(summary.name or ""),
            summary.level,
            int(summary.points or 0),
        )

    def load_retained(self) -> list[Achievement]:
        self._ensure_loaded()
        if self._compact_retained_ids:
            return [
                summary
                for achievement_id in self._compact_retained_ids
                for summary in (self._summary_by_id(achievement_id),)
                if summary is not None
            ]
        return super().load_retained()

    def get_by_category(self, category_id: int) -> list[Achievement]:
        self._ensure_loaded()
        if self._compact_category_ids:
            return [
                summary
                for achievement_id in self._compact_category_ids.get(int(category_id), ())
                for summary in (self._summary_by_id(achievement_id),)
                if summary is not None
            ]
        return list(self._by_category.get(int(category_id), ()))

    def _compact_achievement_ids_for_quest(self, quest_id: int) -> tuple[int, ...]:
        quest_id = int(quest_id)
        # Never reuse a positive or negative result from a replaced JSONL.
        try:
            first = ACHIEVEMENT_COMPACT_CACHE.stat()
            stamp = (first.st_size, first.st_mtime_ns, first.st_ctime_ns, first.st_ino)
        except OSError:
            self._compact_quest_link_cache.clear()
            self._compact_quest_link_stamp = None
            self._compact_quest_ids_by_quest = None
            self._compact_quest_map_stamp = None
            self._compact_quest_sidecar_stamp = None
            return ()
        if self._compact_quest_link_stamp != stamp:
            self._compact_quest_link_cache.clear()
            self._compact_quest_link_stamp = stamp
        if self._compact_quest_ids_by_quest is not None:
            try:
                sidecar = _achievement_compact_index_path(ACHIEVEMENT_COMPACT_CACHE)
                current = sidecar.stat()
                sidecar_stamp = (
                    current.st_size, current.st_mtime_ns,
                    current.st_ctime_ns, current.st_ino,
                )
            except OSError:
                sidecar_stamp = None
            if (
                getattr(self, "_compact_quest_map_stamp", None) == stamp
                and getattr(self, "_compact_quest_sidecar_stamp", None) == sidecar_stamp
                and sidecar_stamp is not None
            ):
                # Both files still belong to the generation validated on load.
                # No JSONL scan and no rich Achievement materialization.
                return self._compact_quest_ids_by_quest.get(quest_id, ())
            self._compact_quest_ids_by_quest = None
            self._compact_quest_map_stamp = None
            self._compact_quest_sidecar_stamp = None
        cached = self._compact_quest_link_cache.get(quest_id)
        if cached is not None:
            self._compact_quest_link_cache.move_to_end(quest_id)
            return cached

        matches: list[int] = []
        seen: set[int] = set()
        wanted_retained = set(self._compact_retained_ids)
        try:
            with ACHIEVEMENT_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
                meta = json.loads(stream.readline())
                if not isinstance(meta, dict) or meta.get("kind") != "meta":
                    raise ValueError("Success header missing")
                boundary = False
                for raw in stream:
                    line = raw.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("Success row invalid")
                    kind = row.get("kind")
                    if kind == "external_start":
                        boundary = True
                        break
                    if kind == "category":
                        continue
                    if kind != "achievement":
                        raise ValueError("Unexpected Success row")
                    value = row.get("value")
                    if not isinstance(value, dict) or type(value.get("id")) is not int:
                        raise ValueError("Success ID invalid")
                    ident = value["id"]
                    if ident in seen or ident not in wanted_retained:
                        raise ValueError("Success retained catalogue mismatch")
                    seen.add(ident)
                    linked = value.get("linked_quests")
                    if not isinstance(linked, list):
                        continue
                    for ref in linked:
                        if not isinstance(ref, dict):
                            continue
                        try:
                            linked_id = int(ref.get("entity_id"))
                        except (TypeError, ValueError):
                            continue
                        if linked_id == quest_id:
                            matches.append(ident)
                            break
                if not boundary or seen != wanted_retained:
                    raise ValueError("Success retained relation cache truncated")
            after = ACHIEVEMENT_COMPACT_CACHE.stat()
            if (after.st_size, after.st_mtime_ns,
                    after.st_ctime_ns, after.st_ino) != stamp:
                raise ValueError("Success cache replaced during relation lookup")
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            # A broken cache is NOT evidence that a quest has no Success.
            # Do not retain the false negative: next lookup can retry.
            logging.getLogger(__name__).warning(
                "Success relations unavailable; next lookup will retry: %s", exc,
            )
            self._compact_quest_link_cache.clear()
            self._compact_quest_link_stamp = None
            return ()

        result = tuple(matches)
        self._compact_quest_link_cache[quest_id] = result
        self._compact_quest_link_cache.move_to_end(quest_id)
        while len(self._compact_quest_link_cache) > 24:
            self._compact_quest_link_cache.popitem(last=False)
        return result

    def get_by_quest(self, quest_id: int) -> list[Achievement]:
        self._ensure_loaded()
        if self._compact_retained_ids:
            return [
                summary
                for achievement_id in self._compact_achievement_ids_for_quest(int(quest_id))
                for summary in (self._summary_by_id(achievement_id),)
                if summary is not None
            ]
        return list(self._by_quest.get(int(quest_id), ()))

    def search(self, query: str, limit: int | None = None) -> list[Achievement]:
        self._ensure_loaded()
        if not self._compact_retained_ids:
            return super().search(query, limit=limit)
        needle = normalize_text(query)
        tokens = [token for token in needle.split("_") if token]
        results: list[Achievement] = []
        for achievement_id in self._compact_retained_ids:
            summary = self._summary_by_id(achievement_id)
            if summary is None:
                continue
            if tokens and not all(token in summary.search_text for token in tokens):
                continue
            results.append(summary)
            if limit is not None and len(results) >= int(limit):
                break
        return results

    def iter_progress_achievement_ids(self):
        """Iterate retained Success IDs without materializing catalogue rows."""

        self._ensure_loaded()
        if self._compact_retained_ids:
            return iter(self._compact_retained_ids)
        return iter(
            int(achievement.id)
            for achievement in self._achievements
            if self.is_retained(int(achievement.id))
        )

    def progress_row_by_id(
        self,
        achievement_id: int,
    ) -> tuple[int, str, tuple[tuple[object, ...], ...]] | None:
        """Load one primitive progress row directly from the compact JSONL."""

        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if (
            self._compact_retained_set
            and achievement_id in self._compact_retained_set
            and self._compact_external_index is not None
        ):
            span = self._compact_external_index.get(achievement_id)
            if span is None:
                return None
            start, length = span
            try:
                with ACHIEVEMENT_COMPACT_CACHE.open("rb") as stream:
                    stream.seek(start)
                    payload = json.loads(stream.read(length))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return None
            value = payload.get("value") if isinstance(payload, dict) else None
            if not isinstance(value, dict):
                return None
            return (
                achievement_id,
                str(value.get("category_name") or ""),
                _progress_objectives_from_rows(value.get("progress_objectives")),
            )

        summary = self.get_by_id(achievement_id)
        if summary is None or not self.is_retained(achievement_id):
            return None
        return (
            achievement_id,
            str(summary.category_name or ""),
            tuple(self.progress_objectives_for(achievement_id)),
        )

    def progress_catalogue(self) -> tuple[tuple[int, str, tuple[tuple[object, ...], ...]], ...]:
        """Primitive progress rows; no Achievement graph enters the resident heap."""

        self._ensure_loaded()
        if not self._compact_retained_ids or self._compact_external_index is None:
            return tuple(
                (
                    int(achievement.id),
                    str(achievement.category_name or ""),
                    tuple(self.progress_objectives_for(int(achievement.id))),
                )
                for achievement in self.load_retained()
            )

        rows: list[tuple[int, str, tuple[tuple[object, ...], ...]]] = []
        try:
            with ACHIEVEMENT_COMPACT_CACHE.open("rb") as stream:
                for achievement_id in self._compact_retained_ids:
                    span = self._compact_external_index.get(int(achievement_id))
                    if span is None:
                        continue
                    start, length = span
                    stream.seek(start)
                    payload = json.loads(stream.read(length))
                    value = payload.get("value") if isinstance(payload, dict) else None
                    if not isinstance(value, dict):
                        continue
                    rows.append(
                        (
                            int(achievement_id),
                            str(value.get("category_name") or ""),
                            _progress_objectives_from_rows(value.get("progress_objectives")),
                        )
                    )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return ()
        return tuple(rows)

    def load_runtime(self) -> None:
        """Warm the catalogue and prepare details for in-process runtimes."""

        self._ensure_loaded()
        # The installed Windows EXE runs Success detail lookups in-process.
        # Unlike the development subprocess path, that requires the detail
        # source indexes to have been prepared before a Qt click invokes
        # get_detail_by_id(). Do it in the existing background stage, not
        # synchronously inside AchievementsView.show_achievement().
        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if bool(getattr(sys, "frozen", False)) or current_data_dir != default_data_dir:
            self.prepare_detail_sources()

    def _compat_achievement(self, summary: Achievement) -> Achievement:
        achievement_id = int(summary.id)
        objectives: list[AchievementObjective] = []
        for order, row in enumerate(self.progress_objectives_for(achievement_id), 1):
            if len(row) != 5:
                continue
            objective_id, objective_type, criterion, text, raw_refs = row
            refs = tuple(
                EntityRef(str(entity_type or ""), int(entity_id), "")
                for entity_type, entity_id in tuple(raw_refs or ())
            )
            objectives.append(
                AchievementObjective(
                    id=int(objective_id),
                    achievement_id=achievement_id,
                    text=str(text or ""),
                    criterion=str(criterion or ""),
                    order=order,
                    objective_type=str(objective_type or ""),
                    entity_ref=(refs[0] if refs else None),
                    entity_refs=refs,
                )
            )
        points_reward = Reward(
            kind="achievement_points",
            name="Points de succès",
            quantity=max(0, int(summary.points or 0)),
            source_id=achievement_id,
        )
        return replace(
            summary,
            objectives=tuple(objectives),
            rewards=(points_reward,),
        )

    def load_all(self) -> list[Achievement]:
        self._ensure_loaded()
        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if bool(getattr(sys, "frozen", False)) or current_data_dir != default_data_dir:
            self.prepare_detail_sources()
            return [self._compat_achievement(summary) for summary in self._achievements]

        if not _achievement_compact_cache_valid(
            ACHIEVEMENT_COMPACT_CACHE,
            data_dir=self.data_dir,
        ):
            return [self._compat_achievement(summary) for summary in self._achievements]

        result: list[Achievement] = []
        with ACHIEVEMENT_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                value = row.get("value") if isinstance(row, dict) else None
                if row.get("kind") != "achievement" or not isinstance(value, dict):
                    continue
                summary = _achievement_from_dict(value)
                raw_progress = value.get("progress_objectives")
                if isinstance(raw_progress, list) and raw_progress:
                    encoded = json.dumps(
                        raw_progress,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    previous = self._progress_objectives.get(int(summary.id))
                    self._progress_objectives[int(summary.id)] = encoded
                    try:
                        result.append(self._compat_achievement(summary))
                    finally:
                        if previous is None and int(summary.id) not in self._by_id:
                            self._progress_objectives.pop(int(summary.id), None)
                        elif previous is not None:
                            self._progress_objectives[int(summary.id)] = previous
                else:
                    result.append(self._compat_achievement(summary))
        return result

    def progress_objectives_for(self, achievement_id: int) -> tuple[tuple[object, ...], ...]:
        self._ensure_loaded()
        encoded = self._progress_objectives.get(int(achievement_id), "")
        if encoded:
            try:
                payload = json.loads(encoded)
            except (TypeError, ValueError, json.JSONDecodeError):
                return ()
            return _progress_objectives_from_rows(payload)
        value = self._compact_value_by_id(int(achievement_id))
        if value is None:
            return ()
        return _progress_objectives_from_rows(value.get("progress_objectives"))

    def get_by_id(self, achievement_id: int) -> Achievement | None:
        """Return one lightweight compatibility object without warming rich sources."""

        self._ensure_loaded()
        achievement_id = int(achievement_id)
        summary = self._summary_by_id(achievement_id)
        if summary is None:
            return None
        if self._compat_cache_id == achievement_id and self._compat_cache is not None:
            return self._compat_cache
        compatible = self._compat_achievement(summary)
        self._compat_cache_id = achievement_id
        self._compat_cache = compatible
        return compatible

    def is_retained(self, achievement_id: int) -> bool:
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._compact_retained_set:
            return achievement_id in self._compact_retained_set
        summary = self._by_id.get(achievement_id)
        return bool(
            summary is not None
            and int(summary.category_id) in {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
        )

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
            raise RuntimeError(
                "Sources de détail Succès non préparées ; load_all() doit être exécuté "
                "hors du thread UI avant l'ouverture d'un détail."
            )
        self._entries = self._sources.mapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            required=True,
        )
        try:
            return BaseAchievementProvider.get_detail_by_id(self, achievement_id)
        finally:
            self._reset_sources()

    def _remember_rich_detail(
        self, achievement_id: int, detail: Achievement,
        old_id: int | None, old_detail: Achievement | None,
    ) -> None:
        """Retain only the last few details; never the whole rich catalogue."""
        if old_detail is not None and old_id is not None and old_id != achievement_id:
            self._recent_rich_details[old_id] = old_detail
            self._recent_rich_details.move_to_end(old_id)
        self._recent_rich_details.pop(achievement_id, None)
        while len(self._recent_rich_details) > 2:
            self._recent_rich_details.popitem(last=False)
        self._detail_cache_id = achievement_id
        self._detail_cache = detail

    def _reuse_recent_rich_detail(self, achievement_id: int) -> Achievement | None:
        cached = self._recent_rich_details.pop(achievement_id, None)
        if cached is None:
            return None
        old_id, old_detail = self._detail_cache_id, self._detail_cache
        self._remember_rich_detail(achievement_id, cached, old_id, old_detail)
        self._last_detail_cache_source = "recent"
        self._last_detail_subprocess_used = False
        self._last_detail_subprocess_ms = 0.0
        self._last_detail_decode_ms = 0.0
        self._last_detail_ms = 0.0
        self._last_detail_thread_name = current_thread().name
        return cached

    @property
    def last_cold_detail_breakdown_ms(self) -> dict[str, object]:
        """Last successful cold detail cost, independent of subsequent cache hits."""
        return dict(self._last_cold_detail_breakdown)

    @property
    def last_detail_breakdown_ms(self) -> dict[str, object]:
        """Identify cold Success detail blocking work, without importing a profiler."""
        return {
            "thread": self._last_detail_thread_name,
            "total_ms": self._last_detail_ms,
            "synchronous_subprocess_ms": getattr(self, "_last_detail_subprocess_ms", 0.0),
            "decode_ms": getattr(self, "_last_detail_decode_ms", 0.0),
            "subprocess_path_used": bool(getattr(self, "_last_detail_subprocess_used", False)),
            "cache_source": self._last_detail_cache_source,
            "recent_cache_entries": len(self._recent_rich_details),
        }

    def get_detail_by_id(self, achievement_id: int):
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            self._last_detail_cache_source = "hot"
            self._last_detail_subprocess_used = False
            self._last_detail_subprocess_ms = 0.0
            self._last_detail_decode_ms = 0.0
            self._last_detail_ms = 0.0
            self._last_detail_thread_name = current_thread().name
            return self._detail_cache
        recent = self._reuse_recent_rich_detail(achievement_id)
        if recent is not None:
            return recent
        old_id, old_detail = self._detail_cache_id, self._detail_cache
        self._last_detail_cache_source = "cold"
        self._last_cold_detail_breakdown = {}

        default_data_dir = Path(RAW_QUEST_DATA_DIR).resolve(strict=False)
        current_data_dir = Path(self.data_dir).resolve(strict=False)
        if (
            not bool(getattr(sys, "frozen", False))
            and current_data_dir == default_data_dir
            and _DUMP_DETAIL_FLAG not in sys.argv
        ):
            # Doctor must distinguish the expensive disposable worker from
            # JSON decoding instead of reporting only an opaque Qt stall.
            # This path is intentionally synchronous until an exact-SHA
            # Graphify impact review authorizes an async UI lifecycle change.
            started = perf_counter()
            self._last_detail_subprocess_used = True
            self._last_detail_decode_ms = 0.0
            try:
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
                    env=_utf8_subprocess_env(),
                    timeout=90,
                    check=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
                )
            finally:
                self._last_detail_subprocess_ms = round(
                    (perf_counter() - started) * 1000.0, 3,
                )
                self._last_detail_ms = self._last_detail_subprocess_ms
                self._last_detail_thread_name = current_thread().name

            decode_started = perf_counter()
            try:
                lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
                if not lines:
                    return None
                payload = json.loads(lines[-1])
                if not isinstance(payload, dict):
                    return None
                detail = _achievement_from_dict(payload)
                self._remember_rich_detail(
                    achievement_id, detail, old_id, old_detail,
                )
                return detail
            finally:
                self._last_detail_decode_ms = round(
                    (perf_counter() - decode_started) * 1000.0, 3,
                )
                self._last_detail_ms = round((perf_counter() - started) * 1000.0, 3)
                if self._detail_cache_id == achievement_id and self._detail_cache is not None:
                    self._last_cold_detail_breakdown = {
                        "achievement_id": achievement_id,
                        "status": "OBSERVED",
                        "thread": self._last_detail_thread_name,
                        "total_ms": self._last_detail_ms,
                        "synchronous_subprocess_ms": self._last_detail_subprocess_ms,
                        "decode_ms": self._last_detail_decode_ms,
                        "subprocess_path_used": True,
                    }

        self._last_detail_subprocess_used = False
        self._last_detail_subprocess_ms = 0.0
        self._last_detail_decode_ms = 0.0
        started = perf_counter()
        detail = self._get_detail_in_process(achievement_id)
        self._last_detail_ms = round((perf_counter() - started) * 1000.0, 3)
        self._last_detail_thread_name = current_thread().name
        if detail is not None:
            self._remember_rich_detail(achievement_id, detail, old_id, old_detail)
            self._last_cold_detail_breakdown = {
                "achievement_id": achievement_id,
                "status": "OBSERVED",
                "thread": self._last_detail_thread_name,
                "total_ms": self._last_detail_ms,
                "synchronous_subprocess_ms": 0.0,
                "decode_ms": 0.0,
                "subprocess_path_used": False,
            }
        return detail

    def get_linked_quests(self, achievement_id: int):
        self._ensure_loaded()
        achievement = self._summary_by_id(int(achievement_id))
        return list(achievement.linked_quests) if achievement is not None else []

    def get_linked_monsters(self, achievement_id: int):
        self._ensure_loaded()
        achievement = self._summary_by_id(int(achievement_id))
        return list(achievement.linked_monsters) if achievement is not None else []

    def get_linked_dungeons(self, achievement_id: int):
        self._ensure_loaded()
        achievement = self._summary_by_id(int(achievement_id))
        return list(achievement.linked_dungeons) if achievement is not None else []

    def get_linked_achievements(self, achievement_id: int):
        self._ensure_loaded()
        achievement = self._summary_by_id(int(achievement_id))
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


def _unique_cache_temporary_path(target: Path) -> Path:
    """Avoid collisions when multiple Atlas instances build the same cache.

    Each writer publishes only a completed file via atomic replace. Temporary
    files must NEVER have a fixed name shared by parallel processes.
    """
    target = Path(target)
    return target.with_name(f".{target.name}.{os.getpid()}.{uuid4().hex}.tmp")


def _build_compact_cache(path: Path, force_rebuild: bool = False) -> int:
    """Build once per shared cache path; repair invalid sidecars under the lock."""
    path = Path(path)
    with _achievement_compact_write_lock(path):
        # A valid JSONL header and positive count do not prove the companion
        # offsets index is usable. The preload can require a repair explicitly.
        if not force_rebuild and _achievement_compact_cache_valid(path, data_dir=RAW_QUEST_DATA_DIR):
            try:
                index_payload = json.loads(
                    _achievement_compact_index_path(path).read_text(encoding="utf-8")
                )
                count = index_payload.get("achievement_count")
                retained = index_payload.get("retained_count")
                retained_ids = index_payload.get("retained_ids")
                offsets = index_payload.get("offsets")
                with path.open("r", encoding="utf-8") as stream:
                    source_meta = json.loads(stream.readline())
                source_marker = source_meta.get("cache_generation")
                index_marker = index_payload.get("cache_generation")
                same_generation = (
                    (source_marker is None and index_marker is None)
                    or (isinstance(source_marker, str) and bool(source_marker)
                        and source_marker == index_marker)
                )
                if (same_generation
                        and type(count) is int and count > 0
                        and type(retained) is int and 0 < retained <= count
                        and isinstance(retained_ids, list)
                        and len(retained_ids) == retained
                        and all(type(value) is int for value in retained_ids)
                        and len(set(retained_ids)) == retained
                        and isinstance(offsets, dict)
                        and len(offsets) == retained
                        and set(offsets) == {str(value) for value in retained_ids}
                        and all(
                            isinstance(span, list) and len(span) == 2
                            and type(span[0]) is int and span[0] >= 0
                            and type(span[1]) is int and span[1] > 0
                            for span in offsets.values()
                        )):
                    print(json.dumps(
                        {"achievement_count": count, "path": str(path)},
                        ensure_ascii=False, separators=(",", ":"),
                    ))
                    return 0
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        return _build_compact_cache_unlocked(path)


def _build_compact_cache_unlocked(path: Path) -> int:
    source_generation = _achievement_compact_source_signature(RAW_QUEST_DATA_DIR)
    provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
    provider._load_disposable_worker_fast()
    if _achievement_compact_source_signature(RAW_QUEST_DATA_DIR) != source_generation:
        raise RuntimeError("Success sources changed during compact-cache build")
    retained_ids = {int(value) for value in RETAINED_TOP_CATEGORY_IDS}
    path = Path(path)
    index_path = _achievement_compact_index_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _unique_cache_temporary_path(path)
    temp_index = _unique_cache_temporary_path(index_path)
    generation = uuid4().hex
    offsets: dict[str, list[int]] = {}

    def line_bytes(payload: dict[str, object]) -> bytes:
        return (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    with temp_path.open("wb") as stream:
        stream.write(
            line_bytes(
                {
                    "kind": "meta",
                    "schema_version": _ACHIEVEMENT_COMPACT_SCHEMA,
                    "cache_generation": generation,
                    "source_signature": source_generation,
                }
            )
        )
        for category in provider._categories.values():
            stream.write(
                line_bytes({"kind": "category", "value": asdict(category)})
            )

        retained = [
            achievement
            for achievement in provider._achievements
            if int(achievement.category_id) in retained_ids
        ]
        external = [
            achievement
            for achievement in provider._achievements
            if int(achievement.category_id) not in retained_ids
        ]
        by_category_ids: dict[int, list[int]] = defaultdict(list)
        by_quest_ids: dict[int, list[int]] = defaultdict(list)
        for achievement in retained:
            by_category_ids[int(achievement.category_id)].append(int(achievement.id))
            if achievement.subcategory_id is not None:
                by_category_ids[int(achievement.subcategory_id)].append(int(achievement.id))
            # Match the canonical scan: malformed links are ignored, and a
            # repeated quest reference must not duplicate an achievement.
            seen_quests: set[int] = set()
            for ref in achievement.linked_quests:
                try:
                    quest_id = int(ref.entity_id)
                except (AttributeError, TypeError, ValueError):
                    continue
                if quest_id in seen_quests:
                    continue
                seen_quests.add(quest_id)
                by_quest_ids[quest_id].append(int(achievement.id))
        for achievement in retained:
            payload = {
                "kind": "achievement",
                "value": _compact_achievement_dict(achievement),
            }
            raw = line_bytes(payload)
            start = stream.tell()
            stream.write(raw)
            # The resident index intentionally covers only retained Successes.
            # External summaries remain in the JSONL and are scanned on-demand;
            # keeping thousands of external offsets in the startup JSON made a
            # short-lived allocation become permanent RSS high-water.
            offsets[str(achievement.id)] = [start, len(raw)]

        stream.write(line_bytes({"kind": "external_start"}))
        for achievement in external:
            payload = {
                "kind": "achievement",
                "value": _compact_achievement_dict(achievement),
            }
            stream.write(line_bytes(payload))

    temp_index.write_text(
        json.dumps(
            {
                "schema_version": _ACHIEVEMENT_COMPACT_SCHEMA,
                "achievement_count": len(provider._achievements),
                "retained_count": len(retained),
                "cache_generation": generation,
                "retained_ids": [int(achievement.id) for achievement in retained],
                "by_category": {
                    str(category_id): list(dict.fromkeys(achievement_ids))
                    for category_id, achievement_ids in sorted(by_category_ids.items())
                },
                "offsets": offsets,
                "by_quest": {
                    str(quest_id): ids
                    for quest_id, ids in sorted(by_quest_ids.items())
                },
                "by_quest_ref_count": sum(len(ids) for ids in by_quest_ids.values()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    if _achievement_compact_source_signature(RAW_QUEST_DATA_DIR) != source_generation:
        # Do not sign old data as current after a concurrent source update.
        # Neither half of the JSONL/sidecar pair may be published.
        temp_path.unlink(missing_ok=True)
        temp_index.unlink(missing_ok=True)
        raise RuntimeError("Success sources changed before compact-cache publication")
    temp_path.replace(path)
    temp_index.replace(index_path)
    print(
        json.dumps(
            {
                "achievement_count": len(provider._achievements),
                "retained_count": len(retained),
                "path": str(path),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


def _dump_default_detail(achievement_id: int) -> int:
    provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
    # This is a disposable child process, just like the compact-cache builder.
    # Reuse its indexed one-pass loader instead of scanning text IDs and then
    # rebuilding the entire rich catalogue through _load_in_process().
    # The detail still comes from the canonical source-backed renderer below.
    provider._load_disposable_worker_fast()
    provider._loaded = True
    provider.prepare_detail_sources()
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


def _ensure_compact_cache_cli() -> int:
    if _achievement_compact_cache_valid(ACHIEVEMENT_COMPACT_CACHE, data_dir=RAW_QUEST_DATA_DIR):
        try:
            payload = json.loads(_achievement_compact_index_path(ACHIEVEMENT_COMPACT_CACHE).read_text(encoding="utf-8"))
            count = max(0, int(payload.get("achievement_count") or 0))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            count = 0
        print(json.dumps({"achievement_count": count, "path": str(ACHIEVEMENT_COMPACT_CACHE)}, ensure_ascii=False, separators=(",", ":")))
        return 0
    return _build_compact_cache(ACHIEVEMENT_COMPACT_CACHE)


if __name__ == "__main__" and _ENSURE_COMPACT_CACHE_FLAG in sys.argv:
    raise SystemExit(_ensure_compact_cache_cli())


if __name__ == "__main__" and _BUILD_COMPACT_CACHE_FLAG in sys.argv:
    try:
        compact_path = Path(sys.argv[sys.argv.index(_BUILD_COMPACT_CACHE_FLAG) + 1])
    except (ValueError, IndexError):
        raise SystemExit(2)
    raise SystemExit(_build_compact_cache(compact_path))

if __name__ == "__main__" and _DUMP_COMPACT_FLAG in sys.argv:
    raise SystemExit(_dump_compact_default_catalogue())

if __name__ == "__main__" and _DUMP_DETAIL_FLAG in sys.argv:
    try:
        detail_id = int(sys.argv[sys.argv.index(_DUMP_DETAIL_FLAG) + 1])
    except (ValueError, IndexError):
        raise SystemExit(2)
    raise SystemExit(_dump_default_detail(detail_id))


__all__ = [
    "ACHIEVEMENT_COMPACT_CACHE",
    "MemoryBoundAchievementProvider",
    "ensure_achievement_compact_cache",
]
