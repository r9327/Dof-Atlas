from __future__ import annotations

import sqlite3
from collections.abc import Callable


BASE_SCHEMA_VERSION = 1
Migration = Callable[[sqlite3.Connection], None]

# Target-version -> migration. A migration must be transactional/idempotent and
# transform an existing database from target_version - 1 to target_version.
# Version 1 is the baseline represented by CREATE_TABLES_SQL.
MIGRATIONS: dict[int, Migration] = {}


def migration_for(target_version: int) -> Migration | None:
    return MIGRATIONS.get(int(target_version))


__all__ = ["BASE_SCHEMA_VERSION", "MIGRATIONS", "Migration", "migration_for"]
