"""Atlas Guide Importer: offline, fail-closed preflight for PR #337 routes.

No scraping, network, Qt widgets, user progress or parallel guide renderer.
This pipeline delegates actual validation/publication to the PR #337 owners.
A matching reference manifest proves *byte parity only*, never editorial
accuracy, redistribution rights or Windows/DOFUS certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.modules.encyclopedia.views.guide_library_sources import (
    INDEX_PATH, load_ganymede_listings, load_ganymede_local_instructions,
)
from tools.import_ganymede_authored_routes import import_authored_routes

_HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _hash(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _step_hash(step: dict[str, Any]) -> str:
    return _hash(json.dumps(
        step, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8"))


def _load_reference(path: Path) -> dict[int, dict[str, Any]]:
    """Reference is supplied independently; never inferred from the offered pack."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
        raise ValueError("Missing, unsafe or oversized reference manifest")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Invalid reference manifest schema")
    guides = data.get("guides")
    if not isinstance(guides, list) or not guides:
        raise ValueError("Empty reference manifest")
    indexed: dict[int, dict[str, Any]] = {}
    for row in guides:
        if not isinstance(row, dict):
            raise ValueError("Invalid reference guide entry")
        gid = row.get("source_guide_id")
        fingerprint = row.get("file_sha256")
        hashes = row.get("step_sha256")
        if (type(gid) is not int or gid <= 0 or gid in indexed
                or not isinstance(fingerprint, str)
                or not _HEX_SHA.fullmatch(fingerprint)
                or not isinstance(hashes, list) or not hashes
                or any(not isinstance(h, str) or not _HEX_SHA.fullmatch(h)
                       for h in hashes)):
            raise ValueError("Duplicate or malformed reference fingerprint")
        indexed[gid] = row
    return indexed


def _check_projection(source_id: int, title: str, steps: tuple[dict, ...]) -> dict:
    """Assert the PR #337 data bridge preserves every ordered action and position.

    Styling/click targets remain owned by SharedGuideManualCard and are NOT
    claimed verified by this pure-data check.
    """
    from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
        project_ganymede_authored_cards,
    )

    cards = project_ganymede_authored_cards(source_id, title, steps)
    if len(cards) != len(steps):
        raise ValueError(f"{source_id}: card count changed")
    count = 0
    copied_targets = 0
    for number, (step, card) in enumerate(zip(steps, cards), 1):
        actions = step["actions"]
        rows = card.get("manual_lines")
        if (card.get("index") != number
                or card.get("manual_stage_id") != f"ganymede_{source_id}_step_{number:04d}"
                or card.get("auto_completion_allowed") is not False
                or card.get("manual_source") is not True
                or not isinstance(rows, list) or len(rows) != len(actions) + 1
                or card.get("manual_sections", {}).get("now") != rows):
            raise ValueError(f"{source_id}:{number}: shared card contract mismatch")
        resource_names = card.get("manual_resource_names", ())
        for index, action in enumerate(actions, 1):
            row = rows[index]
            coords = action.get("coordinates")
            expected_position = f"[{coords[0]},{coords[1]}]" if coords is not None else ""
            if (row.get("position") != expected_position
                    or row.get("kind") != ("combat" if action["kind"] == "fight" else "action")
                    or not isinstance(row.get("text"), str)
                    or not row["text"].endswith(": " + action["text"].strip())):
                raise ValueError(f"{source_id}:{number}:{index}: action lost or reordered")
            items = action.get("items") or []
            if items and row.get("items") != items:
                raise ValueError(f"{source_id}:{number}:{index}: structured items lost")
            for item in items:
                if item.get("name") not in resource_names:
                    raise ValueError(f"{source_id}:{number}:{index}: item lost")
            # Explicit author-provided copy targets must not be silently lost.
            copy_values = action.get("copy_values") or []
            if copy_values:
                row_values = row.get("copy_values")
                if row_values != copy_values:
                    raise ValueError(
                        f"{source_id}:{number}:{index}: explicit copy target not projected; "
                        "update the canonical PR337 bridge first"
                    )
                copied_targets += len(copy_values)
            count += 1
    return {"projected_cards": len(cards), "projected_actions": count,
            "explicit_copy_targets_preserved": copied_targets}


