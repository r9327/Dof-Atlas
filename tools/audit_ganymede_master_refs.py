"""Validate observed public links from the Ganymède master guide MG0.

This is *not* a scraper and MUST NOT infer quest prerequisites, objective
completion, route decisions, or permission to reuse editorial materials.
The input is a dated snapshot of public link identifiers, not guide content.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("data/encyclopedia/guides/ganymede_main_index.json")
MASTER = Path("data/encyclopedia/guides/ganymede_master_observed_links.json")
LINK_TYPES = ("quest", "dungeon", "object", "monster")


def audit_ganymede_master_refs(root: Path) -> dict[str, object]:
    issues: list[dict[str, str]] = []

    def issue(code: str, detail: str) -> None:
        issues.append({"code": code, "detail": detail})

    try:
        index = json.loads((root / INDEX).read_text(encoding="utf-8"))
        doc = json.loads((root / MASTER).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "status": "FAIL",
            "evidence_type": "observed_external_links_only",
            "verified_routes": 0,
            "issues": [{"code": "missing_or_invalid_data", "detail": str(exc)}],
        }

    source = doc.get("source", {})
    coverage = doc.get("coverage", {})
    if doc.get("schema_version") != 1 or not isinstance(source, dict):
        issue("schema", "invalid source format or version")
        source = {}
    if not isinstance(coverage, dict):
        issue("coverage", "coverage must be an object")
        coverage = {}
    if (
        source.get("guide_id") != 2251
        or source.get("source_url") != "https://ganymede-app.com/guides/2251"
        or source.get("extraction_scope") != "factual_link_occurrences_only"
        or source.get("editorial_text_imported") is not False
    ):
        issue("unproven_source", "MG0 source, scope or editorial restrictions invalid")
    if (
        coverage.get("route_order_certified") is not False
        or coverage.get("quest_objective_mapping_verified") != 0
    ):
        issue("false_certification", "observed links cannot certify gameplay routes")
    page_count, per_page = source.get("page_count"), source.get("steps_per_page")
    if (
        type(page_count) is not int or page_count <= 0
        or type(per_page) is not int or per_page <= 0
    ):
        issue("pagination", "invalid snapshot pagination")
        page_count, per_page = 0, 1

    main_guides = index.get("guides", [])
    if not isinstance(main_guides, list):
        issue("index", "invalid source index")
        main_guides = []
    main_ids = {r["ganymede_guide_id"] for r in main_guides
                if isinstance(r, dict)
                and type(r.get("ganymede_guide_id")) is int}
    master_index_rows = [r for r in main_guides
                         if isinstance(r, dict) and r.get("ganymede_guide_id") == 2251]
    expected_steps = master_index_rows[0].get("listed_step_count") if len(master_index_rows) == 1 else None
    if type(expected_steps) is not int or expected_steps <= 0:
        issue("index_master_count", "missing MG0 count in public tree index")

    rows = doc.get("steps", [])
    if not isinstance(rows, list):
        issue("invalid_steps", "steps must be an ordered list")
        rows = []
    if len(rows) != expected_steps or coverage.get("observed_steps") != len(rows):
        issue("step_coverage", "step count differs from the public tree snapshot")
    all_links: set[int] = set()
    link_occurrences = 0
    coord_occurrences = 0
    type_counts = {kind: 0 for kind in LINK_TYPES}
    for offset, row in enumerate(rows):
        where = f"steps[{offset}]"
        if not isinstance(row, dict):
            issue("invalid_step", where)
            continue
        number = row.get("source_step_number")
        page = row.get("source_page")
        if type(number) is not int or number != offset + 1:
            issue("step_sequence", where)
        if type(page) is not int or page != offset // per_page + 1 or page > page_count:
            issue("step_page", where)

        guides = row.get("linked_guide_ids")
        if (not isinstance(guides, list)
                or any(type(gid) is not int or gid <= 0 for gid in guides)
                or len(guides) != len(set(map(str, guides)))):
            issue("invalid_guide_links", where)
        else:
            all_links.update(guides)
            link_occurrences += len(guides)

        links = row.get("external_dofusdb_ids")
        if not isinstance(links, dict) or set(links) != set(LINK_TYPES):
            issue("invalid_dofusdb_links", where)
        else:
            for kind in LINK_TYPES:
                values = links[kind]
                if (
                    not isinstance(values, list)
                    or any(type(v) is not int or v <= 0 for v in values)
                    or len(values) != len(set(map(str, values)))
                ):
                    issue("invalid_dofusdb_id", f"{where}:{kind}")
                else:
                    type_counts[kind] += len(values)
        coords = row.get("coordinate_mentions")
        if (
            not isinstance(coords, list)
            or any(not isinstance(p, list) or len(p) != 2
                   or any(type(v) is not int for v in p) for p in coords)
            or len(set(map(str, coords))) != len(coords)
        ):
            issue("invalid_coordinates", where)
        else:
            coord_occurrences += len(coords)

    outside = sorted(all_links - main_ids)
    if (
        coverage.get("distinct_linked_guide_ids") != len(all_links)
        or coverage.get("linked_main_index_guide_ids") != len(all_links & main_ids)
        or coverage.get("linked_outside_main_index_guide_ids") != outside
        or coverage.get("step_guide_links") != link_occurrences
        or coverage.get("dofusdb_step_link_counts") != type_counts
        or coverage.get("coordinate_mentions") != coord_occurrences
    ):
        issue("link_count_mismatch", "snapshot totals or external guide gaps differ from observations")

    return {
        "status": "FAIL" if issues else "PASS_OBSERVED_LINKS_ONLY",
        "evidence_type": "observed_external_links_only",
        "master_guide_id": 2251,
        "observed_steps": len(rows),
        "referenced_main_guides": len(all_links & main_ids),
        "unclassified_non_main_guide_ids": outside,
        "guide_link_occurrences": link_occurrences,
        "dofusdb_step_link_counts": type_counts,
        "coordinate_mentions": coord_occurrences,
        "verified_routes": 0,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_ganymede_master_refs(args.root.resolve())
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "PASS_OBSERVED_LINKS_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
