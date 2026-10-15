"""Reproducible, fail-closed acquisition of the *runtime* Doduda quest sources.

The source checkout intentionally ignores data/cache; PyInstaller cannot include
untracked files that aren't materialized on its Windows runner. Never let a
successful Qt-only smoke stand in for these mandatory quest sources.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).with_name("quest_assets_lock.json")
RELATIVE_ROOT = Path("data/cache/dofus_maps/raw/doduda_cli")
_MAX_SOURCE_BYTES = 128 * 1024 * 1024


def _static_inventory(source_root: Path, relative_module: str, name: str):
    """Read a literal runtime inventory without importing Qt or loading data."""
    module = ast.parse((source_root / relative_module).read_text(encoding="utf-8"))
    for statement in module.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise ValueError(f"{name} inventory not found in {relative_module}")


def required_sources(source_root: Path) -> tuple[str, ...]:
    """All required Quest AND Success sources, never just the Quest catalogue."""
    quest_entries = _static_inventory(
        source_root, "app/quest_catalog.py", "QUEST_CATALOG_SOURCE_FILES"
    )
    success_entries = _static_inventory(
        source_root,
        "app/modules/encyclopedia/providers/memory_bound_achievement_provider.py",
        "_ACHIEVEMENT_COMPACT_SOURCES",
    )
    detail_entries = _static_inventory(
        source_root,
        "app/modules/encyclopedia/providers/achievement_provider.py",
        "_DETAIL_SOURCE_FILES",
    )
    paths = [entry[1] for entry in quest_entries] + list(success_entries) + list(detail_entries)
    if not all(isinstance(path, str) and path and not Path(path).is_absolute()
               and ".." not in Path(path).parts for path in paths):
        raise ValueError("Unsafe or invalid runtime Quest/Success inventory")
    return tuple(dict.fromkeys(paths))


def read_lock(source_root: Path) -> dict:
    lock = json.loads((source_root / "scripts/windows/quest_assets_lock.json").read_text(encoding="utf-8"))
    if (lock.get("schema_version") != 1 or lock.get("source_repo") != "dofusdude/dofus3-main"
            or not isinstance(lock.get("tag"), str) or not lock["tag"]
            or set(lock.get("assets", {})) != set(required_sources(source_root))):
        raise ValueError("Quest source lock does not match canonical Quest catalog inventory")
    for path, entry in lock["assets"].items():
        if (not isinstance(entry, dict)
                or not isinstance(entry.get("size"), int)
                or not 0 < entry["size"] <= _MAX_SOURCE_BYTES
                or not isinstance(entry.get("sha256"), str)
                or len(entry["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in entry["sha256"])
                or entry.get("asset") != (Path(path).name)):
            raise ValueError(f"Invalid quest asset pin: {path}")
    return lock


def _digest(path: Path, expected_size: int) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected_size:
        return ""
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(part)
    return sha.hexdigest()


def _check_structure(path: Path, filename: str) -> None:
    # Only decode the small structural sources. Large monsters/items datasets
    # remain streaming SHA-256 verified with no full-memory JSON materialization.
    if filename not in {
        "quest_categories.json", "quests.json", "achievements.json",
        "achievement_categories.json", "achievement_objectives.json",
        "languages/fr.json",
    }:
        return
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if filename == "languages/fr.json":
        valid = isinstance(payload, dict) and isinstance(payload.get("entries"), dict)
    else:
        valid = (isinstance(payload, dict)
                 and isinstance(payload.get("references"), dict)
                 and isinstance(payload["references"].get("RefIds"), list))
    if not valid:
        raise ValueError(f"Unsupported Doduda JSON layout: {filename}")


def provision(source_root: Path, *, download: bool) -> int:
    lock = read_lock(source_root)
    repo, tag = lock["source_repo"], lock["tag"]
    for name, info in lock["assets"].items():
        dest = source_root / RELATIVE_ROOT / name
        if _digest(dest, info["size"]) != info["sha256"]:
            if not download:
                raise FileNotFoundError(f"Mandatory frozen Quest source missing/stale: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://github.com/{repo}/releases/download/{tag}/{info['asset']}"
            request = urllib.request.Request(url, headers={
                "User-Agent": "DofusAtlas-Build/1.0",
                "Accept": "application/octet-stream",
            })
            fd, filename = tempfile.mkstemp(prefix=".atlas-quest-", suffix=".tmp", dir=dest.parent)
            try:
                hasher = hashlib.sha256()
                size = 0
                with os.fdopen(fd, "wb") as output:
                    try:
                        with urllib.request.urlopen(request, timeout=90) as stream:
                            while True:
                                block = stream.read(1024 * 1024)
                                if not block:
                                    break
                                size += len(block)
                                if size > info["size"]:
                                    raise ValueError(f"Unexpected oversized quest asset: {name}")
                                output.write(block)
                                hasher.update(block)
                    except (urllib.error.URLError, OSError) as exc:
                        raise RuntimeError(f"Cannot retrieve pinned quest source {name}: {exc}") from exc
                    output.flush()
                    os.fsync(output.fileno())
                if size != info["size"] or hasher.hexdigest() != info["sha256"]:
                    raise ValueError(f"Pinned quest asset failed SHA-256 verification: {name}")
                _check_structure(Path(filename), name)
                os.replace(filename, dest)
            finally:
                Path(filename).unlink(missing_ok=True)
        _check_structure(dest, name)
    print(f"VERIFIED: {len(lock['assets'])} pinned Doduda quest sources ({tag})")
    return len(lock["assets"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="Source checkout, or extracted PyInstaller _internal root")
    parser.add_argument("--download", action="store_true",
                        help="Fetch missing pinned sources during trusted Windows build")
    parser.add_argument("--lock-root", type=Path, default=REPO_ROOT,
                        help="Source checkout containing the lock and Quest catalog inventory")
    args = parser.parse_args()
    # Verify under the packaged root, but load pins from the source checkout.
    try:
        source = args.lock_root.resolve()
        if source == args.root.resolve():
            provision(source, download=args.download)
        else:
            lock = read_lock(source)
            for name, info in lock["assets"].items():
                asset = args.root / RELATIVE_ROOT / name
                if _digest(asset, info["size"]) != info["sha256"]:
                    raise FileNotFoundError(f"Packaged Quest asset missing/corrupt: {asset}")
                _check_structure(asset, name)
            print(f"VERIFIED: {len(lock['assets'])} frozen Quest assets")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"QUEST ASSET CERTIFICATION FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