def inspect_import(
    source_dir: Path,
    *,
    manifest_path: Path | None = None,
    index_path: Path = INDEX_PATH,
    target_dir: Path | None = None,
    strict: bool = True,
    expected_routes: int = 95, allow_overwrite: bool = False,
) -> dict:
    """Preflight in read-only mode, including the existing importer gate."""
    source = Path(source_dir)
    plan = import_authored_routes(
        source, index_path=index_path, target_dir=target_dir,
        strict=strict, expected_routes=expected_routes, apply=False,
        allow_overwrite=allow_overwrite,
    )
    catalog = {entry.source_id: entry for entry in load_ganymede_listings(index_path)}
    manifest = _load_reference(manifest_path) if manifest_path is not None else None
    supplied = {row["source_id"] for row in plan["routes"]}
    if manifest is not None and set(manifest) != supplied:
        raise ValueError("Reference inventory differs from offered routes")

    inspected: list[dict] = []
    for record in plan["routes"]:
        gid = record["source_id"]
        entry = catalog[gid]
        path = source / record["filename"]
        steps = load_ganymede_local_instructions(entry, data_dir=source)
        if steps is None:
            raise ValueError(f"{gid}: no complete route")
        projection = _check_projection(gid, entry.title, steps)
        fingerprint = _hash(path.read_bytes())
        if fingerprint != record["sha256"]:
            raise ValueError(f"{gid}: source file changed during preflight")
        if manifest is not None:
            ref = manifest[gid]
            if (ref["file_sha256"] != fingerprint
                    or ref.get("source_url") != entry.source_url
                    or len(ref["step_sha256"]) != len(steps)
                    or ref["step_sha256"] != [_step_hash(s) for s in steps]):
                raise ValueError(f"{gid}: independent reference mismatch")
        inspected.append({**record, **projection,
                          "reference": "HASH_MATCH" if manifest is not None else "NOT_VERIFIED"})
    return {
        "schema_version": 1,
        "status": "PREFLIGHT_PASS" if manifest is not None else "REFERENCE_REQUIRED",
        "reference_level": (
            "BYTE_AND_STEP_HASH_MATCH_ONLY" if manifest is not None else "NOT_VERIFIED"
        ),
        "source_parity_certified": False,
        "gameplay_certified": False,
        "rights_verified": False,
        "expected_routes": expected_routes,
        "supplied_routes": len(inspected),
        "validated_steps": sum(r["steps"] for r in inspected),
        "validated_actions": sum(r["projected_actions"] for r in inspected),
        "missing_routes": plan["missing_routes"],
        "routes": inspected,
    }


def run_pipeline(
    source_dir: Path, *, manifest_path: Path | None = None,
    index_path: Path = INDEX_PATH, target_dir: Path | None = None,
    strict: bool = True, expected_routes: int = 95,
    apply: bool = False, allow_overwrite: bool = False,
) -> dict:
    report = inspect_import(
        source_dir, manifest_path=manifest_path, index_path=index_path,
        target_dir=target_dir, strict=strict, expected_routes=expected_routes,
        allow_overwrite=allow_overwrite,
    )
    if not apply:
        return report
    if manifest_path is None:
        raise ValueError("Publication blocked: independent reference required")
    result = import_authored_routes(
        source_dir, index_path=index_path, target_dir=target_dir,
        strict=strict, expected_routes=expected_routes,
        apply=True, allow_overwrite=allow_overwrite,
    )
    if {r["source_id"]: r["sha256"] for r in result["routes"]} != {
            r["source_id"]: r["sha256"] for r in report["routes"]}:
        raise ValueError("Source changed between preflight and import")
    destination = Path(target_dir) if target_dir is not None else Path(index_path).parent
    for row in report["routes"]:
        published = destination / row["filename"]
        if published.is_symlink() or _hash(published.read_bytes()) != row["sha256"]:
            raise ValueError(f"Published route hash mismatch: {row['source_id']}")
    return {**report, "status": "IMPORTED_HASH_VERIFIED",
            "created": result["created"], "updated": result["updated"],
            "unchanged": result["unchanged"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(
            args.source_dir, manifest_path=args.reference_manifest,
            index_path=args.index, target_dir=args.target_dir,
            strict=not args.allow_partial, apply=args.apply,
            allow_overwrite=args.allow_overwrite,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "REFERENCE_REQUIRED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
