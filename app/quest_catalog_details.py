"""A lightweight quest index and bounded, on-demand documentary records.

The SQLite file is a reconstructible cache, never progression or game truth.
An immutable source signature names each generation; readers cannot combine
an older list with details from a newer source generation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from app import quest_catalog as qc
from app.quest_source_index import QuestSources

_DETAIL_FIELDS = frozenset({"steps", "source_solution_steps", "solution_blocks", "source_info", "rewards"})
_CACHE_ROOT = qc.ROOT_DIR / ".cache" / "dofus_atlas" / "quest_details_v1"


class DeferredQuestRecord(qc.QuestRecord):
    __slots__ = ("_details",)

    def __getattribute__(self, name):
        if name in _DETAIL_FIELDS:
            try:
                details = object.__getattribute__(self, "_details")
            except AttributeError:
                pass
            else:
                return getattr(details.get(object.__getattribute__(self, "id")), name)
        return super().__getattribute__(name)


class QuestDetails:
    def __init__(self, data_dir: Path, path: Path, signature: tuple, limit: int = 32):
        self.data_dir, self.path, self.signature = data_dir, path, signature
        self.limit = max(1, int(limit))
        self._lock = RLock()
        self._load_lock = RLock()
        self._sources = QuestSources(path.parent)
        self._records: OrderedDict[int, qc.QuestRecord] = OrderedDict()
        self.loads = self.hits = 0

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


def load_lazy_catalog(data_dir: Path, *, cache_root: Path = _CACHE_ROOT) -> qc.QuestCatalog:
    signature = _signature(data_dir)
    digest = hashlib.sha256(_json(signature).encode()).hexdigest()
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_root / f"{digest}.sqlite3"
    with _connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS quests (id INTEGER PRIMARY KEY, summary TEXT NOT NULL, detail TEXT)")
        connection.execute("BEGIN IMMEDIATE")
        ready = connection.execute("SELECT value FROM metadata WHERE key='ready'").fetchone()
        if ready is None:
            records, series = _source_index(data_dir)
            if _signature(data_dir) != signature:
                raise RuntimeError("Les sources Quêtes ont changé pendant l'indexation.")
            connection.executemany("INSERT OR REPLACE INTO quests VALUES (?, ?, NULL)",
                                   ((record.id, _json(asdict(record))) for record in records))
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('series', ?)",
                               (_json([asdict(item) for item in series]),))
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('ready', '1')")
        rows = [json.loads(row[0]) for row in connection.execute("SELECT summary FROM quests")]
        series = tuple(qc._series_from_cache(row) for row in json.loads(
            connection.execute("SELECT value FROM metadata WHERE key='series'").fetchone()[0]))
    details = QuestDetails(data_dir, path, signature)
    records = []
    for row in rows:
        record = DeferredQuestRecord(**row)
        record._details = details
        records.append(record)
    records.sort(key=lambda quest: qc.normalize_text(quest.name))
    catalog = qc.QuestCatalog(records, data_dir, achievement_series=series)
    catalog.get_detail = details.get
    catalog.is_detail_cached = details.cached
    catalog.detail_cache_info = details.info
    catalog.load_search_documents = lambda: details.search_documents(catalog.by_id)
    # Rich search is populated only by an explicit search; graph/list prewarm
    # must never enumerate documentary attributes of these records.
    catalog.deferred_details = True
    return catalog


def _source_index(data_dir):
    """Build only the fields needed by the Quests list and hierarchy."""

    language = qc.read_json_file(data_dir / "languages/fr.json", {})
    entries = language.get("entries", {}) if isinstance(language, dict) else {}
    if not isinstance(entries, dict):
        entries = {}

    quests = qc.doduda_rows(data_dir / "quests.json")
    categories = qc.doduda_rows(data_dir / "quest_categories.json")
    achievements = qc.doduda_rows(data_dir / "achievements.json")
    achievement_objectives = qc.doduda_rows(data_dir / "achievement_objectives.json")
    achievement_categories = qc.doduda_rows(data_dir / "achievement_categories.json")

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
