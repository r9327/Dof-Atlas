from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path

from local_dofus_data.data_store import DataStore


class DataStoreBackupTests(unittest.TestCase):
    def test_backup_contains_committed_wal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "source.sqlite"
            backup_path = Path(tmp) / "backup.sqlite"
            store = DataStore(db_path=db_path)
            connection = store.connect()
            connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample(value) VALUES (?)", ("latest",))
            connection.commit()

            created = store.backup(backup_path)
            self.assertEqual(created, backup_path)
            with closing(sqlite3.connect(created)) as backup:
                row = backup.execute("SELECT value FROM sample").fetchone()
            self.assertEqual(row, ("latest",))
            store.close()


if __name__ == "__main__":
    unittest.main()
