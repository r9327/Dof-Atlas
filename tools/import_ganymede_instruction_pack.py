"""Import a complete *authorized* Ganymède instruction pack into Atlas.

A pack is a folder of 95 independently authored/authorized
`ganymede_<id>_instructions.json` files conforming to
`docs/guides/GANYMEDE_AUTHORING.md`. This command does not download/scrape
Ganymède or claim that public pages are licensed for redistribution.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from app.modules.encyclopedia.views.guide_library_sources import (
    INDEX_PATH, load_ganymede_listings, load_ganymede_local_instructions,
)


def examine_pack(
    source: Path, *, index_path: Path = INDEX_PATH, expected_routes: int = 95,
) -> dict:
    """Validate all routes before any destination is touched."""
    listings = load_ganymede_listings(index_path)
    required = {f"ganymede_{entry.source_id}_instructions.json" for entry in listings}
    supplied = {p.name for p in source.glob("ganymede_*_instructions.json") if p.is_file()}
    missing, unexpected = sorted(required - supplied), sorted(supplied - required)
    invalid = []
    complete = 0
    for entry in listings:
        if f"ganymede_{entry.source_id}_instructions.json" not in supplied:
            continue
        try:
            steps = load_ganymede_local_instructions(entry, data_dir=source)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            invalid.append({"source_id": entry.source_id, "error": str(exc)})
            continue
        if steps is None:
            invalid.append({"source_id": entry.source_id, "error": "No instructions"})
            continue
        complete += len(steps)
    ok = (
        len(listings) == expected_routes
        and not missing and not unexpected and not invalid
        and complete == sum(entry.step_count or 0 for entry in listings)
    )
    return {
        "status": "PASS" if ok else "INCOMPLETE",
        "inventory_routes": len(listings),
        "expected_routes": expected_routes,
        "validated_steps": complete,
        "missing_files": missing,
        "unexpected_files": unexpected,
        "invalid_routes": invalid,
    }


def install_pack(
    source: Path, destination: Path, *, index_path: Path = INDEX_PATH,
    expected_routes: int = 95,
) -> dict:
    """Preflight entire pack; never silently overwrite existing instructions."""
    report = examine_pack(source, index_path=index_path, expected_routes=expected_routes)
    if report["status"] != "PASS":
        raise ValueError("Refusing incomplete/unverified instruction pack")
    filenames = sorted(
        f"ganymede_{entry.source_id}_instructions.json"
        for entry in load_ganymede_listings(index_path)
    )
    if destination.resolve() == source.resolve():
        raise ValueError("Source and destination must differ")
    if any((destination / name).exists() for name in filenames):
        raise FileExistsError("Refusing to replace already installed instructions")
    destination.mkdir(parents=True, exist_ok=True)
    # Stage the entire data set before publication, preserving other guide data.
    # `os.replace` publishes each completed file atomically. If a filesystem
    # error occurs, remove only this invocation's previously published files.
    with tempfile.TemporaryDirectory(prefix=".ganymede-stage-", dir=destination) as stage:
        staged = Path(stage)
        for name in filenames:
            (staged / name).write_bytes((source / name).read_bytes())
        published = []
        try:
            for name in filenames:
                target = destination / name
                if target.exists():
                    raise FileExistsError(str(target))
                os.replace(staged / name, target)
                published.append(target)
        except OSError:
            for target in reversed(published):
                target.unlink(missing_ok=True)
            raise
    return {**report, "installed_files": len(filenames), "destination": str(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Folder containing authorized route JSON")
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--destination", type=Path, default=INDEX_PATH.parent)
    parser.add_argument("--install", action="store_true", help="Install after full preflight")
    args = parser.parse_args()
    try:
        report = (install_pack(args.source, args.destination, index_path=args.index)
                  if args.install else examine_pack(args.source, index_path=args.index))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
