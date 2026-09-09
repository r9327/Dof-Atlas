from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"

CANONICAL = {
    "guide_ultime_final.json",
    "guide_ultime_final_audit.json",
    "guide_ultime_gps_route.json",
    "guide_ultime_gps_route_audit.json",
    "guide_ultime_route_forensic_audit.json",
}
KEEP_IF_PRESENT = {
    "guide_ultime_gps_crash.json",
}


def _is_guide_ultime_candidate(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name.casefold()
    return name.startswith("guide_ultime_") or name.startswith("guide-ultime-")


def _unique_destination(folder: Path, name: str) -> Path:
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 2
    while True:
        candidate = folder / f"{stem}__{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def organize(*, apply: bool) -> dict[str, Any]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        [path for path in ARTIFACTS.iterdir() if _is_guide_ultime_candidate(path)],
        key=lambda path: path.name.casefold(),
    )
    keep = [path for path in candidates if path.name in CANONICAL or path.name in KEEP_IF_PRESENT]
    archive = [path for path in candidates if path.name not in CANONICAL and path.name not in KEEP_IF_PRESENT]

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = ARTIFACTS / "archive" / "guide_ultime" / timestamp
    moved: list[dict[str, str]] = []

    if apply and archive:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for source in archive:
            destination = _unique_destination(archive_dir, source.name)
            shutil.move(str(source), str(destination))
            moved.append(
                {
                    "from": str(source.relative_to(ROOT)),
                    "to": str(destination.relative_to(ROOT)),
                }
            )

        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "mode": "archive_only_no_delete",
            "canonical_kept_at_artifacts_root": sorted(CANONICAL),
            "additional_kept_if_present": sorted(KEEP_IF_PRESENT),
            "moved": moved,
        }
        (archive_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "mode": "apply" if apply else "preview",
        "canonical_present": sorted(path.name for path in keep if path.name in CANONICAL),
        "kept_extra": sorted(path.name for path in keep if path.name in KEEP_IF_PRESENT),
        "archive_candidate_count": len(archive),
        "archive_candidates": [path.name for path in archive],
        "archive_directory": str(archive_dir.relative_to(ROOT)) if archive else None,
        "moved": moved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Range les anciens artefacts Guide Ultime sans rien supprimer définitivement."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Déplace réellement les anciens artefacts vers artifacts/archive/guide_ultime/<timestamp>.",
    )
    args = parser.parse_args()
    result = organize(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.apply:
        print("PREVIEW uniquement. Relance avec --apply pour effectuer le rangement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
