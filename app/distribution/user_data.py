"""Initialize durable user data once per installed version, without overwrites."""
from __future__ import annotations

import os
from contextlib import closing
import shutil
import sqlite3
import tempfile
from pathlib import Path

_USER_PATHS = (
    ("data/local", "data/local"),
    ("data/routes", "data/routes"),
    ("data/client_profiles.json", "data/client_profiles.json"),
    ("data/client_index.json", "data/client_index.json"),
    ("data/client_index.ini", "data/client_index.ini"),
    ("data/bootstrap_status.txt", "data/bootstrap_status.txt"),
    ("config", "config"),
)


def _seed_craft_database(executable: Path, user_root: Path) -> None:
    """Copy the official public seed once, atomically, never overwrite progress.

    The public release manifest authenticates the packaged seed. Guard schema
    before importing so a broken release cannot install an unusable Craft DB.
    """
    source = executable.parent / "_internal" / "data" / "bootstrap" / "craft_seed.sqlite"
    dest = user_root / "data" / "local" / "dofus_data.sqlite"
    if not source.is_file():
        # Older builds carry no Craft seed; retain compatibility on upgrades.
        return
    if dest.is_symlink():
        raise ValueError("Unsafe Craft SQLite destination")
    if dest.exists():
        return
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Bundled Craft SQLite is corrupt")
            for table in ("items", "jobs", "recipes", "recipe_ingredients"):
                if not db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    raise ValueError(f"Bundled Craft data missing: {table}")
    except sqlite3.DatabaseError as exc:
        raise ValueError("Bundled Craft database invalid") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=".atlas-craft-seed-", dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as original:
            shutil.copyfileobj(original, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        # Never replace an existing user's SQLite, including if initialized by
        # an earlier installation during this launch.
        if not dest.exists():
            os.replace(filename, dest)
    finally:
        Path(filename).unlink(missing_ok=True)


def _migrate_world_database(user_root: Path, sources: list[Path]) -> None:
    """Backup the previous version's WAL-backed scan DB before an update.

    SQLite backup (rather than copy2) includes pending WAL state. The frozen
    executable no longer writes its own version's `data/dofus_atlas_world.db`.
    """
    target = user_root / "data" / "dofus_atlas_world.db"
    if target.is_symlink():
        raise ValueError("Unsafe map database destination")
    if target.exists():
        return
    for root in sources:
        source = root / "data" / "dofus_atlas_world.db"
        if source.is_symlink() or not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".atlas-world-migrate-", suffix=".sqlite",
                                    dir=target.parent)
        os.close(fd)
        try:
            with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as old:
                with closing(sqlite3.connect(name)) as new:
                    old.backup(new)
                    new.commit()
                    if new.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Existing map scan database failed integrity check")
                    tables = {row[0] for row in new.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )}
                    if not {"maps", "map_views"}.issubset(tables):
                        raise ValueError("Legacy map database has no expected tables")
            if not target.exists():
                os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
        return


def prepare_user_data(executable: Path, user_root: Path,
                      legacy_root: Path | None = None,
                      previous_install_root: Path | None = None) -> None:
    """Seed missing user files from a legacy source clone, then from the bundle.

    Existing saved profiles/progress always take precedence. Sources are scanned
    only on the first launch of each frozen package; later launches stay fast.
    """
    user_root.mkdir(parents=True, exist_ok=True)
    map_sources = []
    if previous_install_root is not None:
        map_sources.append(previous_install_root)
    if legacy_root is not None and (legacy_root / "DOFUS.bat").is_file():
        map_sources.append(legacy_root)
    _migrate_world_database(user_root, map_sources)
    marker = user_root / ".initialized" / (executable.parent.parent.name + ".ready")
    if marker.is_file():
        _seed_craft_database(executable, user_root)
        return
    sources = [executable.parent / "_internal"]
    if legacy_root is not None and (legacy_root / "DOFUS.bat").is_file():
        sources.insert(0, legacy_root)
    for root in sources:
        for source_rel, dest_rel in _USER_PATHS:
            src = root / source_rel
            dst = user_root / dest_rel
            if src.is_symlink():
                continue
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(src, dst)
            elif src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for child in src.rglob("*"):
                    if child.is_symlink() or not child.is_file():
                        continue
                    output = dst / child.relative_to(src)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if not output.exists():
                        shutil.copy2(child, output)
    _seed_craft_database(executable, user_root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ready\n", encoding="utf-8")
