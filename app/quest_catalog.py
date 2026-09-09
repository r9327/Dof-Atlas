from __future__ import annotations

import gzip
import html
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.constants import (
    CLIENT_INDEX_JSON,
    DATA_DIR,
    KEY_SESSION_ORDER,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
    QUEST_PROGRESS_FILE,
    RAW_QUEST_DATA_DIR,
    ROOT_DIR,
)
from app.core.json_store import read_json_resilient, write_json_atomic
from app.quest_source_index import build_image_index


SENTINEL_COORD = -2147483648
COMBAT_OBJECTIVE_TYPES = {6, 7}
QUEST_CATALOG_CACHE_VERSION = 2
QUEST_CATALOG_CACHE_PATH = ROOT_DIR / ".cache" / "dofus_atlas" / "quest_catalog_v2.json.gz"
QUEST_CATALOG_LEGACY_CACHE_PATH = ROOT_DIR / ".cache" / "dofus_atlas" / "quest_catalog_v1.pkl"
QUEST_CATALOG_SOURCE_FILES = (
    ("language", "languages/fr.json"),
    ("quests", "quests.json"),
    ("quest_steps", "quest_steps.json"),
    ("quest_objectives", "quest_objectives.json"),
    ("quest_step_rewards", "quest_step_rewards.json"),
    ("achievements", "achievements.json"),
    ("achievement_objectives", "achievement_objectives.json"),
    ("achievement_categories", "achievement_categories.json"),
    ("quest_categories", "quest_categories.json"),
    ("quest_objective_types", "quest_objective_types.json"),
    ("items", "items.json"),
    ("jobs", "jobs.json"),
    ("spells", "spells.json"),
    ("titles", "titles.json"),
    ("emoticons", "emoticons.json"),
    ("monsters", "monsters.json"),
    ("npcs", "npcs.json"),
    ("areas", "areas.json"),
    ("subareas", "subareas.json"),
    ("maps_information", "maps_information.json"),
    ("char_xp_mappings", "char_xp_mappings.json"),
)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text.casefold()).strip("_")


def array_value(value: Any) -> list[Any]:
    if isinstance(value, dict):
        inner = value.get("Array", [])
        return inner if isinstance(inner, list) else []
    return value if isinstance(value, list) else []


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def doduda_rows(path: Path) -> dict[int, dict[str, Any]]:
    payload = read_json_file(path, {})
    refs = payload.get("references", {}).get("RefIds", []) if isinstance(payload, dict) else []
    rows: dict[int, dict[str, Any]] = {}
    for ref in refs:
        data = ref.get("data") if isinstance(ref, dict) else None
        if not isinstance(data, dict):
            continue
        try:
            ident = int(data.get("id"))
        except (TypeError, ValueError):
            continue
        rows[ident] = data
    return rows


def doduda_keyed_rows(path: Path) -> dict[int, dict[str, Any]]:
    payload = read_json_file(path, {})
    if not isinstance(payload, dict):
        return {}
    objects = payload.get("objectsById")
    if not isinstance(objects, dict):
        return {}
    keys = array_value(objects.get("m_keys"))
    values = array_value(objects.get("m_values"))
    refs = payload.get("references", {}).get("RefIds", [])
    refs_by_rid = {
        safe_int(ref.get("rid")): ref.get("data")
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("data"), dict)
    }
    rows: dict[int, dict[str, Any]] = {}
    for key, value in zip(keys, values):
        ident = safe_int(key)
        rid = safe_int(value.get("rid")) if isinstance(value, dict) else None
        row = refs_by_rid.get(rid)
        if ident is not None and isinstance(row, dict):
            rows[ident] = row
    return rows


def text_for(entries: dict[str, Any], ident: Any, fallback: str = "") -> str:
    if ident in (None, "", -1):
        return fallback
    value = entries.get(str(ident), fallback)
    if value is None:
        return fallback
    text = html.unescape(str(value))
    return re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()


def localized_name(row: dict[str, Any] | None, entries: dict[str, Any], fallback: str = "") -> str:
    if not isinstance(row, dict):
        return fallback
    raw_name = row.get("name")
    if isinstance(raw_name, dict):
        for key in ("fr", "en", "name"):
            text = raw_name.get(key)
            if text:
                return str(text)
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    return text_for(entries, row.get("nameId"), fallback)


@dataclass(slots=True)
class QuestReward:
    name: str
    quantity: int = 1
    image_path: str = ""
    item_id: int | None = None
    kind: str = "item"


@dataclass(slots=True)
class QuestObjective:
    id: int
    text: str
    type_id: int
    map_label: str = ""
    zone: str = ""
    image_path: str = ""
    image_label: str = ""
    item_id: int | None = None
    item_quantity: int = 0
    is_combat: bool = False


@dataclass(slots=True)
class QuestStep:
    id: int
    name: str
    description: str
    objectives: list[QuestObjective] = field(default_factory=list)
    rewards: list[QuestReward] = field(default_factory=list)


@dataclass(slots=True)
class QuestSolutionBlock:
    order: int
    block_type: str
    content: str = ""
    position: str = ""
    image_path: str = ""
    caption: str = ""
    source_url: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QuestRecord:
    id: int
    name: str
    category: str
    level_min: int
    level_max: int
    start_criterion: str
    zones: list[str] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    steps: list[QuestStep] = field(default_factory=list)
    source_solution_steps: list[QuestStep] = field(default_factory=list)
    solution_blocks: list[QuestSolutionBlock] = field(default_factory=list)
    source_info: dict[str, Any] = field(default_factory=dict)
    rewards: list[QuestReward] = field(default_factory=list)

    @property
    def search_text(self) -> str:
        values = [
            self.name,
            self.category,
            " ".join(self.zones),
            " ".join(self.achievements),
            " ".join(self.prerequisites),
        ]
        return normalize_text(" ".join(values))


@dataclass(slots=True)
class QuestCharacter:
    key: str
    label: str
    slot: int
    connected: bool = False


@dataclass(frozen=True, slots=True)
class QuestAchievementSeries:
    """Ordered quest suite exposed by one local achievement."""

    achievement_id: int
    name: str
    category: str
    order: int
    quest_ids: tuple[int, ...]


