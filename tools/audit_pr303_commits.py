"""Inspect all historical PR303 Git patches, without claiming human approval."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "CI_BYPASS": r"skip[\s_-]*ci|continue-on-error:\s*true|--no-verify",
    "TEST_SKIP": r"\b(?:unittest\.skip(?:If|Unless)?|pytest\.mark\.(?:skip|skipif|xfail)|pytest\.(?:skip|xfail)|self\.skipTest)\s*\(",
    "EXCEPTION": r"\bexcept\*?(?:\s+(?:[A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*|\([^)]*\))(?:\s+as\s+[A-Za-z_]\w*)?)?\s*:",
    "PROCESS": r"subprocess\.(?:run|Popen)|os\.system|shell\s*=\s*True",
    "CACHE": r"lru_cache|cached_property|QPixmapCache|\.deleteLater\(",
    "SQLITE": r"sqlite3|\.as_uri\(|\.resolve\(",
    "UI_QT": r"QWidget|QTimer|QThread|setStyleSheet",
    "DATA": r"\bjson\.(?:load|loads|dump|dumps)\b|\.(?:json|png|qss|webp|svg|jpe?g|ico|ttf|otf)\b",
    "PERFORMANCE": r"\b(?:benchmark|preload|ram|rss|tracemalloc|budget)\b",
}


def git(*args: str) -> str:
    p = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                       capture_output=True, text=True, errors="strict", check=True, timeout=45)
    return p.stdout


def scan_patch(patch: str) -> dict:
    lines = patch.splitlines()
    added = [s[1:] for s in lines if s.startswith("+") and not s.startswith("+++")]
    removed = [s[1:] for s in lines if s.startswith("-") and not s.startswith("---")]
    removed_check = re.compile(
        r"^\s*(?:assert\b|self\.assert\w*\s*\(|self\.fail\s*\(|pytest\.fail\s*\(|(?:with\s+)?pytest\.raises\s*\()", re.I
    )
    removed_test_definition = re.compile(
        r"^\s*(?:async\s+)?def\s+test_[A-Za-z0-9_]*\s*\(", re.I
    )
    findings = {
        name: sum(bool(re.search(pattern, line, flags=re.I)) for line in added)
        for name, pattern in PATTERNS.items()
    }
    # Associate every heuristic flag with its actual diff file and added line,
    # never pretend a commit-wide regex count identifies a root cause.
    risk_locations: list[dict[str, object]] = []
    deleted_assertion_locations: list[dict[str, object]] = []
    deleted_test_locations: list[dict[str, object]] = []
    current_file: str | None = None
    new_line: int | None = None
    old_line: int | None = None
    for diff_line in lines:
        if diff_line.startswith("diff --git "):
            # Never carry a previous file's line number to the next patch.
            current_file = None
            new_line = None
            old_line = None
        elif diff_line.startswith("+++ b/"):
            current_file = diff_line[6:]
            new_line = None
            old_line = None
        elif diff_line.startswith("+++ /dev/null"):
            current_file = None
            new_line = None
            old_line = None
        elif diff_line.startswith("@@ "):
            # A changed test belongs to its OLD hunk coordinates. Added
            # diagnostics below use the NEW coordinates of the same hunk.
            match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", diff_line)
            old_line = int(match.group(1)) if match else None
            new_line = int(match.group(2)) if match else None
        elif diff_line.startswith("+") and not diff_line.startswith("+++"):
            for category, pattern in PATTERNS.items():
                if re.search(pattern, diff_line[1:], flags=re.I):
                    risk_locations.append({
                        "file": current_file, "line": new_line, "category": category,
                    })
            if new_line is not None:
                new_line += 1
        elif diff_line.startswith("-") and not diff_line.startswith("---"):
            if removed_check.search(diff_line[1:]):
                deleted_assertion_locations.append({
                    "file": current_file, "line": old_line,
                })
            # Entire test cases may be deleted while containing no asserts
            # (e.g. pytest tests relying on bare raises or snapshots).
            if removed_test_definition.search(diff_line[1:]):
                deleted_test_locations.append({
                    "file": current_file, "line": old_line,
                    "definition": diff_line[1:].strip(),
                })
            if old_line is not None:
                old_line += 1
        elif diff_line.startswith(" "):
            if new_line is not None:
                new_line += 1
            if old_line is not None:
                old_line += 1
    return {
        "added_lines": len(added),
        "deleted_lines": len(removed),
        "risk_leads": {name: n for name, n in findings.items() if n},
        "risk_locations": risk_locations,
        "deleted_assertions": len(deleted_assertion_locations),
        "deleted_assertion_locations": deleted_assertion_locations,
        "deleted_test_definitions": len(deleted_test_locations),
        "deleted_test_locations": deleted_test_locations,
        "binary_manual_review": "Binary files " in patch or "GIT binary patch" in patch,
    }


def review(base: str, head: str, expected: int | None = None) -> dict:
    if git("rev-parse", "--verify", base + "^{commit}").strip() != base:
        raise ValueError("Missing historical base")
    if git("rev-parse", "--verify", head + "^{commit}").strip() != head:
        raise ValueError("Missing original PR head")
    subprocess.run(["git", "merge-base", "--is-ancestor", base, head], check=True)
    commits = git("rev-list", "--reverse", base + ".." + head).splitlines()
    records = []
    for pos, sha in enumerate(commits, 1):
        parent_shas = git("rev-list", "--parents", "-n", "1", sha).split()[1:]
        if not parent_shas:
            raise ValueError("No parent for commit " + sha)
        parents = []
        for parent in parent_shas:
            paths = git("diff", "--name-status", "--find-renames", parent, sha).splitlines()
            diff = git("diff", "--no-ext-diff", "--unified=0", "--find-renames", parent, sha)
            parents.append({"sha": parent, "paths": paths, **scan_patch(diff)})
        title = git("log", "-1", "--format=%s", sha).strip()
        flags = []
        if len(parents) > 1:
            flags.append("MERGE_BOTH_PARENTS_REVIEW")
        if "revert" in title.lower():
            flags.append("REVERT_FINAL_STATE_REVIEW")
        if re.search(r"skip[\s_-]*ci", title, flags=re.I):
            flags.append("CI_BYPASS_REVIEW")
        if any(p["deleted_assertions"] for p in parents):
            flags.append("REMOVED_ASSERTIONS_REVIEW")
        if any(p["deleted_test_definitions"] for p in parents):
            flags.append("REMOVED_TEST_DEFINITIONS_REVIEW")
        if any(p["risk_leads"].get("TEST_SKIP") for p in parents):
            flags.append("ADDED_TEST_SKIP_REVIEW")
        if any(p["binary_manual_review"] for p in parents):
            flags.append("BINARY_CONTENT_REVIEW")
        records.append({
            "position": pos, "sha": sha, "title": title,
            "parents": parents, "flags": flags,
            "patch_status": "INSPECTED",
            "human_review": "NOT_RUN",
            "decision": "REVIEW_REQUIRED",
        })
    unique = len({x["sha"] for x in records}) == len(records)
    complete = unique and (expected is None or len(records) == expected)
    effective_expected = len(records) if expected is None else expected
    return {
        "schema": 1, "base_sha": base, "head_sha": head,
        "expected": effective_expected, "expected_policy": "DYNAMIC_RANGE" if expected is None else "EXPLICIT",
        "inspected": len(records),
        "status": "PATCH_INVENTORY_COMPLETE_HUMAN_REVIEW_REQUIRED" if complete else "BLOCKED",
        "auto_merge_authorized": False, "records": records,
    }


def save(out: Path, report: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = [
        "# PR303 - Audit des patches de tous les commits",
        "",
        "Etat: " + report["status"],
        "Inspected: " + str(report["inspected"]) + "/" + str(report["expected"]),
        "Audit machine des patchs, pas revue humaine ni validation de l'application.",
        "",
        "| # | SHA | Sujet | Parents | Alertes | Validation |",
        "|---:|---|---|---:|---|---|",
    ]
    for x in report["records"]:
        leads = sorted(set(x["flags"] + [k for p in x["parents"] for k in p["risk_leads"]]))
        title = x["title"].replace("|", "\\|")
        url = "https://github.com/r9327/Dof-Atlas/commit/" + x["sha"]
        md.append("| {pos} | [{sha}]({url}) | {title} | {parents} | {leads} | {status} |".format(
            pos=x["position"], sha=x["sha"][:12], url=url, title=title,
            parents=len(x["parents"]), leads=", ".join(leads) or "-",
            status=x["decision"]))
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-sha", required=True)
    ap.add_argument("--head-sha", required=True)
    ap.add_argument("--expected", type=int, default=None)
    ap.add_argument("--output", type=Path, default=Path("artifacts/pr303_commits/audit.json"))
    args = ap.parse_args()
    if any(re.fullmatch(r"[0-9a-f]{40}", s) is None for s in [args.base_sha, args.head_sha]):
        ap.error("Expected exact lowercase 40-hex SHA")
    report = review(args.base_sha, args.head_sha, args.expected)
    save(args.output, report)
    print(report["status"] + ": " + str(report["inspected"]) + "/" + str(report["expected"]))
    return 0 if report["status"] == "PATCH_INVENTORY_COMPLETE_HUMAN_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
