from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_dofus_data.data_store import DataStore


class DataStoreMigrationTests(unittest.TestCase):
    def test_new_database_records_baseline_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DataStore(Path(directory) / "local.sqlite")
            try:
                store.initialize()
                row = store.query_one("SELECT MAX(version) AS version FROM schema_migrations")
                self.assertIsNotNone(row)
                self.assertEqual(int(row["version"]), 1)
            finally:
                store.close()

    def test_missing_future_migration_fails_instead_of_marking_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DataStore(Path(directory) / "local.sqlite")
            try:
                store.initialize()
                with patch("local_dofus_data.data_store.SCHEMA_VERSION", 2):
                    with self.assertRaisesRegex(RuntimeError, "Migration SQLite manquante"):
                        store.initialize()
                row = store.query_one("SELECT MAX(version) AS version FROM schema_migrations")
                self.assertEqual(int(row["version"]), 1)
            finally:
                store.close()

    def test_registered_future_migration_is_applied_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DataStore(Path(directory) / "local.sqlite")
            try:
                store.initialize()

                def migration(connection) -> None:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS migration_probe (id INTEGER PRIMARY KEY)"
                    )

                with (
                    patch("local_dofus_data.data_store.SCHEMA_VERSION", 2),
                    patch(
                        "local_dofus_data.data_store.migration_for",
                        side_effect=lambda version: migration if int(version) == 2 else None,
                    ),
                ):
                    store.initialize()

                row = store.query_one("SELECT MAX(version) AS version FROM schema_migrations")
                self.assertEqual(int(row["version"]), 2)
                table = store.query_one(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_probe'"
                )
                self.assertIsNotNone(table)
            finally:
                store.close()

    def test_connections_use_wal_and_busy_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DataStore(Path(directory) / "local.sqlite")
            try:
                connection = store.connect()
                busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertGreaterEqual(int(busy_timeout), 10_000)
                self.assertEqual(str(journal_mode).casefold(), "wal")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