class QuestCatalog:
    def __init__(
        self,
        quests: list[QuestRecord],
        loaded_from: Path | None = None,
        errors: list[str] | None = None,
        achievement_series: tuple[QuestAchievementSeries, ...] = (),
    ):
        self.quests = quests
        self.loaded_from = loaded_from
        self.errors = errors or []
        self.by_id = {quest.id: quest for quest in quests}
        self.achievement_series = tuple(achievement_series)

    @classmethod
    def load(
        cls,
        data_dir: Path = RAW_QUEST_DATA_DIR,
    ) -> "QuestCatalog":
        if _is_default_quest_data_dir(data_dir):
            from app.quest_catalog_details import load_lazy_catalog
            return load_lazy_catalog(data_dir)
        return cls._load_source(data_dir)

    @classmethod
    def _load_source(
        cls, data_dir: Path, *, quest_ids: set[int] | None = None, sources=None,
        include_enrichment: bool = True,
    ) -> "QuestCatalog":
        """Compile requested source records; the UI index never calls this."""
        cached = read_quest_catalog_cache(data_dir) if quest_ids is None else None
        if cached is not None:
            return cached

        errors: list[str] = []
        row_loader = sources.rows if sources is not None else doduda_rows
        language = ({"entries": sources.mapping(data_dir / "languages" / "fr.json", "entries")}
                    if sources is not None else read_json_file(data_dir / "languages" / "fr.json", {"entries": {}}))
        entries = language.get("entries", {}) if isinstance(language, dict) else {}
        if not isinstance(entries, Mapping):
            entries = {}

        quests = row_loader(data_dir / "quests.json")
        quest_steps = row_loader(data_dir / "quest_steps.json")
        objectives = row_loader(data_dir / "quest_objectives.json")
        rewards = row_loader(data_dir / "quest_step_rewards.json")
        achievements = row_loader(data_dir / "achievements.json")
        achievement_objectives = row_loader(data_dir / "achievement_objectives.json")
        achievement_categories = row_loader(data_dir / "achievement_categories.json")
        categories = row_loader(data_dir / "quest_categories.json")
        objective_types = row_loader(data_dir / "quest_objective_types.json")
        items = row_loader(data_dir / "items.json")
        jobs = row_loader(data_dir / "jobs.json")
        spells = row_loader(data_dir / "spells.json")
        titles = row_loader(data_dir / "titles.json")
        emoticons = row_loader(data_dir / "emoticons.json")
        monsters = row_loader(data_dir / "monsters.json")
        npcs = row_loader(data_dir / "npcs.json")
        areas = row_loader(data_dir / "areas.json")
        subareas = row_loader(data_dir / "subareas.json")
        maps = row_loader(data_dir / "maps_information.json")
        image_index = (sources.image_index(DATA_DIR / "images") if sources is not None
                       else build_image_index(DATA_DIR / "images"))
        character_xp = load_character_xp_table(data_dir)

        category_names = {
            ident: localized_name(row, entries, f"Categorie {ident}")
            for ident, row in categories.items()
        }
        objective_type_names = {
            ident: text_for(entries, row.get("nameId"), f"Objectif {ident}")
            for ident, row in objective_types.items()
        }
        context = sources.context if sources is not None else {}
        if not context:
            achievement_names = {
                ident: localized_name(row, entries, f"Succes {ident}")
                for ident, row in achievements.items()
            }
            quest_names = {
                ident: localized_name(row, entries, f"Quete {ident}")
                for ident, row in quests.items()
            }

            quest_to_achievements = achievements_by_quest(achievement_objectives, achievement_names)
            context.update(achievement_names=achievement_names, quest_names=quest_names,
                           quest_to_achievements=quest_to_achievements)
        achievement_names = context['achievement_names']
        quest_names = context['quest_names']
        quest_to_achievements = context['quest_to_achievements']
        objectives_by_step: dict[int, list[dict[str, Any]]] = defaultdict(list)
        selected_steps = {int(step) for quest_id in (quest_ids or ())
                          for step in array_value(quests[quest_id].get("stepIds"))}
        objective_rows = (sources.objectives_for_steps(data_dir / "quest_objectives.json", selected_steps)
                          if sources is not None and quest_ids is not None else objectives.values())
        for objective in objective_rows:
            try:
                objectives_by_step[int(objective.get("stepId"))].append(objective)
            except (TypeError, ValueError):
                continue
        rewards_by_id = rewards

        records: list[QuestRecord] = []
        quest_rows = ((key, quests[key]) for key in quest_ids) if quest_ids is not None else quests.items()
        for quest_id, quest in quest_rows:
            name = quest_names.get(quest_id) or f"Quete {quest_id}"
            steps: list[QuestStep] = []
            quest_rewards: list[QuestReward] = []
            zones: list[str] = []
            combat_count = 0
            for start in array_value(quest.get("startPosition")):
                if isinstance(start, dict):
                    zone = zone_for_map(start.get("mapId"), maps, subareas, areas, entries)
                    if zone:
                        add_unique(zones, zone)
            for step_id in array_value(quest.get("stepIds")):
                try:
                    step = quest_steps.get(int(step_id))
                except (TypeError, ValueError):
                    step = None
                if not step:
                    continue
                step_objectives: list[QuestObjective] = []
                for objective in objectives_by_step.get(int(step_id), []):
                    resolved = resolve_objective(
                        objective,
                        objective_type_names,
                        entries,
                        items,
                        monsters,
                        npcs,
                        maps,
                        subareas,
                        areas,
                        image_index,
                    )
                    step_objectives.append(resolved)
                    if resolved.zone:
                        add_unique(zones, resolved.zone)
                    if resolved.is_combat:
                        combat_count += 1
                reward_rows = []
                for reward_id in array_value(step.get("rewardsIds")):
                    ident = safe_int(reward_id)
                    if ident is not None and rewards_by_id.get(ident):
                        reward_rows.append(rewards_by_id[ident])
                step_rewards = [
                    reward
                    for reward_row in select_reward_rows(reward_rows, safe_int(quest.get("levelMin")) or 0)
                    for reward in resolve_step_rewards(
                        reward_row,
                        entries,
                        items,
                        jobs,
                        spells,
                        titles,
                        emoticons,
                        image_index,
                        character_xp,
                        safe_int(quest.get("levelMin")) or 0,
                    )
                ]
                quest_rewards.extend(step_rewards)
                steps.append(
                    QuestStep(
                        id=int(step_id),
                        name=text_for(entries, step.get("nameId"), f"Etape {step_id}"),
                        description=text_for(entries, step.get("descriptionId"), ""),
                        objectives=step_objectives,
                        rewards=step_rewards,
                    )
                )

            info = quest_info(quest, combat_count)
            prerequisites = criteria_to_lines(str(quest.get("startCriterion") or ""), quest_names, achievement_names)
            records.append(
                QuestRecord(
                    id=quest_id,
                    name=name,
                    category=category_names.get(safe_int(quest.get("categoryId")) or -1, ""),
                    level_min=int(quest.get("levelMin") or 0),
                    level_max=int(quest.get("levelMax") or 0),
                    start_criterion=str(quest.get("startCriterion") or ""),
                    zones=zones,
                    achievements=quest_to_achievements.get(quest_id, []),
                    prerequisites=prerequisites,
                    info=info,
                    steps=steps,
                    rewards=dedupe_rewards(quest_rewards),
                )
            )

        enrichment = ({"quests": {str(quest_id): sources.mapping(
            DATA_DIR / "encyclopedia" / "quests" / "quests_enriched.json", "quests").get(str(quest_id), {})
            for quest_id in quest_ids}} if include_enrichment and sources is not None and quest_ids is not None else None)
        if include_enrichment:
            apply_quest_enrichment(records, payload=enrichment)
        records.sort(key=lambda quest: normalize_text(quest.name))
        catalog = cls(
            records,
            data_dir,
            errors,
            achievement_series=() if quest_ids is not None else achievement_quest_series(
                achievements,
                achievement_objectives,
                achievement_categories,
                achievement_names,
                entries,
            ),
        )
        if quest_ids is None:
            write_quest_catalog_cache(catalog, data_dir)
        return catalog


