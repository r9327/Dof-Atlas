"""Narrow proof that Doctor's AST duplicate scan completed; not a full graph audit.

The canonical code-inspect command may return REVIEW when unrelated graph or
JSON-lineage inputs are absent/truncated. Its AST source scan can nevertheless
be complete. Record both verdicts and fail closed on partial AST evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarize_ast_duplicates(raw: dict[str, Any], *, sha: str) -> dict[str, Any]:
    from .deep_intelligence import MAX_FINDINGS, MAX_FILES

    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Exact Git SHA required")
    source = raw.get("source")
    if not isinstance(source, dict):
        raise ValueError("Doctor source intelligence missing")
    counts = source.get("counts") or {}
    paths = source.get("paths_inspected") or []
    requested = source.get("requested_count")
    duplicates = source.get("duplicate_bodies") or []
    near = source.get("near_duplicate_candidates") or []
    errors = source.get("parse_errors") or []
    budgets = source.get("budgets") or {}
    complete = (
        raw.get("kind") == "doctor_code_inspection"
        and raw.get("status") != "BLOCKED"
        and source.get("status") in {"PASS", "REVIEW"}
        and isinstance(requested, int) and 0 < requested <= MAX_FILES
        and isinstance(paths, list) and requested == len(paths)
        and len(set(paths)) == len(paths)
        and not errors
        and budgets.get("function_limit_reached") is False
        and isinstance(counts.get("functions"), int)
        and isinstance(counts.get("duplicate_groups"), int)
        and isinstance(counts.get("near_duplicate_groups"), int)
        and 0 <= counts["duplicate_groups"] <= MAX_FINDINGS
        and 0 <= counts["near_duplicate_groups"] <= MAX_FINDINGS
        and len(duplicates) == counts["duplicate_groups"]
        and len(near) == counts["near_duplicate_groups"]
    )
    return {
        "schema_version": 1,
        "kind": "atlas_doctor_ast_duplicate_review",
        "git_head": sha,
        "status": "PASS" if complete else "BLOCKED",
        "source": {
            "counts": counts,
            "paths_inspected": paths,
            "requested_count": requested,
            "duplicate_bodies": duplicates,
            "near_duplicate_candidates": near,
            "parse_errors": errors,
            "function_limit_reached": budgets.get("function_limit_reached"),
        },
        "full_code_inspection_status": raw.get("status"),
        "graph_status": raw.get("graph_status"),
        "full_code_inspection_truncated": source.get("truncated"),
        "review_required": bool(duplicates or near or source.get("silent_exceptions")),
        "coverage_statement": (
            "PASS means complete bounded AST duplicate evidence on all selected "
            "changed Python sources. It does NOT mean that the entire graph/code "
            "inspector passed, no reviewed findings exist, or all repo files were scanned."
        ),
        "missing_proof": [] if complete else [
            "incomplete_or_failed_AST_coverage_or_finding_budget"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    result = summarize_ast_duplicates(raw, sha=args.sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "counts": result["source"]["counts"],
                      "inspection_status": result["full_code_inspection_status"]}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
