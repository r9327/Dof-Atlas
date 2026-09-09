from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterable

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .migrations import BASE_SCHEMA_VERSION, migration_for
from .schema import CREATE_TABLES_SQL, SCHEMA_VERSION
from .utils import deep_merge, now_iso


JSON_COLUMNS = {
    "metadata_json",
    "counts_json",
    "warnings_json",
    "errors_json",
    "neighbours_json",
    "payload_json",
}
DB_BUSY_TIMEOUT_MS = 10_000


class DataStore:
    def __init__(self, db_path: str | Path | None = None, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config
        self.db_path = Path(db_path) if db_path else config.sqlite_path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self.connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(
                self.db_path,
                timeout=DB_BUSY_TIMEOUT_MS / 1000.0,
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = NORMAL")
        return self.connection

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def initialize(self) -> None:
        ensure_directories(self.config)
        conn = self.connect()
        conn.executescript(CREATE_TABLES_SQL)
        self._apply_schema_migrations(conn)
        conn.commit()

    def _apply_schema_migrations(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        current = int(row["version"] or 0) if row is not None else 0

        if current <= 0:
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (BASE_SCHEMA_VERSION, now_iso()),
            )
            current = BASE_SCHEMA_VERSION

        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Base locale plus recente que l'application: db={current}, app={SCHEMA_VERSION}"
            )

        for target_version in range(current + 1, SCHEMA_VERSION + 1):
            migration = migration_for(target_version)
            if migration is None:
                raise RuntimeError(
                    f"Migration SQLite manquante: {target_version - 1} -> {target_version}"
                )
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (target_version, now_iso()),
            )

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self.connect().execute(sql, tuple(params))

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_source(self, source: dict[str, Any]) -> int:
        payload = self._json(source.get("metadata_json") or source.get("metadata") or {})
        now = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sources(name, type, path, version, status, last_seen, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(type, path) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    status=excluded.status,
                    last_seen=excluded.last_seen,
                    metadata_json=excluded.metadata_json
                """,
                (
                    source.get("name") or source.get("type") or "source",
                    source.get("type") or "unknown",
                    str(source.get("path") or ""),
                    str(source.get("version") or ""),
                    source.get("status") or "ok",
                    now,
                    payload,
                ),
            )
            row = conn.execute(
                "SELECT id FROM sources WHERE type=? AND path=?",
                (source.get("type") or "unknown", str(source.get("path") or "")),
            ).fetchone()
            return int(row["id"])

    def upsert_entity(self, table: str, row: dict[str, Any], conflict_column: str = "ankama_id") -> int:
        row = self._prepare_row(row)
        table_columns = self._table_columns(table)
        row = {key: value for key, value in row.items() if key in table_columns}
        if "updated_at" in table_columns:
            row.setdefault("updated_at", now_iso())
        existing = None
        conflict_value = row.get(conflict_column)
        if conflict_value not in (None, ""):
            existing = self.query_one(f"SELECT * FROM {table} WHERE {conflict_column}=?", (conflict_value,))
        if existing:
            merged = dict(existing)
            for key, value in row.items():
                if key == "id":
                    continue
                if key.endswith("_json") and existing.get(key):
                    existing_json = self._loads(existing.get(key))
                    incoming_json = self._loads(value)
                    if isinstance(existing_json, dict) and isinstance(incoming_json, dict):
                        value = self._json(deep_merge(existing_json, incoming_json))
                    elif incoming_json not in (None, "", [], {}):
                        value = self._json(incoming_json)
                    else:
                        value = existing.get(key)
                elif value in (None, "", [], {}) and existing.get(key) not in (None, ""):
                    value = existing.get(key)
                merged[key] = value
            assignments = ", ".join(f"{key}=?" for key in row if key != "id")
            values = [merged[key] for key in row if key != "id"]
            values.append(conflict_value)
            with self.transaction() as conn:
                conn.execute(f"UPDATE {table} SET {assignments} WHERE {conflict_column}=?", values)
                return int(existing["id"])

        columns = [key for key in row if key != "id"]
        placeholders = ", ".join("?" for _ in columns)
        with self.transaction() as conn:
            cursor = conn.execute(
                f"INSERT INTO {table}({', '.join(columns)}) VALUES ({placeholders})",
                [row[key] for key in columns],
            )
            return int(cursor.lastrowid)

    def replace_recipe_ingredients(self, recipe_id: int, ingredients: list[dict[str, Any]]) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (recipe_id,))
            for ingredient in ingredients:
                row = self._prepare_row({**ingredient, "recipe_id": recipe_id})
                columns = [key for key in row if key != "id"]
                placeholders = ", ".join("?" for _ in columns)
                conn.execute(
                    f"INSERT OR REPLACE INTO recipe_ingredients({', '.join(columns)}) VALUES ({placeholders})",
                    [row[key] for key in columns],
                )

    def upsert_raw_object(self, source: str, object_type: str, object_id: Any, path: str | Path, payload: Any) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO raw_objects(source, object_type, object_id, path, payload_json, imported_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source, object_type, str(object_id or ""), str(path or ""), self._json(payload), now_iso()),
            )
            return int(cursor.lastrowid)

    def insert_import_report(self, report: dict[str, Any]) -> int:
        row = self._prepare_row(report)
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO import_reports(source, status, started_at, finished_at, counts_json, warnings_json, errors_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("source", ""),
                    row.get("status", "ok"),
                    row.get("started_at", ""),
                    row.get("finished_at", ""),
                    row.get("counts_json", "{}"),
                    row.get("warnings_json", "[]"),
                    row.get("errors_json", "[]"),
                ),
            )
            return int(cursor.lastrowid)

    def backup(self, destination: str | Path | None = None) -> Path:
        source = self.connect()
        source.commit()
        destination = Path(destination) if destination else self.db_path.with_suffix(f".{now_iso().replace(':', '-')}.bak")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        return destination

    def integrity_check(self) -> str:
        row = self.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"

    def _prepare_row(self, row: dict[str, Any]) -> dict[str, Any]:
        prepared: dict[str, Any] = {}
        for key, value in row.items():
            if key in JSON_COLUMNS or key.endswith("_json"):
                prepared[key] = self._json(value)
            elif isinstance(value, bool):
                prepared[key] = int(value)
            else:
                prepared[key] = value
        return prepared

    def _table_columns(self, table: str) -> set[str]:
        rows = self.connect().execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    @staticmethod
    def _json(value: Any) -> str:
        if isinstance(value, str):
            try:
                json.loads(value)
                return value
            except Exception:
                return json.dumps(value, ensure_ascii=False)
        return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _loads(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return {}
        return value or {}
