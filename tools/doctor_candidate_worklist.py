"""Exact-SHA, lossless Doctor candidate worklists with explicit unresolved review.

This is a deterministic triage aid, NOT a proof of runtime usage, file presence
on installed machines, semantic links, or permission to delete assets.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.windows.export_app_repository import selected_runtime_path


def _source_scope(source: str) -> str:
    if source.startswith("app/"):
        return "APP_RUNTIME_OR_BUNDLED_TOOLS"
    if source.startswith("scripts/windows/"):
        return "WINDOWS_PACKAGING"
    if source.startswith("tools/"):
        return "DEVELOPMENT_AND_CERTIFICATION"
    if source.startswith("data/"):
        return "DATASET_JSON"
    return "OTHER_ORIGIN"


def _link_family(row: dict[str, Any]) -> str:
    known = row.get("triage_bucket", "UNCLASSIFIED_REFERENCE_REVIEW")
    if known != "UNCLASSIFIED_REFERENCE_REVIEW":
        return str(known)
    literal = str(row["literal"])
    source = str(row["source"])
    if any(char in literal for char in "*?["):
        return "GLOB_PATTERN_NOT_AN_EXACT_FILE_REVIEW"
    if literal.startswith("/releases/"):
        return "REMOTE_RELEASE_ENDPOINT_REVIEW"
    if source.startswith("app/distribution/") or source == "app/constants.py":
        return "LOCAL_OR_INSTALL_STATE_REVIEW"
    return _source_scope(source) + "_LITERAL_REVIEW"


def _asset_family(path: str) -> str:
    # Real runtime selector reads these paths dynamically, so absence of
    # their literal filenames in AST is not evidence that files are unused.
    if path.startswith("data/encyclopedia/guides/replacement_drafts/cutovers/"):
        return "GANYMEDE_TRUSTED_CUTOVER_ROUTE_DYNAMIC_CONSUMER_REVIEW"
    if path.startswith("data/encyclopedia/guides/replacement_drafts/"):
        return "GANYMEDE_REPLACEMENT_ROUTE_DYNAMIC_CONSUMER_REVIEW"
    if path.startswith("data/encyclopedia/guides/ganymede_") and path.endswith(
        ("_observed_links.json", "_action_candidates.json", "_evidence.json")
    ):
        return "GANYMEDE_DIAGNOSTIC_INPUT_REVIEW"
    if path.startswith(("data/images/classes/", "data/images/breeds/")):
        return "CLASS_PORTRAIT_BUNDLE_REVIEW"
    if path.startswith("data/routes/guide_ultime_manual/"):
        return "MANUAL_ROUTE_DYNAMIC_CONSUMER_REVIEW"
    if path.startswith("data/images/archive/unmatched/"):
        return "ARCHIVED_UNMATCHED_IMAGE_REVIEW"
    if path.startswith("data/images/items/"):
        return "INDEXED_ITEM_IMAGE_REVIEW"
    if path.startswith("data/images/resources/"):
        return "INDEXED_RESOURCE_IMAGE_REVIEW"
    if path.startswith("data/encyclopedia/images/quests/"):
        return "QUEST_VISUAL_MANIFEST_REVIEW"
    if path.startswith("app/assets/themes/"):
        return "UNITY_THEME_ASSET_REVIEW"
    return "OTHER_STATIC_CANDIDATE_REVIEW"


def build_worklists(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    links = report["resource_link_audit"]
    sha = report["candidate_sha"]
    if not (isinstance(sha, str) and len(sha) == 40
            and all(char in "0123456789abcdef" for char in sha)):
        raise ValueError("Invalid exact Git SHA in Doctor evidence")
    if not (report.get("worktree_clean") and
            links.get("all_link_candidates_exported") is True and
            links.get("all_candidates_exported") is True and
            links.get("triage_counts_complete") is True and
            links.get("automatic_deletion_authorized") is False):
        raise ValueError("Doctor evidence is incomplete or not safe for review")
    unresolved = links["unresolved_literal_all_candidates"]
    ambiguous = links["ambiguous_literal_all_candidates"]
    names = links["no_static_consumer_all_candidates"]
    count = links["counts"]
    if (len(unresolved) != count["unresolved_literals"] + count["unsafe_literals"]
            or len(ambiguous) != count["possible_edges"]
            or len(names) != links["no_static_consumer_total"]):
        raise ValueError("Candidate cardinality mismatch; refuse a partial list")

    link_rows: list[dict[str, Any]] = []
    # Stable review IDs: an unrelated new finding must not invalidate all
    # existing decisions, as a global row-number-based ID would.
    occurrences: Counter[tuple[str, str, str, str]] = Counter()
    for row in [*unresolved, *ambiguous]:
        if len(row.get("candidates", [])) != row.get("candidate_count", len(row.get("candidates", []))):
            raise ValueError("Ambiguous target list truncated")
        locator = str(row.get("json_pointer") or row.get("line") or "")
        signature = (row["source"], locator, row["literal"], row["kind"])
        ordinal = occurrences[signature]
        occurrences[signature] += 1
        key = "\\x1f".join([*signature, str(ordinal)])
        link_rows.append({
            "id": "L-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
            "candidate_sha": sha,
            "source": row["source"],
            "source_scope": _source_scope(row["source"]),
            "line": row.get("line", ""),
            "json_pointer": row.get("json_pointer", ""),
            "json_role": row.get("json_role", ""),
            "literal": row["literal"],
            "scanner_kind": row["kind"],
            "triage_family": _link_family(row),
            "possible_targets": "|".join(row.get("candidates", [])),
            "candidate_count": row.get("candidate_count", 0),
            "review_status": "OPEN_REQUIRES_RUNTIME_OR_CONSUMER_EVIDENCE",
            "reviewer_decision": "",
            "evidence": "",
        })
    asset_rows: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name:
            raise ValueError("Invalid asset candidate path")
        if name in seen_assets:
            raise ValueError("Duplicate asset candidate path; review IDs would collide")
        seen_assets.add(name)
        selected = selected_runtime_path(name)
        asset_rows.append({
            "id": "A-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16],
            "candidate_sha": sha,
            "path": name,
            "triage_family": _asset_family(name),
            "app_mirror_allowlist": "INCLUDED" if selected else "EXCLUDED",
            "allowlist_source": "scripts/windows/export_app_repository.py:selected_runtime_path",
            "known_dynamic_loader": (
                "app/modules/encyclopedia/services/guide_ganymede_cutover.py:"
                "select_verified_replacement_path"
                if name.startswith("data/encyclopedia/guides/replacement_drafts/")
                else ""
            ),
            "packaged_in_exe_verified": "NOT_RUN",
            "runtime_consumer_verified": "NOT_RUN",
            "review_status": "OPEN_REQUIRES_RUNTIME_OR_PACKAGING_EVIDENCE",
            "reviewer_decision": "",
            "evidence": "",
        })

    summary = {
        "candidate_sha": sha,
        "status": "WORKLIST_COMPLETE_EVIDENCE_INCOMPLETE",
        "links_count": len(link_rows),
        "assets_count": len(asset_rows),
        "links_by_kind": dict(sorted(Counter(x["scanner_kind"] for x in link_rows).items())),
        "links_by_family": dict(sorted(Counter(x["triage_family"] for x in link_rows).items())),
        "links_by_source_scope": dict(sorted(Counter(x["source_scope"] for x in link_rows).items())),
        "assets_by_family": dict(sorted(Counter(x["triage_family"] for x in asset_rows).items())),
        "assets_by_mirror_allowlist": dict(sorted(Counter(x["app_mirror_allowlist"] for x in asset_rows).items())),
        "open_link_reviews": len(link_rows),
        "open_asset_reviews": len(asset_rows),
        "closed_without_proof": 0,
        "automatic_deletion_authorized": False,
        "notes": [
            "An explicit mirror allowlist proves only the selected files for THAT export script.",
            "It does not prove installed EXE contents or runtime asset usage.",
            "Patterns, user state, and generated paths remain visible in review sheets.",
            "No item is marked FIXED_VERIFIED or KEEP_VERIFIED solely by this classifier.",
        ],
    }
    return link_rows, asset_rows, summary


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    if report.get("candidate_sha") != args.expected_sha:
        raise SystemExit("Exact-SHA mismatch; refusing stale Doctor evidence")
    links, assets, summary = build_worklists(report)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out_dir / "link_reviews.csv", links, list(links[0]) if links else [
        "id", "candidate_sha", "source", "review_status"])
    _write_csv(args.out_dir / "asset_reviews.csv", assets, list(assets[0]) if assets else [
        "id", "candidate_sha", "path", "review_status"])
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({k: summary[k] for k in (
        "candidate_sha", "links_count", "assets_count",
        "assets_by_mirror_allowlist", "open_link_reviews", "open_asset_reviews"
    )}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