def _is_default_quest_data_dir(data_dir: Path) -> bool:
    try:
        return data_dir.resolve() == RAW_QUEST_DATA_DIR.resolve()
    except OSError:
        return False


def quest_catalog_cache_signature(data_dir: Path = RAW_QUEST_DATA_DIR) -> tuple[tuple[str, str, int | None, int | None], ...]:
    entries: list[tuple[str, str, int | None, int | None]] = []
    for label, relative_path in QUEST_CATALOG_SOURCE_FILES:
        path = data_dir / relative_path
        entries.append(_path_signature(label, path))
    entries.append(_path_signature("enrichment", DATA_DIR / "encyclopedia" / "quests" / "quests_enriched.json"))
    entries.append(_path_signature("loader", Path(__file__)))
    for folder_name in ("items", "resources", "misc", "archive"):
        entries.append(_path_signature(f"images/{folder_name}", DATA_DIR / "images" / folder_name))
    return tuple(entries)


def _path_signature(label: str, path: Path) -> tuple[str, str, int | None, int | None]:
    try:
        stat = path.stat()
    except OSError:
        return (label, str(path), None, None)
    return (label, str(path), stat.st_mtime_ns, stat.st_size)


def _catalog_to_cache_payload(catalog: QuestCatalog, data_dir: Path) -> dict[str, Any]:
    return {
        "version": QUEST_CATALOG_CACHE_VERSION,
        "signature": [list(value) for value in quest_catalog_cache_signature(data_dir)],
        "catalog": {
            "loaded_from": str(catalog.loaded_from) if catalog.loaded_from is not None else "",
            "errors": list(catalog.errors),
            "quests": [asdict(quest) for quest in catalog.quests],
            "achievement_series": [asdict(series) for series in catalog.achievement_series],
        },
    }


def _reward_from_cache(row: Any) -> QuestReward:
    row = row if isinstance(row, dict) else {}
    return QuestReward(
        name=str(row.get("name") or ""),
        quantity=safe_int(row.get("quantity")) or 1,
        image_path=str(row.get("image_path") or ""),
        item_id=safe_int(row.get("item_id")),
        kind=str(row.get("kind") or "item"),
    )


def _objective_from_cache(row: Any) -> QuestObjective:
    row = row if isinstance(row, dict) else {}
    return QuestObjective(
        id=safe_int(row.get("id")) or 0,
        text=str(row.get("text") or ""),
        type_id=safe_int(row.get("type_id")) or 0,
        map_label=str(row.get("map_label") or ""),
        zone=str(row.get("zone") or ""),
        image_path=str(row.get("image_path") or ""),
        image_label=str(row.get("image_label") or ""),
        item_id=safe_int(row.get("item_id")),
        item_quantity=safe_int(row.get("item_quantity")) or 0,
        is_combat=bool(row.get("is_combat")),
    )


def _step_from_cache(row: Any) -> QuestStep:
    row = row if isinstance(row, dict) else {}
    return QuestStep(
        id=safe_int(row.get("id")) or 0,
        name=str(row.get("name") or ""),
        description=str(row.get("description") or ""),
        objectives=[_objective_from_cache(value) for value in row.get("objectives", []) if isinstance(value, dict)],
        rewards=[_reward_from_cache(value) for value in row.get("rewards", []) if isinstance(value, dict)],
    )


def _solution_block_from_cache(row: Any) -> QuestSolutionBlock:
    row = row if isinstance(row, dict) else {}
    return QuestSolutionBlock(
        order=safe_int(row.get("order")) or 0,
        block_type=str(row.get("block_type") or ""),
        content=str(row.get("content") or ""),
        position=str(row.get("position") or ""),
        image_path=str(row.get("image_path") or ""),
        caption=str(row.get("caption") or ""),
        source_url=str(row.get("source_url") or ""),
        data=dict(row.get("data") or {}) if isinstance(row.get("data"), dict) else {},
    )


def _record_from_cache(row: Any) -> QuestRecord:
    row = row if isinstance(row, dict) else {}
    return QuestRecord(
        id=safe_int(row.get("id")) or 0,
        name=str(row.get("name") or ""),
        category=str(row.get("category") or ""),
        level_min=safe_int(row.get("level_min")) or 0,
        level_max=safe_int(row.get("level_max")) or 0,
        start_criterion=str(row.get("start_criterion") or ""),
        zones=[str(value) for value in row.get("zones", [])],
        achievements=[str(value) for value in row.get("achievements", [])],
        prerequisites=[str(value) for value in row.get("prerequisites", [])],
        info=[str(value) for value in row.get("info", [])],
        steps=[_step_from_cache(value) for value in row.get("steps", []) if isinstance(value, dict)],
        source_solution_steps=[
            _step_from_cache(value) for value in row.get("source_solution_steps", []) if isinstance(value, dict)
        ],
        solution_blocks=[
            _solution_block_from_cache(value) for value in row.get("solution_blocks", []) if isinstance(value, dict)
        ],
        source_info=dict(row.get("source_info") or {}) if isinstance(row.get("source_info"), dict) else {},
        rewards=[_reward_from_cache(value) for value in row.get("rewards", []) if isinstance(value, dict)],
    )


