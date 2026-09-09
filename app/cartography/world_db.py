from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, LOGGER

WORLD_DB_PATH = DATA_DIR / "dofus_atlas_world.db"
VALID_MAP_STATUSES = {"unknown", "unverified", "verified", "current"}
DB_BUSY_TIMEOUT_MS = 10_000
_INIT_LOCK = threading.RLock()
_INITIALIZED_DB_IDENTITY = ""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_status(status: str | None) -> str:
    value = str(status or "unverified").strip().casefold()
    return value if value in VALID_MAP_STATUSES else "unverified"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def encode_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _db_identity() -> str:
    try:
        return str(WORLD_DB_PATH.resolve())
    except OSError:
        return str(WORLD_DB_PATH)


def get_connection() -> sqlite3.Connection:
    WORLD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        WORLD_DB_PATH,
        timeout=DB_BUSY_TIMEOUT_MS / 1000.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def connection_scope():
    connection = get_connection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(connection, table_name):
        return set()
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _rename_legacy_maps_if_needed(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "maps")
    if not columns or "view_key" in columns:
        return
    base_name = "maps_legacy_world_grid"
    target_name = base_name
    suffix = 1
    while _table_exists(connection, target_name):
        target_name = f"{base_name}_{suffix}"
        suffix += 1
    LOGGER.info("Migration cartographie: ancienne table maps renommee en %s", target_name)
    connection.execute(f"ALTER TABLE maps RENAME TO {_quote_identifier(target_name)}")


def init_db(force: bool = False) -> None:
    global _INITIALIZED_DB_IDENTITY

    identity = _db_identity()
    with _INIT_LOCK:
        if (
            not force
            and _INITIALIZED_DB_IDENTITY == identity
            and WORLD_DB_PATH.exists()
        ):
            return

        WORLD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with connection_scope() as connection:
            _rename_legacy_maps_if_needed(connection)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS map_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    view_key TEXT NOT NULL UNIQUE,
                    parent_view_key TEXT,
                    name TEXT NOT NULL,
                    kind TEXT DEFAULT 'world',
                    asset_path TEXT,
                    min_x INTEGER,
                    max_x INTEGER,
                    min_y INTEGER,
                    max_y INTEGER,
                    tile_width INTEGER DEFAULT 64,
                    tile_height INTEGER DEFAULT 32,
                    sort_order INTEGER DEFAULT 0,
                    raw_data TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS maps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    view_key TEXT NOT NULL,
                    map_id TEXT,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    status TEXT DEFAULT 'unverified',
                    scan_count INTEGER DEFAULT 0,
                    last_seen_at TEXT,
                    polygon_json TEXT,
                    rect_json TEXT,
                    raw_data TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(view_key, x, y)
                );

                CREATE TABLE IF NOT EXISTS map_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_view_key TEXT NOT NULL,
                    from_x INTEGER,
                    from_y INTEGER,
                    target_view_key TEXT NOT NULL,
                    label TEXT,
                    link_type TEXT DEFAULT 'entrance',
                    marker_x INTEGER,
                    marker_y INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_map_views_parent ON map_views(parent_view_key);
                CREATE INDEX IF NOT EXISTS idx_maps_view_xy ON maps(view_key, x, y);
                CREATE INDEX IF NOT EXISTS idx_maps_view_status ON maps(view_key, status);
                CREATE INDEX IF NOT EXISTS idx_map_links_from ON map_links(from_view_key);
                CREATE INDEX IF NOT EXISTS idx_map_links_target ON map_links(target_view_key);
                """
            )
        _INITIALIZED_DB_IDENTITY = identity


def upsert_map_view(
    view_key: str,
    name: str,
    parent_view_key: str | None = None,
    kind: str = "world",
    asset_path: str | None = None,
    min_x: int | None = None,
    max_x: int | None = None,
    min_y: int | None = None,
    max_y: int | None = None,
    tile_width: int = 64,
    tile_height: int = 32,
    sort_order: int = 0,
    raw_data: Any = None,
) -> dict[str, Any]:
    init_db()
    clean_key = str(view_key or "").strip()
    clean_name = str(name or "").strip()
    if not clean_key:
        raise ValueError("view_key obligatoire.")
    if not clean_name:
        raise ValueError("Le nom de la vue est obligatoire.")
    now = utc_now()
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO map_views (
                view_key, parent_view_key, name, kind, asset_path, min_x, max_x,
                min_y, max_y, tile_width, tile_height, sort_order, raw_data,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(view_key) DO UPDATE SET
                parent_view_key = excluded.parent_view_key,
                name = excluded.name,
                kind = excluded.kind,
                asset_path = excluded.asset_path,
                min_x = excluded.min_x,
                max_x = excluded.max_x,
                min_y = excluded.min_y,
                max_y = excluded.max_y,
                tile_width = excluded.tile_width,
                tile_height = excluded.tile_height,
                sort_order = excluded.sort_order,
                raw_data = COALESCE(excluded.raw_data, map_views.raw_data),
                updated_at = excluded.updated_at
            """,
            (
                clean_key,
                str(parent_view_key).strip() if parent_view_key else None,
                clean_name,
                str(kind or "world").strip() or "world",
                str(asset_path).strip() if asset_path else None,
                optional_int(min_x),
                optional_int(max_x),
                optional_int(min_y),
                optional_int(max_y),
                int(tile_width or 64),
                int(tile_height or 32),
                int(sort_order or 0),
                encode_json(raw_data),
                now,
                now,
            ),
        )
        row = connection.execute(
            "SELECT * FROM map_views WHERE view_key = ?",
            (clean_key,),
        ).fetchone()
        return row_to_dict(row) or {}


