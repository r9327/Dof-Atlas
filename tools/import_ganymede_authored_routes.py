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
        planned.append({
            "source_id": entry.source_id,
            "filename": path.name,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "steps": len(validated),
            "state": state,
        })

    # No mutation until every supplied document has passed validation.
    changed = [item for item in planned if item["state"] != "unchanged"]
    if apply and changed:
        target.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError("Destination cannot be a symlink")
        for item in changed:
            src = source / item["filename"]
            destination = target / item["filename"]
            # Stage on the same volume and publish each JSON atomically.
            fd, tmp = tempfile.mkstemp(prefix=".ganymede-", suffix=".json",
                                       dir=target)
            try:
                with os.fdopen(fd, "wb") as handle:
                    with src.open("rb") as reader:
                        shutil.copyfileobj(reader, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                if hashlib.sha256(Path(tmp).read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"Route changed during import: {src}")
                os.replace(tmp, destination)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
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
