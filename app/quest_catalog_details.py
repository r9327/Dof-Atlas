"""A lightweight quest index and bounded, on-demand documentary records.

The SQLite file is a reconstructible cache, never progression or game truth.
An immutable source signature names each generation; readers cannot combine
an older list with details from a newer source generation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from app import quest_catalog as qc
from app.quest_source_index import QuestSources

_DETAIL_FIELDS = frozenset({"steps", "source_solution_steps", "solution_blocks", "source_info", "rewards"})
_SUMMARY_FIELDS = {"achievements": 0, "prerequisites": 1, "info": 2}
_CACHE_ROOT = qc.ROOT_DIR / ".cache" / "dofus_atlas" / "quest_details_v1"


class DeferredQuestRecord(qc.QuestRecord):
    __slots__ = ("_details",)

    def __getattribute__(self, name):
        summary_index = _SUMMARY_FIELDS.get(name)
        if summary_index is not None:
            try:
                details = object.__getattribute__(self, "_details")
            except AttributeError:
                details = None
            if details is not None:
                return details.summary_fields(object.__getattribute__(self, "id"))[summary_index]
        if name in _DETAIL_FIELDS:
            try:
                details = object.__getattribute__(self, "_details")
            except AttributeError:
                details = None
            if details is not None:
                return getattr(details.get(object.__getattribute__(self, "id")), name)
        return super().__getattribute__(name)


class QuestDetails:
    def __init__(self, data_dir: Path, path: Path, signature: tuple, limit: int = 32):
        self.data_dir, self.path, self.signature = data_dir, path, signature
        self.limit = max(1, int(limit))
        self._lock = RLock()
        self._load_lock = RLock()
        # Reuse the canonical byte-offset indexes prepared by preload.
        # Using the SQLite parent directly created a second offset-cache namespace,
        # so the first rich Quest detail rebuilt indexes from monolithic JSON in
        # Atlas' long-lived process and caused the Guide memory spike.
        self._sources = QuestSources(path.parent / "source_offsets")
        self._records: OrderedDict[int, qc.QuestRecord] = OrderedDict()
        self._summaries: OrderedDict[
            int,
            tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
        ] = OrderedDict()
        self.loads = self.hits = 0

    def summary_fields(
        self,
        quest_id: int,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        quest_id = int(quest_id)
        with self._lock:
            cached = self._summaries.get(quest_id)
            if cached is not None:
                self._summaries.move_to_end(quest_id)
                return cached
        with _connect(self.path) as connection:
            row = connection.execute(
                "SELECT achievements, prerequisites, info FROM quests WHERE id=?",
                (quest_id,),
            ).fetchone()
        if row is None:
            return (), (), ()
        result = (
            tuple(str(value) for value in json.loads(row[0] or "[]")),
            tuple(str(value) for value in json.loads(row[1] or "[]")),
            tuple(str(value) for value in json.loads(row[2] or "[]")),
        )
        with self._lock:
            self._summaries[quest_id] = result
            self._summaries.move_to_end(quest_id)
            while len(self._summaries) > self.limit:
                self._summaries.popitem(last=False)
        return result

    def guide_evidence(self, quest_id: int) -> dict[str, object]:
        """Return tiny Guide-only item/combat evidence without hydrating Quest details."""

        with _connect(self.path) as connection:
            row = connection.execute(
                "SELECT guide_evidence FROM quests WHERE id=?",
                (int(quest_id),),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row[0] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def cached(self, quest_id: int) -> bool:
        with self._lock:
            return int(quest_id) in self._records

    def get(self, quest_id: int) -> qc.QuestRecord:
        quest_id = int(quest_id)
        with self._load_lock:
            with self._lock:
                record = self._records.get(quest_id)
                if record is not None:
                    self.hits += 1
                    self._records.move_to_end(quest_id)
                    return record
            with _connect(self.path) as connection:
                row = connection.execute("SELECT detail FROM quests WHERE id=?", (quest_id,)).fetchone()
            if row is None:
                raise KeyError(quest_id)
            if row[0] is not None:
                record = qc._record_from_cache(json.loads(row[0]))
            else:
                if _signature(self.data_dir) != self.signature:
                    raise RuntimeError("Les sources Quêtes ont changé ; rechargez le catalogue.")
                try:
                    record = qc.QuestCatalog._load_source(self.data_dir, quest_ids={quest_id}, sources=self._sources).by_id[quest_id]
                finally:
                    self._sources.close()
                if _signature(self.data_dir) != self.signature:
                    raise RuntimeError("Les sources Quêtes ont changé pendant le chargement.")
                with _connect(self.path) as connection:
                    connection.execute("UPDATE quests SET detail=? WHERE id=?", (_json(asdict(record)), quest_id))
            with self._lock:
                self._records[quest_id] = record
                self.loads += 1
                while len(self._records) > self.limit:
                    self._records.popitem(last=False)
            return record

    def info(self):
        with self._lock:
            return {"records": len(self._records), "limit": self.limit, "loads": self.loads, "hits": self.hits}

    def search_documents(self, quest_ids):
        """Build the existing rich search index only after a real search request."""
        with self._load_lock:
            with _connect(self.path) as connection:
                row = connection.execute("SELECT value FROM metadata WHERE key='search'").fetchone()
            if row is not None:
                return {int(key): value for key, value in json.loads(row[0]).items()}
            if _signature(self.data_dir) != self.signature:
                raise RuntimeError("Les sources Quêtes ont changé ; rechargez le catalogue.")
            documents = {}
            ids = list(quest_ids)
            try:
                # Explicit rich search needs objective text across the catalogue.
                # Keep only a bounded batch of source records, never all details.
                for offset in range(0, len(ids), 32):
                    catalog = qc.QuestCatalog._load_source(self.data_dir, quest_ids=set(ids[offset:offset + 32]),
                        sources=self._sources, include_enrichment=False)
                    documents.update({quest.id: qc.normalize_text(" ".join([
                        quest.search_text, " ".join(step.name for step in quest.steps),
                        " ".join(objective.text for step in quest.steps for objective in step.objectives),
                        " ".join(reward.name for reward in quest.rewards),
                    ])) for quest in catalog.quests})
                    del catalog
            finally:
                self._sources.close()
            if _signature(self.data_dir) != self.signature:
                raise RuntimeError("Les sources Quêtes ont changé pendant l'indexation de recherche.")
            with _connect(self.path) as connection:
                connection.execute("INSERT OR REPLACE INTO metadata VALUES ('search', ?)", (_json(documents),))
            return documents


@contextmanager
def _connect(path):
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        with connection:
            yield connection
    finally:
        connection.close()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _signature(data_dir):
    return (*qc.quest_catalog_cache_signature(data_dir), qc._path_signature("details_loader", Path(__file__)),
            qc._path_signature("source_index", Path(__file__).with_name("quest_source_index.py")))


def _cache_identity(data_dir: Path, cache_root: Path) -> tuple[tuple, Path]:
    signature = _signature(data_dir)
    digest = hashlib.sha256(_json(signature).encode()).hexdigest()
    cache_root.mkdir(parents=True, exist_ok=True)
    return signature, cache_root / f"{digest}.sqlite3"


def ensure_lazy_catalog_cache(
    data_dir: Path = qc.RAW_QUEST_DATA_DIR,
    *,
    cache_root: Path = _CACHE_ROOT,
) -> int:
    """Materialize the reconstructible Quest SQLite store without retaining rows."""

    signature, path = _cache_identity(data_dir, cache_root)
    with _connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS quests ("
            "id INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "category TEXT NOT NULL, "
            "level_min INTEGER NOT NULL, "
            "level_max INTEGER NOT NULL, "
            "start_criterion TEXT NOT NULL, "
            "achievements TEXT NOT NULL, "
            "prerequisites TEXT NOT NULL, "
            "info TEXT NOT NULL, "
            "guide_evidence TEXT NOT NULL DEFAULT '{}', "
            "detail TEXT"
            ")"
        )
        connection.execute("BEGIN IMMEDIATE")
        ready = connection.execute("SELECT value FROM metadata WHERE key='ready'").fetchone()
        if ready is None:
            records, series = _source_index(data_dir)
            guide_evidence = _guide_evidence_index(data_dir)
            if _signature(data_dir) != signature:
                raise RuntimeError("Les sources Quêtes ont changé pendant l'indexation.")
            connection.executemany(
                "INSERT OR REPLACE INTO quests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    (
                        int(record.id),
                        str(record.name),
                        str(record.category),
                        int(record.level_min),
                        int(record.level_max),
                        str(record.start_criterion),
                        _json(record.achievements),
                        _json(record.prerequisites),
                        _json(record.info),
                        _json(guide_evidence.get(int(record.id), {})),
                    )
                    for record in records
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata VALUES ('series', ?)",
                (_json([asdict(item) for item in series]),),
            )
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('ready', '1')")
        row = connection.execute("SELECT COUNT(*) FROM quests").fetchone()
        return max(0, int(row[0] if row else 0))


def load_quest_name_index(
    data_dir: Path = qc.RAW_QUEST_DATA_DIR,
    *,
    cache_root: Path = _CACHE_ROOT,
) -> dict[str, int]:
    """Return normalized quest-name -> id directly from the compact SQLite store."""

    ensure_lazy_catalog_cache(data_dir, cache_root=cache_root)
    _signature_value, path = _cache_identity(data_dir, cache_root)
    result: dict[str, int] = {}
    with _connect(path) as connection:
        for quest_id, name in connection.execute("SELECT id, name FROM quests ORDER BY id"):
            key = qc.normalize_text(str(name or ""))
            if key and key not in result:
                result[key] = int(quest_id)
    return result


class NetworkQuestRecord:
    """Tiny network-only row; rich Quest details stay SQLite-backed."""

    __slots__ = ("id", "name", "_details")

    def __init__(self, quest_id: int, name: str, details: QuestDetails) -> None:
        self.id = int(quest_id)
        self.name = str(name or f"Quete {quest_id}")
        self._details = details

    @property
    def steps(self):
        return self._details.get(self.id).steps


def load_network_catalog(
    data_dir: Path = qc.RAW_QUEST_DATA_DIR,
    *,
    cache_root: Path = _CACHE_ROOT,
) -> qc.QuestCatalog:
    """Return the minimal QuestCatalog contract required by network validation."""

    ensure_lazy_catalog_cache(data_dir, cache_root=cache_root)
    signature, path = _cache_identity(data_dir, cache_root)
    details = QuestDetails(data_dir, path, signature, limit=8)
    records: list[NetworkQuestRecord] = []
    with _connect(path) as connection:
        for quest_id, name in connection.execute("SELECT id, name FROM quests ORDER BY id"):
            records.append(NetworkQuestRecord(int(quest_id), str(name or ""), details))
    catalog = qc.QuestCatalog(records, data_dir, achievement_series=())
    catalog.get_detail = details.get
    catalog.is_detail_cached = details.cached
    catalog.detail_cache_info = details.info
    catalog.deferred_details = True
    return catalog


def load_lazy_catalog(data_dir: Path, *, cache_root: Path = _CACHE_ROOT) -> qc.QuestCatalog:
    ensure_lazy_catalog_cache(data_dir, cache_root=cache_root)
    signature, path = _cache_identity(data_dir, cache_root)
    details = QuestDetails(data_dir, path, signature)
    records: list[DeferredQuestRecord] = []
    empty: tuple = ()
    with _connect(path) as connection:
        cursor = connection.execute(
            "SELECT id, name, category, level_min, level_max, start_criterion "
            "FROM quests ORDER BY name COLLATE NOCASE"
        )
        for (
            quest_id,
            name,
            category,
            level_min,
            level_max,
            start_criterion,
        ) in cursor:
            record = DeferredQuestRecord(
                id=int(quest_id),
                name=str(name or ""),
                category=str(category or ""),
                level_min=int(level_min or 0),
                level_max=int(level_max or 0),
                start_criterion=str(start_criterion or ""),
                zones=empty,
                achievements=empty,
                prerequisites=empty,
                info=empty,
                steps=empty,
                source_solution_steps=empty,
                solution_blocks=empty,
                source_info=None,
                rewards=empty,
            )
            record._details = details
            records.append(record)
        series_row = connection.execute(
            "SELECT value FROM metadata WHERE key='series'"
        ).fetchone()
        series = tuple(
            qc._series_from_cache(row)
            for row in json.loads(series_row[0] if series_row else "[]")
        )
    catalog = qc.QuestCatalog(records, data_dir, achievement_series=series)
    catalog.get_detail = details.get
    catalog.is_detail_cached = details.cached
    catalog.detail_cache_info = details.info
    catalog.guide_evidence = details.guide_evidence
    catalog.load_search_documents = lambda: details.search_documents(catalog.by_id)
    # Rich search is populated only by an explicit search; graph/list prewarm
    # must never enumerate documentary attributes of these records.
    catalog.deferred_details = True
    return catalog


def _guide_evidence_index(data_dir: Path) -> dict[int, dict[str, object]]:
    """Build tiny Guide item/combat evidence from raw Quest objectives."""

    required = (
        data_dir / "quests.json",
        data_dir / "quest_objectives.json",
        data_dir / "items.json",
        data_dir / "monsters.json",
        data_dir / "languages" / "fr.json",
    )
    if any(not path.exists() for path in required):
        return {}

    sources = QuestSources(_CACHE_ROOT / "source_offsets")
    try:
        entries = sources.mapping(data_dir / "languages/fr.json", "entries")
        quests = sources.rows(data_dir / "quests.json")
        items = sources.rows(data_dir / "items.json")
        monsters = sources.rows(data_dir / "monsters.json")
        objective_path = data_dir / "quest_objectives.json"
        result: dict[int, dict[str, object]] = {}

        for quest_id, quest in quests.items():
            step_ids = [
                int(value)
                for value in qc.array_value(quest.get("stepIds"))
                if qc.safe_int(value) is not None
            ]
            if not step_ids:
                continue

            item_rows: list[dict[str, object]] = []
            combat_rows: list[dict[str, object]] = []
            seen_items: set[tuple[int, int]] = set()
            seen_combats: set[int] = set()

            for objective in sources.objectives_for_steps(objective_path, step_ids):
                if not isinstance(objective, dict):
                    continue
                type_id = qc.safe_int(objective.get("typeId")) or 0
                objective_id = qc.safe_int(objective.get("id")) or 0
                params = objective.get("parameters") if isinstance(objective.get("parameters"), dict) else {}
                values = [params.get(f"parameter{index}", 0) for index in range(5)]

                item_id = None
                quantity = 1
                if type_id in {2, 3}:
                    item_id = qc.safe_int(values[1])
                    quantity = qc.safe_int(values[2]) or 1
                elif type_id == 8:
                    item_id = qc.safe_int(values[0])
                elif type_id == 17:
                    item_id = qc.safe_int(values[0])
                    quantity = qc.safe_int(values[1]) or 1

                if item_id is not None:
                    item_key = (int(item_id), int(quantity))
                    if item_key not in seen_items:
                        seen_items.add(item_key)
                        item_rows.append(
                            {
                                "item_id": int(item_id),
                                "name": qc.localized_name(
                                    items.get(int(item_id)),
                                    entries,
                                    f"Objet {item_id}",
                                ),
                                "quantity": max(1, int(quantity)),
                            }
                        )

                if type_id in qc.COMBAT_OBJECTIVE_TYPES and objective_id > 0:
                    if objective_id in seen_combats:
                        continue
                    seen_combats.add(objective_id)
                    monster_id = qc.safe_int(values[0])
                    combat_rows.append(
                        {
                            "objective_id": int(objective_id),
                            "monster": qc.localized_name(
                                monsters.get(monster_id or -1),
                                entries,
                                f"Monstre {monster_id}" if monster_id is not None else "",
                            ),
                            "quantity": max(1, int(qc.safe_int(values[1]) or 1)),
                        }
                    )

            if item_rows or combat_rows:
                result[int(quest_id)] = {"items": item_rows, "combats": combat_rows}
        return result
    finally:
        sources.close()


def _source_index(data_dir):
    """Build only the fields needed by the Quests list and hierarchy."""

    sources = QuestSources(_CACHE_ROOT / "source_offsets")
    try:
        entries = sources.mapping(data_dir / "languages/fr.json", "entries")
        quests = sources.rows(data_dir / "quests.json")
        categories = sources.rows(data_dir / "quest_categories.json")
        achievements = sources.rows(data_dir / "achievements.json")
        achievement_objectives = sources.rows(data_dir / "achievement_objectives.json")
        achievement_categories = sources.rows(data_dir / "achievement_categories.json")

        category_names = {
            ident: qc.localized_name(row, entries, f"Categorie {ident}")
            for ident, row in categories.items()
        }
        achievement_names = {
            ident: qc.localized_name(row, entries, f"Succes {ident}")
            for ident, row in achievements.items()
        }
        quest_names = {
            ident: qc.localized_name(row, entries, f"Quete {ident}")
            for ident, row in quests.items()
        }
        linked_achievements = qc.achievements_by_quest(
            achievement_objectives,
            achievement_names,
        )

        records = []
        for quest_id, row in quests.items():
            criterion = str(row.get("startCriterion") or "")
            records.append(
                qc.QuestRecord(
                    id=int(quest_id),
                    name=quest_names.get(int(quest_id), f"Quete {quest_id}"),
                    category=category_names.get(
                        qc.safe_int(row.get("categoryId")) or -1,
                        "",
                    ),
                    level_min=int(row.get("levelMin") or 0),
                    level_max=int(row.get("levelMax") or 0),
                    start_criterion=criterion,
                    # Documentary fields are loaded by QuestDetails.get() only
                    # after an explicit quest selection or search.
                    zones=[],
                    achievements=linked_achievements.get(int(quest_id), []),
                    prerequisites=qc.criteria_to_lines(
                        criterion,
                        quest_names,
                        achievement_names,
                    ),
                    info=qc.quest_info(row, 0),
                )
            )

        records.sort(key=lambda quest: qc.normalize_text(quest.name))
        series = qc.achievement_quest_series(
            achievements,
            achievement_objectives,
            achievement_categories,
            achievement_names,
            entries,
        )
        return records, series
    finally:
        sources.close()


if __name__ == "__main__" and "--ensure-cache" in sys.argv:
    count = ensure_lazy_catalog_cache()
    if "--result-file" in sys.argv:
        try:
            result_path = Path(sys.argv[sys.argv.index("--result-file") + 1])
        except (ValueError, IndexError):
            raise SystemExit(2)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(str(count), encoding="utf-8")
    else:
        print(count)
