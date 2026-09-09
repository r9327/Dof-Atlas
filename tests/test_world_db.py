from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.cartography import world_db


class WorldDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_path = world_db.WORLD_DB_PATH
        self.previous_identity = world_db._INITIALIZED_DB_IDENTITY
        world_db.WORLD_DB_PATH = Path(self.tmp.name) / "world.db"
        world_db._INITIALIZED_DB_IDENTITY = ""

    def tearDown(self) -> None:
        world_db.WORLD_DB_PATH = self.previous_path
        world_db._INITIALIZED_DB_IDENTITY = self.previous_identity
        self.tmp.cleanup()

    def test_connection_uses_wal_and_busy_timeout(self):
        world_db.init_db()
        with world_db.connection_scope() as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(str(journal_mode).casefold(), "wal")
        self.assertGreaterEqual(int(busy_timeout), world_db.DB_BUSY_TIMEOUT_MS)
        self.assertEqual(int(foreign_keys), 1)

    def test_init_db_is_cached_for_same_database_path(self):
        world_db.init_db()
        first_identity = world_db._INITIALIZED_DB_IDENTITY
        self.assertTrue(first_identity)
        world_db.init_db()
        self.assertEqual(world_db._INITIALIZED_DB_IDENTITY, first_identity)

    def test_map_view_upserts_maps_statuses_and_links(self):
        world_db.init_db()
        view = world_db.upsert_map_view(
            "world_amakna",
            "Monde des Douze",
            kind="main_world",
            asset_path="data/cartography/assets/world/amakna/world.png",
        )
        self.assertEqual(view["view_key"], "world_amakna")

        map_row = world_db.upsert_map(
            "world_amakna",
            -2,
            0,
            map_id="88081177",
            rect_json={"x": 1200, "y": 800, "w": 36, "h": 24},
        )
        self.assertEqual(map_row["status"], "unverified")
        self.assertIn('"w": 36', map_row["rect_json"])

        verified = world_db.mark_map_verified("world_amakna", -2, 0)
        self.assertEqual(verified["status"], "verified")
        self.assertIsNotNone(verified["last_seen_at"])

        current = world_db.set_current_map("world_amakna", -2, 0)
        self.assertEqual(current["status"], "current")
        self.assertEqual(current["scan_count"], 1)

        link = world_db.add_map_link(
            "world_amakna",
            "cave_mine_astrub_1",
            "Mine Astrub 1",
            from_x=-2,
            from_y=0,
            link_type="mine",
            marker_x=1220,
            marker_y=815,
        )
        self.assertEqual(link["target_view_key"], "cave_mine_astrub_1")

        maps = world_db.get_maps_for_view("world_amakna")
        links = world_db.get_links_for_view("world_amakna")
        self.assertEqual(len(maps), 1)
        self.assertEqual(len(links), 1)

    def test_legacy_maps_table_is_renamed_before_new_schema(self):
        world_db.WORLD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(world_db.WORLD_DB_PATH)
        try:
            connection.execute("CREATE TABLE maps (id INTEGER PRIMARY KEY, world_id INTEGER, x INTEGER, y INTEGER)")
            connection.commit()
        finally:
            connection.close()

        world_db.init_db()
        world_db.upsert_map_view("world_amakna", "Monde des Douze")
        row = world_db.upsert_map("world_amakna", 1, 2)
        self.assertEqual(row["view_key"], "world_amakna")

        connection = sqlite3.connect(world_db.WORLD_DB_PATH)
        try:
            tables = {
                name
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            connection.close()
        self.assertIn("maps", tables)
        self.assertIn("maps_legacy_world_grid", tables)


if __name__ == "__main__":
    unittest.main()