def get_map_views() -> list[dict[str, Any]]:
    init_db()
    with connection_scope() as connection:
        rows = connection.execute(
            "SELECT * FROM map_views ORDER BY sort_order ASC, name COLLATE NOCASE ASC"
        ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def get_child_views(parent_view_key: str | None) -> list[dict[str, Any]]:
    init_db()
    with connection_scope() as connection:
        if parent_view_key is None:
            rows = connection.execute(
                """
                SELECT * FROM map_views
                WHERE parent_view_key IS NULL OR parent_view_key = ''
                ORDER BY sort_order ASC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM map_views
                WHERE parent_view_key = ?
                ORDER BY sort_order ASC, name COLLATE NOCASE ASC
                """,
                (str(parent_view_key),),
            ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def get_map_view(view_key: str) -> dict[str, Any] | None:
    init_db()
    with connection_scope() as connection:
        row = connection.execute(
            "SELECT * FROM map_views WHERE view_key = ?",
            (str(view_key),),
        ).fetchone()
        return row_to_dict(row)


def _map_select_clause() -> str:
    return """
        SELECT maps.*,
               map_views.name AS view_name,
               map_views.kind AS view_kind,
               map_views.parent_view_key AS parent_view_key
        FROM maps
        LEFT JOIN map_views ON map_views.view_key = maps.view_key
    """


def upsert_map(
    view_key: str,
    x: int,
    y: int,
    map_id: str | None = None,
    status: str = "unverified",
    rect_json: Any = None,
    polygon_json: Any = None,
    raw_data: Any = None,
) -> dict[str, Any]:
    init_db()
    clean_key = str(view_key or "").strip()
    if not clean_key:
        raise ValueError("view_key obligatoire.")
    now = utc_now()
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO maps (
                view_key, map_id, x, y, status, scan_count, last_seen_at,
                polygon_json, rect_json, raw_data, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(view_key, x, y) DO UPDATE SET
                map_id = COALESCE(excluded.map_id, maps.map_id),
                status = excluded.status,
                polygon_json = COALESCE(excluded.polygon_json, maps.polygon_json),
                rect_json = COALESCE(excluded.rect_json, maps.rect_json),
                raw_data = COALESCE(excluded.raw_data, maps.raw_data),
                updated_at = excluded.updated_at
            """,
            (
                clean_key,
                str(map_id).strip() if map_id not in (None, "") else None,
                int(x),
                int(y),
                normalize_status(status),
                encode_json(polygon_json),
                encode_json(rect_json),
                encode_json(raw_data),
                now,
                now,
            ),
        )
        row = connection.execute(
            _map_select_clause()
            + " WHERE maps.view_key = ? AND maps.x = ? AND maps.y = ?",
            (clean_key, int(x), int(y)),
        ).fetchone()
        return row_to_dict(row) or {}


def replace_view_children(view_key: str) -> None:
    init_db()
    clean_key = str(view_key or "").strip()
    if not clean_key:
        raise ValueError("view_key obligatoire.")
    with connection_scope() as connection:
        connection.execute("DELETE FROM maps WHERE view_key = ?", (clean_key,))
        connection.execute("DELETE FROM map_links WHERE from_view_key = ?", (clean_key,))


def _set_map_status(view_key: str, x: int, y: int, status: str) -> dict[str, Any]:
    init_db()
    clean_key = str(view_key or "").strip()
    if not clean_key:
        raise ValueError("view_key obligatoire.")
    normalized = normalize_status(status)
    if normalized == "current":
        return set_current_map(clean_key, x, y)
    now = utc_now()
    with connection_scope() as connection:
        cursor = connection.execute(
            """
            UPDATE maps
            SET status = ?,
                updated_at = ?,
                last_seen_at = CASE WHEN ? = 'verified' THEN ? ELSE last_seen_at END
            WHERE view_key = ? AND x = ? AND y = ?
            """,
            (normalized, now, normalized, now, clean_key, int(x), int(y)),
        )
        if cursor.rowcount == 0:
            connection.execute(
                """
                INSERT INTO maps (view_key, x, y, status, scan_count, last_seen_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    clean_key,
                    int(x),
                    int(y),
                    normalized,
                    now if normalized == "verified" else None,
                    now,
                    now,
                ),
            )
        row = connection.execute(
            _map_select_clause()
            + " WHERE maps.view_key = ? AND maps.x = ? AND maps.y = ?",
            (clean_key, int(x), int(y)),
        ).fetchone()
        return row_to_dict(row) or {}


def mark_map_verified(view_key: str, x: int, y: int) -> dict[str, Any]:
    return _set_map_status(view_key, x, y, "verified")


def mark_map_unverified(view_key: str, x: int, y: int) -> dict[str, Any]:
    return _set_map_status(view_key, x, y, "unverified")


def set_current_map(view_key: str, x: int, y: int) -> dict[str, Any]:
    init_db()
    clean_key = str(view_key or "").strip()
    if not clean_key:
        raise ValueError("view_key obligatoire.")
    now = utc_now()
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE maps
            SET status = 'verified', updated_at = ?
            WHERE view_key = ? AND status = 'current' AND NOT (x = ? AND y = ?)
            """,
            (now, clean_key, int(x), int(y)),
        )
        cursor = connection.execute(
            """
            UPDATE maps
            SET status = 'current',
                scan_count = COALESCE(scan_count, 0) + 1,
                last_seen_at = ?,
                updated_at = ?
            WHERE view_key = ? AND x = ? AND y = ?
            """,
            (now, now, clean_key, int(x), int(y)),
        )
        if cursor.rowcount == 0:
            connection.execute(
                """
                INSERT INTO maps (
                    view_key, x, y, status, scan_count, last_seen_at, created_at, updated_at
                )
                VALUES (?, ?, ?, 'current', 1, ?, ?, ?)
                """,
                (clean_key, int(x), int(y), now, now, now),
            )
        row = connection.execute(
            _map_select_clause()
            + " WHERE maps.view_key = ? AND maps.x = ? AND maps.y = ?",
            (clean_key, int(x), int(y)),
        ).fetchone()
        return row_to_dict(row) or {}


def get_maps_for_view(view_key: str) -> list[dict[str, Any]]:
    init_db()
    with connection_scope() as connection:
        rows = connection.execute(
            _map_select_clause()
            + " WHERE maps.view_key = ? ORDER BY maps.y ASC, maps.x ASC",
            (str(view_key),),
        ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def get_maps_around(view_key: str, center_x: int, center_y: int, radius: int = 10) -> list[dict[str, Any]]:
    init_db()
    radius = max(0, int(radius or 0))
    center_x = int(center_x)
    center_y = int(center_y)
    with connection_scope() as connection:
        rows = connection.execute(
            _map_select_clause()
            + """
            WHERE maps.view_key = ?
              AND maps.x BETWEEN ? AND ?
              AND maps.y BETWEEN ? AND ?
            ORDER BY maps.y ASC, maps.x ASC
            """,
            (
                str(view_key),
                center_x - radius,
                center_x + radius,
                center_y - radius,
                center_y + radius,
            ),
        ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def add_map_link(
    from_view_key: str,
    target_view_key: str,
    label: str,
    from_x: int | None = None,
    from_y: int | None = None,
    link_type: str = "entrance",
    marker_x: int | None = None,
    marker_y: int | None = None,
) -> dict[str, Any]:
    init_db()
    clean_from = str(from_view_key or "").strip()
    clean_target = str(target_view_key or "").strip()
    clean_label = str(label or "").strip() or clean_target
    if not clean_from:
        raise ValueError("from_view_key obligatoire.")
    if not clean_target:
        raise ValueError("target_view_key obligatoire.")
    from_x_int = optional_int(from_x)
    from_y_int = optional_int(from_y)
    now = utc_now()
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT id FROM map_links
            WHERE from_view_key = ?
              AND target_view_key = ?
              AND COALESCE(label, '') = COALESCE(?, '')
              AND COALESCE(from_x, -999999) = COALESCE(?, -999999)
              AND COALESCE(from_y, -999999) = COALESCE(?, -999999)
            """,
            (clean_from, clean_target, clean_label, from_x_int, from_y_int),
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO map_links (
                    from_view_key, from_x, from_y, target_view_key, label, link_type,
                    marker_x, marker_y, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_from,
                    from_x_int,
                    from_y_int,
                    clean_target,
                    clean_label,
                    str(link_type or "entrance").strip() or "entrance",
                    optional_int(marker_x),
                    optional_int(marker_y),
                    now,
                    now,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE map_links
                SET link_type = ?, marker_x = ?, marker_y = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(link_type or "entrance").strip() or "entrance",
                    optional_int(marker_x),
                    optional_int(marker_y),
                    now,
                    int(row["id"]),
                ),
            )
        link_row = connection.execute(
            """
            SELECT map_links.*, target.name AS target_name, target.kind AS target_kind
            FROM map_links
            LEFT JOIN map_views AS target ON target.view_key = map_links.target_view_key
            WHERE map_links.from_view_key = ?
              AND map_links.target_view_key = ?
              AND COALESCE(map_links.label, '') = COALESCE(?, '')
              AND COALESCE(map_links.from_x, -999999) = COALESCE(?, -999999)
              AND COALESCE(map_links.from_y, -999999) = COALESCE(?, -999999)
            """,
            (clean_from, clean_target, clean_label, from_x_int, from_y_int),
        ).fetchone()
        return row_to_dict(link_row) or {}


def get_links_for_view(view_key: str) -> list[dict[str, Any]]:
    init_db()
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT map_links.*, target.name AS target_name, target.kind AS target_kind
            FROM map_links
            LEFT JOIN map_views AS target ON target.view_key = map_links.target_view_key
            WHERE map_links.from_view_key = ?
            ORDER BY map_links.link_type COLLATE NOCASE ASC, map_links.label COLLATE NOCASE ASC
            """,
            (str(view_key),),
        ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def reset_database_for_tests(path: Path) -> None:
    global WORLD_DB_PATH, _INITIALIZED_DB_IDENTITY
    with _INIT_LOCK:
        WORLD_DB_PATH = Path(path)
        _INITIALIZED_DB_IDENTITY = ""
        for candidate in (
            WORLD_DB_PATH,
            Path(str(WORLD_DB_PATH) + "-wal"),
            Path(str(WORLD_DB_PATH) + "-shm"),
        ):
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                LOGGER.warning("Suppression base cartographie test impossible: %s", exc)
