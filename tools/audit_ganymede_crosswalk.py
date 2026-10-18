"""Audit explicit Ganymède -> Atlas guide references (no external scraping).

Only metadata is mapped. The result MUST NOT be treated as evidence that
external quest steps or an optimized route have been imported or certified.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CROSSWALK = Path("data/encyclopedia/guides/ganymede_source_crosswalk.json")
CATALOG = Path("data/encyclopedia/guides/catalog.json")
MAIN_INDEX = Path("data/encyclopedia/guides/ganymede_main_index.json")
_SOURCE_PATH = re.compile(r"^/guides/([1-9][0-9]*)/?$")


def audit_ganymede_crosswalk(root: Path) -> dict[str, object]:
    """Validate URLs, canonical guide IDs and explicit non-certified states."""
    issues: list[dict[str, str]] = []
    crosswalk_path, catalog_path = root / CROSSWALK, root / CATALOG
    for filename, path in (("crosswalk", crosswalk_path), ("catalog", catalog_path), ("main_index", root / MAIN_INDEX)):
        if not path.is_file():
            return {
                "status": "FAIL",
                "evidence_type": "metadata_only",
                "entries": 0,
                "verified_routes": 0,
                "issues": [{"code": "missing_file", "detail": f"{filename}: {path}"}],
            }
    try:
        payload = json.loads(crosswalk_path.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        index_payload = json.loads((root / MAIN_INDEX).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return {
            "status": "FAIL",
            "evidence_type": "metadata_only",
            "entries": 0,
            "verified_routes": 0,
            "issues": [{"code": "invalid_json", "detail": str(exc)}],
        }

    if payload.get("schema_version") != 1:
        issues.append({"code": "schema", "detail": "unsupported crosswalk schema_version"})
    source = payload.get("source", {})
    if not isinstance(source, dict) or source.get("role") != "route_reference_priority":
        issues.append({"code": "source_role", "detail": "unexpected route reference role"})
    available = {row["id"] for row in catalog.get("guides", [])
                 if isinstance(row, dict) and isinstance(row.get("id"), str)}
    seen_ids: set[int] = set()
    seen_keys: set[str] = set()
    rows = payload.get("guides", [])
    if not isinstance(rows, list) or not rows:
        issues.append({"code": "empty_inventory", "detail": "expected a nonempty guide list"})
        rows = []

    for index, row in enumerate(rows):
        where = f"guides[{index}]"
        if not isinstance(row, dict):
            issues.append({"code": "invalid_row", "detail": where})
            continue
        key = row.get("external_key")
        gid = row.get("ganymede_guide_id")
        if not isinstance(key, str) or not key.strip() or key in seen_keys:
            issues.append({"code": "external_key", "detail": where})
        else:
            seen_keys.add(key)
        if type(gid) is not int or gid <= 0 or gid in seen_ids:
            issues.append({"code": "external_id", "detail": where})
        else:
            seen_ids.add(gid)
        parsed = urlparse(str(row.get("source_url", "")))
        match = _SOURCE_PATH.fullmatch(parsed.path)
        if (parsed.scheme != "https"
                or parsed.netloc != "ganymede-app.com"
                or not match
                or parsed.query or parsed.fragment
                or type(gid) is not int
                or int(match.group(1)) != gid):
            issues.append({"code": "source_url", "detail": where})
        targets = row.get("atlas_guide_ids")
        if not isinstance(targets, list) or not targets or len(set(map(str, targets))) != len(targets):
            issues.append({"code": "atlas_targets", "detail": where})
            continue
        for target in targets:
            if target not in available:
                issues.append({"code": "unknown_atlas_guide", "detail": f"{where}: {target}"})
        # A URL + title is never sufficient to certify source steps or route parity.
        if (row.get("status") != "metadata_only"
                or row.get("quest_mapping_verified") is not False
                or row.get("route_parity_verified") is not False):
            issues.append({"code": "unproved_certification", "detail": where})

    coverage = payload.get("coverage", {})
    if not isinstance(coverage, dict) or coverage.get("asserted_complete") is not False:
        issues.append({"code": "invalid_coverage", "detail": "inventory must not claim exhaustive coverage"})
    index_rows = index_payload.get("guides", [])
    index_ids: set[int] = set()
    if not isinstance(index_rows, list) or not index_rows:
        issues.append({"code": "empty_main_index", "detail": "source index absent/empty"})
        index_rows = []
    for index, row in enumerate(index_rows):
        where = f"main_index[{index}]"
        if not isinstance(row, dict):
            issues.append({"code": "invalid_main_index_row", "detail": where})
            continue
        external_id = row.get("ganymede_guide_id")
        parsed = urlparse(str(row.get("source_url", "")))
        match = _SOURCE_PATH.fullmatch(parsed.path)
        if (type(external_id) is not int or external_id <= 0
                or external_id in index_ids):
            issues.append({"code": "main_index_id", "detail": where})
        else:
            index_ids.add(external_id)
        if (parsed.scheme != "https" or parsed.netloc != "ganymede-app.com"
                or not match or type(external_id) is not int
                or int(match.group(1)) != external_id
                or parsed.query or parsed.fragment):
            issues.append({"code": "main_index_url", "detail": where})
        if row.get("status") != "metadata_only":
            issues.append({"code": "main_index_false_certification", "detail": where})
    snapshot = index_payload.get("snapshot", {})
    if not isinstance(snapshot, dict) or snapshot.get("total_main_guides") != len(index_rows):
        issues.append({"code": "index_count_mismatch", "detail": "total_main_guides differs from indexed rows"})
    if not isinstance(snapshot, dict) or snapshot.get("guide_routes_certified") != 0:
        issues.append({"code": "index_false_route_certification", "detail": "no routes verified"})
    absent = sorted(seen_ids - index_ids)
    if absent:
        issues.append({"code": "crosswalk_guide_absent_from_index", "detail": str(absent)})

    return {
        "status": "FAIL" if issues else "PASS_METADATA_ONLY",
        "evidence_type": "metadata_only",
        "entries": len(rows),
        "indexed_main_guides": len(index_rows),
        "unmapped_main_guides": len(index_ids - seen_ids),
        "mapped_atlas_guides": len({
            target for row in rows if isinstance(row, dict)
            for target in row.get("atlas_guide_ids", [])
        }),
        "verified_routes": 0,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_ganymede_crosswalk(args.root.resolve())
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0 if report["status"] == "PASS_METADATA_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
