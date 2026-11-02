"""Import rights-cleared, fully authored Ganymède routes into Atlas offline data.

Only explicit author-provided JSON files are accepted. No scraping, quest-list
fallback, guessed instructions or unreviewed facts are promoted to gameplay.

Use --apply to write; dry-run is the default. --strict requires all 95 routes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from app.modules.encyclopedia.views.guide_library_sources import (
    INDEX_PATH, load_ganymede_listings, load_ganymede_local_instructions,
)


def import_authored_routes(
    source_dir: Path,
    *,
    index_path: Path = INDEX_PATH,
    target_dir: Path | None = None,
    strict: bool = True,
    apply: bool = False,
    allow_overwrite: bool = False,
    expected_routes: int = 95,
) -> dict:
    """Validate *all* offered files before writing any output.

    Every payload must match its canonical source ID, step count, URL and
    complete authored-action schema. The operation never modifies user saves.
    Existing files require an opt-in to overwrite (no silent replacement).
    """
    source = Path(source_dir).resolve(strict=True)
    target = (Path(target_dir) if target_dir is not None
              else Path(index_path).parent).resolve(strict=False)
    listings = load_ganymede_listings(index_path)
    if len(listings) != expected_routes:
        raise ValueError("Unexpected source index size")
    if not source.is_dir():
        raise ValueError("Source must be a directory")
    if source == target:
        raise ValueError("Source and destination must differ")

    allowed = {f"ganymede_{entry.source_id}_instructions.json": entry
               for entry in listings}
    supplied = sorted(source.glob("ganymede_*_instructions.json"))
    if not supplied:
        raise ValueError("No authored route files supplied")
    rejected = sorted(path.name for path in supplied
                      if path.name not in allowed or not path.is_file()
                      or path.is_symlink())
    missing = sorted(entry.source_id for name, entry in allowed.items()
                     if not (source / name).is_file())
    if rejected:
        raise ValueError("Unknown or unsafe route files: " + ", ".join(rejected))
    if strict and missing:
        raise ValueError(f"Missing {len(missing)} authored routes")

    planned = []
    for path in supplied:
        entry = allowed[path.name]
        validated = load_ganymede_local_instructions(entry, data_dir=source)
        if validated is None or len(validated) != entry.step_count:
            raise ValueError(f"Incomplete guide {entry.source_id}")
        blob = path.read_bytes()
        # Bound the artifact being imported. No HTML, executable or transient
        # data leaves this controlled JSON-only route list.
        if len(blob) > 8_000_000:
            raise ValueError(f"Oversized route {entry.source_id}")
        target_path = target / path.name
        if target_path.exists():
            if target_path.is_symlink() or not target_path.is_file():
                raise ValueError(f"Unsafe existing route: {target_path}")
            existing = target_path.read_bytes()
            if existing == blob:
                state = "unchanged"
            elif not allow_overwrite:
                raise FileExistsError(f"Route already exists: {target_path}")
            else:
                state = "update"
        else:
            state = "new"
        previous_sha256 = (
            hashlib.sha256(existing).hexdigest() if state == "update" else None
        )
        planned.append({
            "previous_sha256": previous_sha256,
            "source_id": entry.source_id,
            "filename": path.name,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "steps": len(validated),
            "state": state,
        })

    # Preflight all offered files before touching any published route. Stage
    # *all* changed files, then publish. A recoverable mid-batch failure restores
    # previously published files; no writes touch user progress or guide UI.
    changed = [item for item in planned if item["state"] != "unchanged"]
    if apply and changed:
        if target.is_symlink():
            raise ValueError("Destination cannot be a symlink")
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ganymede-stage-", dir=target) as staging:
            stage = Path(staging)
            for item in changed:
                name = item["filename"]
                incoming = stage / name
                with (source / name).open("rb") as reader, incoming.open("wb") as writer:
                    shutil.copyfileobj(reader, writer)
                    writer.flush()
                    os.fsync(writer.fileno())
                if hashlib.sha256(incoming.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"Route changed during import: {source / name}")
                destination = target / name
                backup = stage / (name + ".previous")
                if item["state"] == "update":
                    if destination.is_symlink() or not destination.is_file():
                        raise ValueError(f"Destination changed: {destination}")
                    shutil.copyfile(destination, backup)
                    if (hashlib.sha256(backup.read_bytes()).hexdigest()
                            != item["previous_sha256"]
                            or hashlib.sha256(destination.read_bytes()).hexdigest()
                            != item["previous_sha256"]):
                        raise ValueError(f"Destination changed during staging: {destination}")
                elif destination.exists() or destination.is_symlink():
                    raise FileExistsError(f"Unexpected destination: {destination}")

            published = []
            try:
                for item in changed:
                    name = item["filename"]
                    destination = target / name
                    backup = stage / (name + ".previous")
                    if item["state"] == "new":
                        if destination.exists() or destination.is_symlink():
                            raise FileExistsError(f"Unexpected destination: {destination}")
                    elif (destination.is_symlink() or not destination.is_file()
                          or hashlib.sha256(destination.read_bytes()).hexdigest()
                          != hashlib.sha256(backup.read_bytes()).hexdigest()):
                        raise ValueError(f"Destination modified concurrently: {destination}")
                    os.replace(stage / name, destination)
                    published.append(item)
            except BaseException:
                rollback_errors = []
                for item in reversed(published):
                    dest = target / item["filename"]
                    try:
                        if item["state"] == "update":
                            os.replace(stage / (item["filename"] + ".previous"), dest)
                        else:
                            dest.unlink()
                    except OSError as exc:
                        rollback_errors.append(f"{dest}: {exc}")
                if rollback_errors:
                    raise OSError("Import rollback incomplete: " + "; ".join(rollback_errors))
                raise
    return {
        "status": "IMPORTED" if apply else "DRY_RUN",
        "strict": strict,
        "source_inventory": len(listings),
        "supplied_routes": len(planned),
        "verified_steps": sum(item["steps"] for item in planned),
        "missing_routes": missing,
        "created": sum(item["state"] == "new" for item in planned),
        "updated": sum(item["state"] == "update" for item in planned),
        "unchanged": sum(item["state"] == "unchanged" for item in planned),
        "routes": planned,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true",
                        help="Import reviewed subset; default requires all 95")
    parser.add_argument("--apply", action="store_true",
                        help="Write validated JSON routes; default is dry-run")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()
    result = import_authored_routes(
        args.source_dir, index_path=args.index, target_dir=args.target_dir,
        strict=not args.allow_partial, apply=args.apply,
        allow_overwrite=args.allow_overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
