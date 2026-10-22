"""Build a complete, non-playable-until-certified Atlas home navigation catalog.

The 95 Ganymède guides are source metadata, not 95 executable quest routes.
The catalog is a stable one-to-one ID mapping, not permission to launch a
source-link snapshot as a playable Atlas guide. UI must query verified local
routes separately and never promote availability from these metadata.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.audit_ganymede_master_refs import ROOT

INDEX = Path("data/encyclopedia/guides/ganymede_main_index.json")
CROSSWALK = Path("data/encyclopedia/guides/ganymede_source_crosswalk.json")
CATALOG = Path("data/encyclopedia/guides/catalog.json")
DESTINATION = Path("data/encyclopedia/guides/ganymede_home_catalog.json")

# Stable editorial groups, not inferred quest dependency or progression.
# Top groups preserve existing UI; only below_top is a two-column accordion.
GROUPS: dict[str, tuple[int, ...]] = {
    "optimized": (2251,),
    "alignments": (2226, 2249, 2263),
    "dofus": (
        2203, 2248, 2204, 2205, 2208, 2209, 2211, 2276, 2212,
        2221, 2214, 2217, 2269, 2271, 2247, 2261, 2216, 2256,
        2287, 2283, 2218, 2285, 2272, 2273, 2290, 2260,
    ),
    "dimensions": (2237, 2238, 2239, 2244, 2245, 2246, 2240,
                   2241, 2243, 2250, 2257, 2258),
    "eliocalypse": (2268, 2280, 2282, 2275, 2281, 2279, 2278, 2277, 2286),
    "regions": (2207, 2219, 2224, 2223, 2227, 2225, 2220,
                2231, 2232, 2234, 2255, 2213, 2252, 2262,
                2253, 2215, 2235, 2254, 2259, 2293, 3794),
    "events": (2590, 2595, 3795, 3737),
    "other": (2230, 2233, 2236, 2289, 2284, 2270),
    "islands": (2228, 2206, 2210, 2222, 2229, 2265, 2288,
                2264, 2291, 2274, 2292, 2266, 3738),
}
LAYOUT = (
    {"key": "optimized", "label": "Guides optimisés", "placement": "top_left"},
    {"key": "alignments", "label": "Alignements", "placement": "top_left"},
    {"key": "dofus", "label": "Guides Dofus", "placement": "top_right"},
    {"key": "dimensions", "label": "Dimensions divines", "placement": "below_left_1"},
    {"key": "eliocalypse", "label": "Eliocalypse", "placement": "below_right_1"},
    {"key": "regions", "label": "Zones et régions", "placement": "below_left_2"},
    {"key": "events", "label": "Événements", "placement": "below_right_2"},
    {"key": "other", "label": "Autres aventures", "placement": "below_left_3"},
    {"key": "islands", "label": "Îles et territoires", "placement": "below_right_3"},
)


def build_home_catalog(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    index = json.loads((root / INDEX).read_text(encoding="utf-8"))
    crosswalk = json.loads((root / CROSSWALK).read_text(encoding="utf-8"))
    atlas_catalog = json.loads((root / CATALOG).read_text(encoding="utf-8"))
    local_rows = atlas_catalog.get("guides")
    if not isinstance(local_rows, list) or not local_rows:
        raise ValueError("Atlas home guide catalog is unavailable")
    local_ids = {
        row.get("id") for row in local_rows
        if isinstance(row, dict) and row.get("enabled") is True
        and isinstance(row.get("id"), str)
    }
    if len(local_ids) != len([row for row in local_rows
                               if isinstance(row, dict) and row.get("enabled") is True]):
        raise ValueError("Duplicate or invalid Atlas guide IDs")
    rows = index.get("guides")
    if not isinstance(rows, list) or len(rows) != 95:
        raise ValueError("Expected the complete, authoritative 95-guide index")
    source_ids = [row.get("ganymede_guide_id") for row in rows]
    if any(type(x) is not int or x <= 0 for x in source_ids):
        raise ValueError("Invalid Ganymède guide ID")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Duplicate Ganymède guide ID in source index")

    listed = [x for ids in GROUPS.values() for x in ids]
    if len(listed) != len(set(listed)) or set(listed) != set(source_ids):
        missing = sorted(set(source_ids) - set(listed))
        extra = sorted(set(listed) - set(source_ids))
        raise ValueError(
            f"Editorial category coverage mismatch: missing={missing}, "
            f"extra={extra}, duplicates={len(listed)-len(set(listed))}"
        )

    links = {}
    for match in crosswalk.get("guides", []):
        source_id = match.get("ganymede_guide_id")
        atlas_ids = match.get("atlas_guide_ids")
        if source_id not in source_ids or source_id in links:
            raise ValueError(f"Unknown or repeated crosswalk source ID: {source_id}")
        if (not isinstance(atlas_ids, list)
                or not atlas_ids
                or any(not isinstance(x, str) or not x.strip() for x in atlas_ids)
                or len(set(atlas_ids)) != len(atlas_ids)):
            raise ValueError(f"Invalid Atlas IDs for source guide: {source_id}")
        missing_local = sorted(set(atlas_ids) - local_ids)
        if missing_local:
            raise ValueError(f"Nonexistent Atlas navigation targets: {missing_local}")
        links[source_id] = list(atlas_ids)

    source_by_id = {row["ganymede_guide_id"]: row for row in rows}
    entries = []
    for family in LAYOUT:
        for source_id in GROUPS[family["key"]]:
            row = source_by_id[source_id]
            expected_url = f"https://ganymede-app.com/guides/{source_id}"
            if (row.get("source_url") != expected_url
                    or row.get("status") != "metadata_only"
                    or not isinstance(row.get("title"), str)
                    or not row["title"].strip()
                    or type(row.get("listed_step_count")) is not int
                    or row["listed_step_count"] <= 0):
                raise ValueError(f"Untrusted or incomplete metadata for {source_id}")
            prerequisites = row.get("public_tree_prerequisite_guide_ids")
            if (not isinstance(prerequisites, list)
                    or any(type(x) is not int or x not in source_ids or x == source_id
                           for x in prerequisites)
                    or len(set(prerequisites)) != len(prerequisites)):
                raise ValueError(f"Invalid public prerequisite IDs for {source_id}")
            entries.append({
                "ganymede_guide_id": source_id,
                "title": row["title"],
                "family": family["key"],
                "source_url": expected_url,
                "recommended_level_min": row.get("recommended_level_min"),
                "listed_source_step_count": row["listed_step_count"],
                "public_tree_prerequisite_guide_ids": prerequisites,
                "atlas_guide_ids": links.get(source_id, []),
                "source_status": "metadata_only",
                "playable": False,
                "launch_enabled": False,
            })

    return {
        "schema_version": 1,
        "source": "ganymede_main_index",
        "source_coverage": "95_of_95_metadata_only",
        "routes_certified": 0,
        "playable_claimed": 0,
        "ui_contract": "top_existing_plus_aligned_two_column_accordions",
        "groups": [
            {**family, "guide_count": len(GROUPS[family["key"]])}
            for family in LAYOUT
        ],
        "guides": entries,
    }


def render_catalog(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="Write a generated metadata catalog")
    parser.add_argument("--check", action="store_true", help="Fail on a stale catalog")
    args = parser.parse_args()
    if args.check and args.output:
        parser.error("--check and --output are mutually exclusive")
    try:
        rendered = render_catalog(build_home_catalog(args.root))
        if args.check:
            current = (args.root / DESTINATION).read_text(encoding="utf-8")
            if current != rendered:
                raise ValueError("Ganymède home catalog is stale")
        elif args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Home guide catalog blocked: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