def _series_from_cache(row: Any) -> QuestAchievementSeries:
    row = row if isinstance(row, dict) else {}
    return QuestAchievementSeries(
        achievement_id=safe_int(row.get("achievement_id")) or 0,
        name=str(row.get("name") or ""),
        category=str(row.get("category") or ""),
        order=safe_int(row.get("order")) or 0,
        quest_ids=tuple(
            ident for ident in (safe_int(value) for value in row.get("quest_ids", [])) if ident is not None
        ),
    )


def _catalog_from_cache_payload(payload: Any) -> QuestCatalog | None:
    if not isinstance(payload, dict):
        return None
    rows = payload.get("quests")
    if not isinstance(rows, list):
        return None
    loaded_from_text = str(payload.get("loaded_from") or "").strip()
    series_rows = payload.get("achievement_series") if isinstance(payload.get("achievement_series"), list) else []
    return QuestCatalog(
        [_record_from_cache(row) for row in rows if isinstance(row, dict)],
        Path(loaded_from_text) if loaded_from_text else None,
        [str(value) for value in payload.get("errors", [])],
        achievement_series=tuple(_series_from_cache(row) for row in series_rows if isinstance(row, dict)),
    )


def read_quest_catalog_cache(data_dir: Path = RAW_QUEST_DATA_DIR) -> QuestCatalog | None:
    if not _is_default_quest_data_dir(data_dir) or not QUEST_CATALOG_CACHE_PATH.exists():
        return None
    try:
        with gzip.open(QUEST_CATALOG_CACHE_PATH, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != QUEST_CATALOG_CACHE_VERSION:
        return None
    raw_signature = payload.get("signature")
    if not isinstance(raw_signature, list):
        return None
    cached_signature = tuple(tuple(value) for value in raw_signature if isinstance(value, list))
    if cached_signature != quest_catalog_cache_signature(data_dir):
        return None
    return _catalog_from_cache_payload(payload.get("catalog"))


def write_quest_catalog_cache(catalog: QuestCatalog, data_dir: Path = RAW_QUEST_DATA_DIR) -> None:
    if not _is_default_quest_data_dir(data_dir):
        return
    payload = _catalog_to_cache_payload(catalog, data_dir)
    try:
        QUEST_CATALOG_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = QUEST_CATALOG_CACHE_PATH.with_suffix(QUEST_CATALOG_CACHE_PATH.suffix + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(QUEST_CATALOG_CACHE_PATH)
        try:
            QUEST_CATALOG_LEGACY_CACHE_PATH.unlink(missing_ok=True)
        except OSError:
            pass
    except (OSError, TypeError, ValueError):
        return


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def add_unique(values: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def load_character_xp_table(data_dir: Path) -> dict[int, int]:
    rows = doduda_keyed_rows(data_dir / "char_xp_mappings.json")
    table: dict[int, int] = {}
    for level, row in rows.items():
        value = safe_float(row.get("experiencePoints"))
        if value >= 0:
            table[level] = int(round(value))
    return table


def achievement_quest_series(
    achievements: dict[int, dict[str, Any]],
    achievement_objectives: dict[int, dict[str, Any]],
    categories: dict[int, dict[str, Any]],
    achievement_names: dict[int, str],
    entries: dict[str, Any],
) -> tuple[QuestAchievementSeries, ...]:
    """Keep the source achievement order used by the Quests hierarchy."""

    category_names = {
        category_id: localized_name(row, entries, f"Categorie {category_id}")
        for category_id, row in categories.items()
    }
    quest_rows: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for objective_id, objective in achievement_objectives.items():
        achievement_id = safe_int(objective.get("achievementId"))
        if achievement_id is None:
            continue
        order = safe_int(objective.get("order")) or 0
        criterion = str(objective.get("criterion") or "")
        for match_index, match in enumerate(re.finditer(r"\bQf\s*[=><!]+\s*(\d+)", criterion)):
            quest_id = safe_int(match.group(1))
            if quest_id is not None:
                quest_rows[achievement_id].append((order, int(objective_id) * 100 + match_index, quest_id))

    result: list[QuestAchievementSeries] = []
    for achievement_id, achievement in achievements.items():
        ordered_ids: list[int] = []
        for _order, _objective_id, quest_id in sorted(quest_rows.get(achievement_id, ())):
            if quest_id not in ordered_ids:
                ordered_ids.append(quest_id)
        if not ordered_ids:
            continue
        category_id = safe_int(achievement.get("categoryId")) or 0
        category = categories.get(category_id)
        category_name = category_names.get(category_id, "")
        result.append(
            QuestAchievementSeries(
                achievement_id=int(achievement_id),
                name=achievement_names.get(int(achievement_id), f"Succes {achievement_id}"),
                # Child labels are the useful families (Frigost, Wabbits, ...).
                category=category_name if isinstance(category, dict) else "",
                order=safe_int(achievement.get("order")) or 0,
                quest_ids=tuple(ordered_ids),
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda series: (
                normalize_text(series.category),
                series.order,
                normalize_text(series.name),
                series.achievement_id,
            ),
        )
    )


def achievements_by_quest(
    achievement_objectives: dict[int, dict[str, Any]],
    achievement_names: dict[int, str],
) -> dict[int, list[str]]:
    result: dict[int, list[str]] = defaultdict(list)
    for objective in achievement_objectives.values():
        criterion = str(objective.get("criterion") or "")
        achievement_id = safe_int(objective.get("achievementId"))
        if achievement_id is None:
            continue
        achievement = achievement_names.get(achievement_id, f"Succes {achievement_id}")
        for match in re.finditer(r"\bQf\s*[=><!]+\s*(\d+)", criterion):
            quest_id = safe_int(match.group(1))
            if quest_id is not None and achievement not in result[quest_id]:
                result[quest_id].append(achievement)
    return {quest_id: sorted(names, key=normalize_text) for quest_id, names in result.items()}


def criteria_to_lines(
    criterion: str,
    quest_names: dict[int, str],
    achievement_names: dict[int, str],
) -> list[str]:
    text = str(criterion or "").strip()
    if not text or text == "BT=1":
        return []
    lines: list[str] = []
    for match in re.finditer(r"\bPL\s*>\s*(\d+)", text):
        level = int(match.group(1)) + 1
        add_unique(lines, f"Niveau {level}+")
    for match in re.finditer(r"\bQf\s*=\s*(\d+)", text):
        ident = int(match.group(1))
        add_unique(lines, f"Quete terminee: {quest_names.get(ident, f'#{ident}')}")
    for match in re.finditer(r"\bQa\s*=\s*(\d+)", text):
        ident = int(match.group(1))
        add_unique(lines, f"Quete active: {quest_names.get(ident, f'#{ident}')}")
    for match in re.finditer(r"\bSc\s*=\s*(\d+)", text):
        ident = int(match.group(1))
        add_unique(lines, f"Succes requis: {achievement_names.get(ident, f'#{ident}')}")
    if not lines:
        add_unique(lines, text)
    return lines[:8]


def quest_info(quest: dict[str, Any], combat_count: int) -> list[str]:
    info: list[str] = []
    if safe_int(quest.get("isPartyQuest")):
        info.append("Combat de groupe / quete de groupe")
    elif combat_count:
        info.append("Combat detecte dans les objectifs")
    else:
        info.append("Aucun combat detecte")
    if safe_int(quest.get("isDungeonQuest")):
        info.append("Donjon")
    if safe_int(quest.get("isEvent")):
        info.append("Evenement")
    if combat_count:
        info.append(f"{combat_count} objectif(s) de combat")
    return info


def zone_for_map(
    map_id: Any,
    maps: dict[int, dict[str, Any]],
    subareas: dict[int, dict[str, Any]],
    areas: dict[int, dict[str, Any]],
    entries: dict[str, Any],
) -> str:
    ident = safe_int(map_id)
    if ident is None:
        return ""
    map_row = maps.get(ident)
    if not map_row:
        return ""
    subarea = subareas.get(safe_int(map_row.get("subAreaId")) or -1)
    area = areas.get(safe_int(subarea.get("areaId")) or -1) if subarea else None
    subarea_name = localized_name(subarea, entries, "")
    area_name = localized_name(area, entries, "")
    if subarea_name and area_name and subarea_name != area_name:
        return f"{area_name} - {subarea_name}"
    return subarea_name or area_name


def map_label(
    map_id: Any,
    coords: dict[str, Any] | None,
    maps: dict[int, dict[str, Any]],
) -> str:
    x_value = coords.get("x") if isinstance(coords, dict) else SENTINEL_COORD
    y_value = coords.get("y") if isinstance(coords, dict) else SENTINEL_COORD
    x = safe_int(x_value)
    y = safe_int(y_value)
    if x is not None and y is not None and x != SENTINEL_COORD and y != SENTINEL_COORD:
        return f"[{x},{y}]"
    ident = safe_int(map_id)
    map_row = maps.get(ident or -1)
    if map_row:
        pos_x = map_row.get("posX")
        pos_y = map_row.get("posY")
        if pos_x is not None and pos_y is not None:
            return f"[{pos_x},{pos_y}]"
    return ""


def resolve_objective(
    objective: dict[str, Any],
    objective_type_names: dict[int, str],
    entries: dict[str, Any],
    items: dict[int, dict[str, Any]],
    monsters: dict[int, dict[str, Any]],
    npcs: dict[int, dict[str, Any]],
    maps: dict[int, dict[str, Any]],
    subareas: dict[int, dict[str, Any]],
    areas: dict[int, dict[str, Any]],
    image_index: dict[str, str],
) -> QuestObjective:
    type_id = safe_int(objective.get("typeId")) or 0
    params = objective.get("parameters") if isinstance(objective.get("parameters"), dict) else {}
    values = [params.get(f"parameter{index}", 0) for index in range(5)]
    base = objective_type_names.get(type_id, f"Objectif {type_id}")
    replacements = parameter_replacements(type_id, values, entries, items, monsters, npcs, maps, subareas, areas)
    text = base
    for index, value in enumerate(replacements, 1):
        text = text.replace(f"#{index}", value)
    text = re.sub(r"#\d+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" :-")
    location = map_label(objective.get("mapId"), objective.get("coords"), maps)
    zone = zone_for_map(objective.get("mapId"), maps, subareas, areas, entries)
    image_path, image_label, item_id, item_quantity = objective_image(type_id, values, entries, items, monsters, npcs, image_index)
    if location and location not in text:
        text = f"{text} {location}".strip()
    return QuestObjective(
        id=safe_int(objective.get("id")) or 0,
        text=text or f"Objectif {safe_int(objective.get('id')) or ''}".strip(),
        type_id=type_id,
        map_label=location,
        zone=zone,
        image_path=image_path,
        image_label=image_label,
        item_id=item_id,
        item_quantity=item_quantity,
        is_combat=type_id in COMBAT_OBJECTIVE_TYPES,
    )


def image_path_for_row(row: dict[str, Any] | None, image_index: dict[str, str]) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("iconId", "gfxId", "id"):
        ident = safe_int(row.get(key))
        if ident is not None and str(ident) in image_index:
            return image_index[str(ident)]
    return ""


def objective_image(
    type_id: int,
    values: list[Any],
    entries: dict[str, Any],
    items: dict[int, dict[str, Any]],
    monsters: dict[int, dict[str, Any]],
    npcs: dict[int, dict[str, Any]],
    image_index: dict[str, str],
) -> tuple[str, str, int | None, int]:
    row: dict[str, Any] | None = None
    label = ""
    item_id: int | None = None
    quantity = 0
    if type_id in {2, 3}:
        item_id = safe_int(values[1])
        quantity = safe_int(values[2]) or 1
        row = items.get(item_id or -1)
        label = localized_name(row, entries, "")
    elif type_id == 8:
        item_id = safe_int(values[0])
        quantity = 1
        row = items.get(item_id or -1)
        label = localized_name(row, entries, "")
    elif type_id == 17:
        item_id = safe_int(values[0])
        quantity = safe_int(values[1]) or 1
        row = items.get(item_id or -1)
        label = localized_name(row, entries, "")
    elif type_id in COMBAT_OBJECTIVE_TYPES:
        row = monsters.get(safe_int(values[0]) or -1)
        label = localized_name(row, entries, "")
    elif type_id in {1, 9, 10}:
        row = npcs.get(safe_int(values[0]) or -1)
        label = localized_name(row, entries, "")
    return (image_path_for_row(row, image_index), label, item_id, quantity)


def parameter_replacements(
    type_id: int,
    values: list[Any],
    entries: dict[str, Any],
    items: dict[int, dict[str, Any]],
    monsters: dict[int, dict[str, Any]],
    npcs: dict[int, dict[str, Any]],
    maps: dict[int, dict[str, Any]],
    subareas: dict[int, dict[str, Any]],
    areas: dict[int, dict[str, Any]],
) -> list[str]:
    def npc_name(value: Any) -> str:
        ident = safe_int(value)
        return localized_name(npcs.get(ident or -1), entries, f"PNJ {value}")

    def item_name(value: Any) -> str:
        ident = safe_int(value)
        return localized_name(items.get(ident or -1), entries, f"Objet {value}")

    def monster_name(value: Any) -> str:
        ident = safe_int(value)
        return localized_name(monsters.get(ident or -1), entries, f"Monstre {value}")

    if type_id in {1, 9, 10}:
        return [npc_name(values[0])]
    if type_id in {2, 3}:
        return [npc_name(values[0]), item_name(values[1]), str(values[2] or 1)]
    if type_id in COMBAT_OBJECTIVE_TYPES:
        return [monster_name(values[0]), str(values[1] or 1)]
    if type_id == 0:
        return [text_for(entries, values[0], str(values[0] or ""))]
    if type_id == 5:
        zone = zone_for_map(values[0], maps, subareas, areas, entries)
        return [zone or str(values[0] or "")]
    if type_id == 8:
        return [item_name(values[0])]
    if type_id == 17:
        return [item_name(values[0]), str(values[1] or 1)]
    return [str(value or "") for value in values]


def resolve_step_rewards(
    reward: dict[str, Any] | None,
    entries: dict[str, Any],
    items: dict[int, dict[str, Any]],
    jobs: dict[int, dict[str, Any]],
    spells: dict[int, dict[str, Any]],
    titles: dict[int, dict[str, Any]],
    emoticons: dict[int, dict[str, Any]],
    image_index: dict[str, str],
    character_xp: dict[int, int],
    quest_level: int,
) -> list[QuestReward]:
    if not isinstance(reward, dict):
        return []
    result: list[QuestReward] = []
    xp_amount = quest_xp_amount(reward, character_xp, quest_level)
    if xp_amount > 0:
        result.append(QuestReward("XP", xp_amount, kind="xp"))
    kamas_amount = quest_kamas_amount(reward, quest_level)
    if kamas_amount > 0:
        result.append(QuestReward("Kamas", kamas_amount, kind="kamas"))
    for raw in array_value(reward.get("itemsReward")):
        values = array_value(raw.get("values") if isinstance(raw, dict) else raw)
        if len(values) < 2:
            continue
        ident = safe_int(values[0])
        quantity = safe_int(values[1]) or 1
        row = items.get(ident or -1)
        icon_id = safe_int(row.get("iconId")) if row else None
        image_path = image_index.get(str(icon_id), "") if icon_id is not None else ""
        result.append(
            QuestReward(
                localized_name(row, entries, f"Objet {ident}"),
                quantity,
                image_path,
                item_id=ident,
            )
        )
    for ident in reward_identifiers(reward.get("jobsReward")):
        if ident is not None:
            result.append(QuestReward(localized_name(jobs.get(ident), entries, f"Metier {ident}"), kind="job"))
    for ident in reward_identifiers(reward.get("spellsReward")):
        if ident is not None:
            result.append(QuestReward(localized_name(spells.get(ident), entries, f"Sort {ident}"), kind="spell"))
    for ident in reward_identifiers(reward.get("titlesReward")):
        if ident is not None:
            result.append(QuestReward(localized_name(titles.get(ident), entries, f"Titre {ident}"), kind="title"))
    for ident in reward_identifiers(reward.get("emotesReward")):
        if ident is not None:
            result.append(QuestReward(localized_name(emoticons.get(ident), entries, f"Emote {ident}"), kind="emote"))
    return result


def reward_identifiers(value: Any) -> list[int]:
    identifiers: list[int] = []
    for raw in array_value(value):
        values = array_value(raw.get("values")) if isinstance(raw, dict) else []
        ident = safe_int(values[0]) if values else safe_int(raw)
        if ident is not None:
            identifiers.append(ident)
    return identifiers


def select_reward_rows(rows: list[dict[str, Any]], quest_level: int) -> list[dict[str, Any]]:
    if not rows or quest_level <= 0:
        return rows
    unbounded: list[dict[str, Any]] = []
    matching: list[dict[str, Any]] = []
    for row in rows:
        level_min = safe_int(row.get("levelMin"))
        level_max = safe_int(row.get("levelMax"))
        has_min = level_min is not None and level_min >= 0
        has_max = level_max is not None and level_max >= 0
        if not has_min and not has_max:
            unbounded.append(row)
            continue
        if (not has_min or quest_level >= int(level_min)) and (not has_max or quest_level <= int(level_max)):
            matching.append(row)
    return unbounded + matching if matching else (unbounded or rows)


def reward_effective_level(reward: dict[str, Any], quest_level: int) -> int:
    level = max(1, int(quest_level or 1))
    level_min = safe_int(reward.get("levelMin"))
    level_max = safe_int(reward.get("levelMax"))
    if level_min is not None and level_min > 0:
        level = max(level, level_min)
    if level_max is not None and level_max > 0:
        level = min(level, level_max)
    return max(1, level)


def quest_xp_amount(reward: dict[str, Any], character_xp: dict[int, int], quest_level: int) -> int:
    ratio = safe_float(reward.get("experienceRatio"))
    if ratio <= 0 or not character_xp:
        return 0
    level = reward_effective_level(reward, quest_level)
    base = character_xp.get(level)
    if not base and level == 1:
        base = character_xp.get(2, 0)
    amount = int(round(float(base or 0) * ratio / 100.0))
    return max(1, amount) if amount > 0 else 0


def quest_kamas_amount(reward: dict[str, Any], quest_level: int) -> int:
    ratio = safe_float(reward.get("kamasRatio"))
    if ratio <= 0:
        return 0
    level = reward_effective_level(reward, quest_level)
    amount = int(round(float(level) * ratio * 100.0))
    return max(1, amount) if amount > 0 else 0


def dedupe_rewards(rewards: list[QuestReward]) -> list[QuestReward]:
    merged: dict[tuple[str, str, str, str], QuestReward] = {}
    for reward in rewards:
        key = (reward.kind, str(reward.item_id or ""), reward.name, reward.image_path)
        if key in merged:
            if reward.kind in {"item", "kamas"}:
                merged[key].quantity += max(1, reward.quantity)
        else:
            merged[key] = QuestReward(
                reward.name,
                max(1, reward.quantity),
                reward.image_path,
                item_id=reward.item_id,
                kind=reward.kind,
            )
    return sorted(merged.values(), key=lambda item: normalize_text(item.name))[:30]


def apply_quest_enrichment(records: list[QuestRecord], *, payload=None) -> None:
    path = DATA_DIR / "encyclopedia" / "quests" / "quests_enriched.json"
    payload = read_json_file(path, {}) if payload is None else payload
    quests = payload.get("quests", {}) if isinstance(payload, dict) else {}
    if not isinstance(quests, dict):
        return
    by_id = {int(record.id): record for record in records}
    for quest_id_text, row in quests.items():
        quest_id = safe_int(quest_id_text)
        if quest_id is None or quest_id not in by_id or not isinstance(row, dict):
            continue
        record = by_id[quest_id]
        solution_blocks = enrichment_solution_blocks(row)
        if solution_blocks:
            record.solution_blocks = sorted(solution_blocks, key=lambda item: item.order)
        source_steps = []
        for index, step_row in enumerate(array_value(row.get("solution_steps")), 1):
            if not isinstance(step_row, dict):
                continue
            objectives = []
            for objective_index, objective_row in enumerate(array_value(step_row.get("objectives")), 1):
                if not isinstance(objective_row, dict):
                    continue
                image_path = resolve_local_asset_path(objective_row.get("image_path"))
                objectives.append(
                    QuestObjective(
                        id=-(index * 1000 + objective_index),
                        text=str(objective_row.get("text") or ""),
                        type_id=6 if objective_row.get("combat") else 0,
                        map_label=str(objective_row.get("position") or ""),
                        image_path=image_path,
                        image_label=str(objective_row.get("caption") or ""),
                        item_id=safe_int(objective_row.get("item_id")),
                        item_quantity=safe_int(objective_row.get("quantity")) or 0,
                        is_combat=bool(objective_row.get("combat")),
                    )
                )
            source_steps.append(
                QuestStep(
                    id=-index,
                    name=str(step_row.get("title") or ""),
                    description=str(step_row.get("description") or ""),
                    objectives=objectives,
                    rewards=[],
                )
            )
        if source_steps:
            record.source_solution_steps = source_steps
        required_items = []
        for item in array_value(row.get("required_items")):
            if not isinstance(item, dict):
                required_items.append(item)
                continue
            normalized_item = dict(item)
            if normalized_item.get("image_path"):
                normalized_item["image_path"] = resolve_local_asset_path(normalized_item["image_path"])
            required_items.append(normalized_item)

        record.source_info = {
            "status": str(row.get("status") or ""),
            "source": str(row.get("source") or ""),
            "source_url": str(row.get("source_url") or ""),
            "required_items": required_items,
            "preparation": array_value(row.get("preparation")),
            "launch_position": row.get("launch_position") if isinstance(row.get("launch_position"), dict) else {},
            "rewards": array_value(row.get("rewards")),
            "quality": row.get("quality") if isinstance(row.get("quality"), dict) else {},
            "source_meta": row.get("source_meta") if isinstance(row.get("source_meta"), dict) else {},
        }


def enrichment_solution_blocks(row: dict[str, Any]) -> list[QuestSolutionBlock]:
    """Return only an explicitly ordered documentary walkthrough.

    Legacy ``solution_steps`` are gameplay objectives, not a faithful source
    document.  They remain available through ``source_solution_steps`` as a
    textual fallback, but must not be promoted to documentary blocks or make
    their attached NPC/monster assets visible automatically.
    """

    blocks: list[QuestSolutionBlock] = []
    for index, block_row in enumerate(array_value(row.get("solution_blocks")), 1):
        if not isinstance(block_row, dict):
            continue
        block_type = str(block_row.get("type") or block_row.get("block_type") or "").strip()
        if not block_type:
            continue
        blocks.append(
            QuestSolutionBlock(
                order=safe_int(block_row.get("order")) or index,
                block_type=block_type,
                content=str(block_row.get("content") or block_row.get("text") or ""),
                position=str(block_row.get("position") or ""),
                image_path=resolve_local_asset_path(block_row.get("image_path") or block_row.get("path")),
                caption=str(block_row.get("caption") or ""),
                source_url=str(block_row.get("source_url") or ""),
                data=block_row.get("data") if isinstance(block_row.get("data"), dict) else {},
            )
        )
    return blocks


def resolve_local_asset_path(value: Any) -> str:
    """Resolve portable or legacy absolute project paths against this checkout."""

    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    candidates = [path] if path.is_absolute() else [ROOT_DIR / path, path]

    normalized_parts = [part.casefold() for part in path.parts]
    if "data" in normalized_parts:
        data_index = normalized_parts.index("data")
        candidates.append(ROOT_DIR.joinpath(*path.parts[data_index:]))

    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate.resolve())
        except OSError:
            continue
    return text


def load_quest_progress(path: Path = QUEST_PROGRESS_FILE) -> dict[str, Any]:
    payload = read_json_resilient(path, {"version": 1, "characters": {}})
    if not isinstance(payload, dict):
        return {"version": 1, "characters": {}}
    payload.setdefault("version", 1)
    if not isinstance(payload.get("characters"), dict):
        payload["characters"] = {}
    return payload


def save_quest_progress(progress: dict[str, Any], path: Path = QUEST_PROGRESS_FILE) -> None:
    write_json_atomic(path, progress)


def quest_done(progress: dict[str, Any], character_key: str, quest_id: int) -> bool:
    character = progress.get("characters", {}).get(character_key, {})
    done = character.get("done", {}) if isinstance(character, dict) else {}
    return bool(done.get(str(quest_id)))


def set_quest_done(
    progress: dict[str, Any],
    character_key: str,
    quest_id: int,
    done: bool,
    path: Path = QUEST_PROGRESS_FILE,
) -> None:
    characters = progress.setdefault("characters", {})
    character = characters.setdefault(character_key, {"done": {}})
    done_map = character.setdefault("done", {})
    if done:
        done_map[str(quest_id)] = True
    else:
        done_map.pop(str(quest_id), None)
    save_quest_progress(progress, path)


def quest_item_done(progress: dict[str, Any], character_key: str, quest_id: int, item_id: int) -> bool:
    character = progress.get("characters", {}).get(character_key, {})
    items = character.get("quest_items", {}) if isinstance(character, dict) else {}
    quest_items = items.get(str(quest_id), {}) if isinstance(items, dict) else {}
    return bool(quest_items.get(str(item_id))) if isinstance(quest_items, dict) else False


def set_quest_item_done(
    progress: dict[str, Any],
    character_key: str,
    quest_id: int,
    item_id: int,
    done: bool,
    path: Path = QUEST_PROGRESS_FILE,
) -> None:
    characters = progress.setdefault("characters", {})
    character = characters.setdefault(character_key, {"done": {}})
    items = character.setdefault("quest_items", {})
    quest_items = items.setdefault(str(quest_id), {})
    if done:
        quest_items[str(item_id)] = True
    else:
        quest_items.pop(str(item_id), None)
        if not quest_items:
            items.pop(str(quest_id), None)
    save_quest_progress(progress, path)


def display_saved_character(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return " ".join(part.capitalize() for part in re.split(r"[_\s]+", text) if part)


def is_generic_dofus_client_name(value: str) -> bool:
    """Return whether a Unity title is build metadata, not a character name."""

    key = normalize_text(value)
    if not key:
        return False
    tokens = [token for token in key.split("_") if token]
    if not tokens or tokens[0] != "dofus":
        return False
    metadata = {"dofus", "release", "beta", "main", "client", "windows", "win64", "x64"}
    return all(token in metadata or token.isdigit() for token in tokens)


def load_quest_characters(
    profile_path: Path = PROFILE_FILE,
    client_index_path: Path = CLIENT_INDEX_JSON,
    slot_count: int = 8,
    binding_path: Path | None = None,
    connected_only: bool = False,
) -> list[QuestCharacter]:
    clients_payload = read_json_resilient(client_index_path, {})
    clients = clients_payload.get("clients", []) if isinstance(clients_payload, dict) else []
    if binding_path is None and Path(profile_path) == PROFILE_FILE and Path(client_index_path) == CLIENT_INDEX_JSON:
        binding_path = NETWORK_CHARACTER_BINDINGS_FILE
    identities: dict[int, dict] = {}
    if binding_path is not None:
        binding_payload = read_json_resilient(Path(binding_path), {})
        identity_rows = binding_payload.get("characters", {}) if isinstance(binding_payload, dict) else {}
        for raw_id, row in identity_rows.items() if isinstance(identity_rows, dict) else ():
            character_id = safe_int(raw_id)
            if character_id is not None and character_id > 0 and isinstance(row, dict):
                identities[character_id] = dict(row)

        # Backward-compatible read of verified rows written before progression
        # identity stopped using Organizer slots. Rows without an id are not
        # exposed because no safe progression key can be derived from them.
        old_slots = binding_payload.get("slots", {}) if isinstance(binding_payload, dict) else {}
        for raw_slot, row in old_slots.items() if isinstance(old_slots, dict) else ():
            character_id = safe_int(row.get("character_id")) if isinstance(row, dict) else None
            if character_id is None or character_id <= 0:
                continue
            migrated = dict(row)
            migrated.setdefault("organizer_slot", safe_int(raw_slot) or 0)
            identities.setdefault(character_id, migrated)

    ids_by_name: dict[str, list[int]] = {}
    ids_by_pid: dict[int, list[int]] = {}
    for character_id, row in identities.items():
        name_key = normalize_text(row.get("name"))
        if name_key:
            ids_by_name.setdefault(name_key, []).append(character_id)
        binding_pid = safe_int(row.get("pid"))
        if binding_pid is not None and binding_pid > 0:
            ids_by_pid.setdefault(binding_pid, []).append(character_id)

    connected_by_id: dict[int, tuple[int, str]] = {}
    for client in clients if isinstance(clients, list) else []:
        if not isinstance(client, dict):
            continue
        name = str(client.get("character_name") or client.get("name") or "").strip()
        if not name:
            continue
        client_pid = safe_int(client.get("pid")) or 0
        organizer_slot = safe_int(client.get("slot")) or safe_int(client.get("index")) or 0
        candidate_ids: tuple[int, ...]
        if is_generic_dofus_client_name(name):
            candidate_ids = tuple(dict.fromkeys(ids_by_pid.get(client_pid, ())))
        else:
            candidate_ids = tuple(dict.fromkeys(ids_by_name.get(normalize_text(name), ())))
            # A new named character can reuse the old character's process.
            # The former PID binding must not make that new name selectable
            # under somebody else's stable identity.
        if len(candidate_ids) != 1:
            continue
        character_id = candidate_ids[0]
        learned = str(identities[character_id].get("name") or "").strip()
        connected_by_id[character_id] = (
            organizer_slot,
            learned if is_generic_dofus_client_name(name) else name,
        )

    characters: list[QuestCharacter] = []
    for character_id, row in identities.items():
        connected = connected_by_id.get(character_id)
        if connected_only and connected is None:
            continue
        connected_slot, connected_name = connected if connected is not None else (0, "")
        slot = connected_slot or safe_int(row.get("organizer_slot")) or 0
        label = display_saved_character(connected_name or row.get("name"))
        if not label:
            continue
        characters.append(
            QuestCharacter(
                key=f"character:{character_id}",
                label=label,
                slot=slot,
                connected=connected is not None,
            )
        )
    return sorted(
        characters,
        key=lambda character: (
            0 if character.connected else 1,
            character.slot if character.slot > 0 else slot_count + 1,
            normalize_text(character.label),
        ),
    )
