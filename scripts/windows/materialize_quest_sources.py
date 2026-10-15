"""Fetch only immutable, SHA-256-pinned Doduda source JSON required at runtime.

data/cache/ is intentionally gitignored. The frozen Windows build MUST materialize
this pinned, public dataset before PyInstaller collects "data;data". Never silently
accept missing files or resolve to the newest (mutable) Doduda release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

LOCK_PATH = Path(__file__).with_name("quest_sources_lock.json")
DEFAULT_DESTINATION = Path("data/cache/dofus_maps/raw/doduda_cli")
SOURCE_REPOSITORY = "dofusdude/dofus3-main"
REQUIRED_SOURCE_NAMES = frozenset({
    "languages/fr.json", "quests.json", "quest_steps.json",
    "quest_objectives.json", "quest_step_rewards.json", "achievements.json",
    "achievement_objectives.json", "achievement_categories.json",
    "quest_categories.json", "quest_objective_types.json", "items.json",
    "jobs.json", "spells.json", "titles.json", "emoticons.json",
    "monsters.json", "npcs.json", "areas.json", "subareas.json",
    "maps_information.json", "char_xp_mappings.json",
})


class QuestSourceBundleError(RuntimeError):
    """Required immutable source data is missing or invalid."""


def load_lock(path: Path = LOCK_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("repository") != SOURCE_REPOSITORY:
        raise QuestSourceBundleError("Untrusted quest source lock identity")
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", str(payload.get("release_tag", ""))):
        raise QuestSourceBundleError("Invalid pinned Doduda release tag")
    files = payload.get("files")
    if not isinstance(files, dict) or set(files) != REQUIRED_SOURCE_NAMES:
        raise QuestSourceBundleError("Incomplete mandatory quest sources lock")
    for relative, entry in files.items():
        asset = relative.removeprefix("languages/")
        if (not isinstance(entry, dict)
                or entry.get("asset") != asset
                or type(entry.get("size")) is not int
                or not 0 < entry["size"] <= 128 * 1024**2
                or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("sha256", "")))):
            raise QuestSourceBundleError(f"Invalid pinned source metadata: {relative}")
    return payload


def _target(root: Path, name: str) -> Path:
    if root.is_symlink():
        raise QuestSourceBundleError("Quest source root must not be a symlink")
    path = root / name
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise QuestSourceBundleError(f"Linked quest source location: {path}")
    return path


def _verify_file(path: Path, entry: dict) -> bool:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != entry["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == entry["sha256"]


def verify_bundle(root: Path, lock: dict) -> int:
    for name, entry in lock["files"].items():
        path = _target(root, name)
        if not _verify_file(path, entry):
            raise QuestSourceBundleError(f"Missing/invalid frozen quest source: {name}")
    return len(lock["files"])


def materialize_bundle(root: Path, lock: dict, *, opener=None) -> int:
    """Download only pinned assets, atomically, with verified size and SHA-256."""
    if root.is_symlink():
        raise QuestSourceBundleError("Quest source root must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    opener = opener or urllib.request.urlopen
    for relative, entry in lock["files"].items():
        target = _target(root, relative)
        if _verify_file(target, entry):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        url = (f"https://github.com/{SOURCE_REPOSITORY}/releases/download/"
               f"{lock['release_tag']}/{entry['asset']}")
        completed = False
        for attempt in range(3):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".quest-source-",
                                                 suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    request = urllib.request.Request(
                        url, headers={"User-Agent": "DofusAtlas-ReleaseBuild/1",
                                      "Accept": "application/octet-stream"},
                    )
                    digest = hashlib.sha256()
                    total = 0
                    with opener(request, timeout=90) as remote:
                        while block := remote.read(1024 * 1024):
                            total += len(block)
                            if total > entry["size"]:
                                raise QuestSourceBundleError(f"Oversized upstream asset: {relative}")
                            output.write(block)
                            digest.update(block)
                if total != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise QuestSourceBundleError(f"SHA-256/size mismatch for pinned quest source: {relative}")
                temporary.replace(target)
                completed = True
                break
            except (OSError, urllib.error.URLError) as exc:
                if attempt == 2:
                    raise QuestSourceBundleError(f"Cannot download pinned quest source: {relative}: {exc}") from exc
                time.sleep(attempt + 1)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        if not completed:
            raise QuestSourceBundleError(f"Unable to materialize quest source: {relative}")
        print(f"VERIFIED source: {relative}", flush=True)
    return verify_bundle(root, lock)


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize the exact frozen quest source contract")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        lock = load_lock()
        count = (verify_bundle(args.destination, lock) if args.verify_only
                 else materialize_bundle(args.destination, lock))
        print(f"VERIFIED: {count} pinned quest source JSON assets ({lock['release_tag']})", flush=True)
        return 0
    except (QuestSourceBundleError, OSError, ValueError, KeyError) as exc:
        print(f"QUEST SOURCE BUNDLE FAILED: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
