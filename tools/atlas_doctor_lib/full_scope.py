"""Full-inventory static source and Unity style triage owned by Atlas Doctor.

No app imports, tests, graph rebuild, screenshots, deletion or runtime execution.
Unlike the bounded changed-file inspector, every Git-tracked Python source is
parsed, and every finding is counted. This is NOT behavioral or native UI proof.
"""
from __future__ import annotations

import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])")
_STYLE_FILES = ("app/ui/unity_skin.py", "app/ui/theme.py")


def _git(root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False, timeout=45,
    )
    if process.returncode:
        raise ValueError("Git inventory unavailable: " + process.stderr.decode(errors="replace")[:300])
    return process.stdout.decode("utf-8", errors="strict")


def _snapshot(root: Path) -> tuple[str, list[str], list[str], bool]:
    sha = _git(root, "rev-parse", "--verify", "HEAD").strip()
    if not _SHA.fullmatch(sha):
        raise ValueError("No exact Git HEAD")
    raw = _git(root, "ls-files", "-z", "--", "*.py")
    paths = sorted(set(filter(None, raw.split("\0"))))
    all_paths = sorted(set(filter(None, _git(root, "ls-files", "-z").split("\0"))))
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no").strip())
    return sha, paths, all_paths, not dirty


def _imports_missing(root: Path, path: str, tree: ast.AST) -> list[dict[str, Any]]:
    # Reuse Doctor's bounded inspector's exact import semantics without its
    # file/function/finding caps. These remain candidates, not broken imports.
    from .deep_intelligence import _missing_internal_imports
    return _missing_internal_imports(root, path, tree)


def _style_candidates(path: str, tree: ast.AST) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "setStyleSheet":
                issues.append({
                    "file": path, "line": node.lineno, "kind": "LOCAL_QSS_OVERRIDE_REVIEW",
                    "reason": "Review local QSS against shared Unity theme; dynamic values may be valid.",
                })
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            literal = node.value
            if "QWidget" in literal or "QPushButton" in literal or "QFrame" in literal:
                if "{" in literal and "}" in literal:
                    colors = sorted(set(_HEX_COLOR.findall(literal)))
                    if colors and path not in _STYLE_FILES:
                        issues.append({
                            "file": path, "line": node.lineno,
                            "kind": "LOCAL_LITERAL_QSS_COLOR_REVIEW",
                            "colors": colors, "review_only": True,
                        })
    return issues


def _silent_exceptions(path: str, tree: ast.AST) -> list[dict[str, Any]]:
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = [item for item in node.body if not (
            isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        )]
        if len(body) == 1 and (
            isinstance(body[0], ast.Pass)
            or (isinstance(body[0], ast.Return) and (
                body[0].value is None or isinstance(body[0].value, ast.Constant)
            ))
        ):
            hits.append({
                "file": path, "line": node.lineno,
                "kind": "SWALLOWED_EXCEPTION_REVIEW", "review_only": True,
            })
    return hits



def _current_graph_audit(root: Path, sha: str) -> dict[str, Any]:
    """Reuse Doctor's exact-SHA Graphify audit, without rebuilding or truncation."""
    try:
        from .architecture import graph_status
        from .graph_audit import audit_current_graph
        evidence = graph_status(root)
        if evidence.get("status") != "PASS":
            return {
                "status": "BLOCKED",
                "reason": evidence.get("reason", "Current Graphify graph unavailable"),
                "rebuild_command": evidence.get("rebuild_command"),
            }
        report = audit_current_graph(root, graph_evidence=evidence, all_candidates=True)
        if report.get("candidate_sha") != sha:
            return {"status": "BLOCKED", "reason": "Graphify candidate SHA differs"}
        if report.get("status") == "BLOCKED":
            return report
        pagination = (report.get("limits") or {}).get("pagination") or {}
        if any(section.get("truncated") for section in pagination.values()):
            return {"status": "BLOCKED", "reason": "Graphify candidate section truncated"}
        return report
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc)}


def audit_full_scope(root: Path, *, expected_sha: str | None = None,
                     with_graph: bool = False, with_json: bool = False,
                     with_links: bool = False) -> dict[str, Any]:
    """Scan *every* tracked Python file, fail closed on missing or unreadable ones.

    SOURCE_COVERED does not imply runtime, Graphify, UI or native certification.
    The static findings are complete for this declared source inventory.
    """
    root = root.resolve()
    try:
        sha, paths, all_paths, clean = _snapshot(root)
    except (OSError, UnicodeError, subprocess.TimeoutExpired, ValueError) as exc:
        return {
            "schema_version": 1, "kind": "doctor_full_scope_audit",
            "status": "BLOCKED", "reason": str(exc),
            "source_coverage": {"status": "BLOCKED", "truncated": False},
        }
    if expected_sha is not None and (not _SHA.fullmatch(expected_sha) or sha != expected_sha):
        return {
            "schema_version": 1, "kind": "doctor_full_scope_audit",
            "status": "BLOCKED", "candidate_sha": sha,
            "reason": "Expected SHA differs from exact checkout HEAD",
            "source_coverage": {"status": "BLOCKED", "truncated": False},
        }
    if not paths:
        return {
            "schema_version": 1, "kind": "doctor_full_scope_audit",
            "status": "BLOCKED", "candidate_sha": sha, "reason": "No tracked Python files",
            "source_coverage": {"status": "BLOCKED", "truncated": False},
        }

    inventory_counts = {"python": 0, "json": 0, "qss": 0, "visual_asset": 0, "other": 0}
    json_files = []
    for name in all_paths:
        suffix = Path(name).suffix.casefold()
        group = ("python" if suffix == ".py" else "json" if suffix == ".json"
                 else "qss" if suffix == ".qss"
                 else "visual_asset" if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".ttf", ".otf"}
                 else "other")
        inventory_counts[group] += 1
        if group == "json":
            json_files.append(name)

    inspected: list[str] = []
    failed: list[dict[str, str]] = []
    duplicate_bodies: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_imports: list[dict[str, Any]] = []
    silent: list[dict[str, Any]] = []
    style: list[dict[str, Any]] = []
    json_references: list[dict[str, Any]] = []
    functions = 0

    for relative in paths:
        full = root / relative
        try:
            # Reject symlinks / external paths rather than silently following them.
            if full.is_symlink() or not full.is_file():
                raise ValueError("Missing or symlinked tracked source")
            full.resolve().relative_to(root)
            tree = ast.parse(full.read_text(encoding="utf-8-sig"), filename=relative)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            failed.append({"file": relative, "error": type(exc).__name__})
            continue

        inspected.append(relative)
        missing_imports.extend(_imports_missing(root, relative, tree))
        silent.extend(_silent_exceptions(relative, tree))
        if relative.startswith("app/"):
            style.extend(_style_candidates(relative, tree))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions += 1
                # Exact AST body only, like the existing Doctor inspector.
                fingerprint = hashlib.sha256(ast.dump(
                    ast.Module(body=node.body, type_ignores=[]),
                    include_attributes=False,
                ).encode()).hexdigest()
                duplicate_bodies[fingerprint].append({
                    "file": relative, "line": node.lineno, "name": node.name,
                })
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and len(node.value) <= 240 and node.value.lower().endswith(".json")):
                json_references.append({
                    "file": relative, "line": node.lineno,
                    "literal": node.value, "proof": "LITERAL_NOT_RUNTIME_USE",
                })

    duplicate_groups = [
        {"kind": "EXACT_AST_BODY_REVIEW", "occurrences": rows,
         "proof_of_equivalent_behavior": False}
        for rows in duplicate_bodies.values() if len(rows) > 1
    ]
    duplicate_groups.sort(key=lambda row: (
        -len(row["occurrences"]), row["occurrences"][0]["file"],
        row["occurrences"][0]["line"],
    ))
    missing_files = sorted(set(paths) - set(inspected))
    source_status = "PASS" if not missing_files and not failed and clean else "BLOCKED"
    style_files_present = [path for path in _STYLE_FILES if path in inspected]
    style_status = "REVIEW" if len(style_files_present) == len(_STYLE_FILES) else "BLOCKED"
    graph = _current_graph_audit(root, sha) if with_graph else {
        "status": "NOT_RUN", "reason": "Use --with-graph with a current exact-SHA Graphify graph."
    }
    graph_failed = with_graph and graph.get("status") in {"FAIL", "BLOCKED"}
    if with_json:
        from .json_semantic_coverage import inspect_tracked_json
        json_audit = inspect_tracked_json(root, json_files, sha=sha, clean=clean)
    else:
        json_audit = {"status": "NOT_RUN", "syntax_coverage": "NOT_RUN"}
    json_failed = with_json and json_audit.get("status") == "BLOCKED"
    if with_links:
        from .resource_link_audit import inspect_resource_links
        links_audit = inspect_resource_links(root, all_paths, paths, json_files)
    else:
        links_audit = {"status": "NOT_RUN", "reason": "Use --with-links for advisory resource consumer triage."}
    links_failed = with_links and links_audit.get("status") == "BLOCKED"
    return {
        "schema_version": 1, "kind": "doctor_full_scope_audit",
        "candidate_sha": sha, "worktree_clean": clean,
        # NO false global PASS: dynamic callbacks, EXE, UI, user paths NOT RUN.
        "status": "BLOCKED" if source_status == "BLOCKED" or graph_failed or json_failed or links_failed else "REVIEW",
        "tracked_file_inventory": {
            "status": "INVENTORIED_NOT_CONTENT_CERTIFIED",
            "tracked_total": len(all_paths),
            "categories": inventory_counts,
            "json_files": json_files,
            "truncated": False,
            "json_content_coverage": json_audit["syntax_coverage"],
            "asset_reference_verification": "NOT_RUN",
            "qss_visual_rendering": "NOT_RUN",
            "note": ("Git inventory covers tracked paths; Python and JSON syntax parsed, "
                     "but semantic links/assets/UI remain unverified." if with_json
                     else "Inventory is exhaustive for tracked Git paths; parsing is Python-only."),
        },
        "source_coverage": {
            "status": source_status,
            "worktree_dirty": not clean,
            "total": len(paths), "inspected": len(inspected),
            "missing": missing_files, "parse_errors": failed,
            "truncated": False, "file_count_limit": None, "function_count_limit": None,
            "functions_inspected": functions,
            "inventory_sha256": hashlib.sha256(
                "\0".join(paths).encode("utf-8")
            ).hexdigest(),
        },
        "findings": {
            "exact_ast_duplicate_groups": duplicate_groups,
            "missing_import_candidates": missing_imports,
            "silent_exception_candidates": silent,
            "literal_json_references": json_references,
            "counts": {
                "duplicate_groups": len(duplicate_groups),
                "missing_imports": len(missing_imports),
                "silent_exceptions": len(silent),
                "literal_json_references": len(json_references),
            },
            "truncated": False, "automatic_deletion_authorized": False,
        },
        "unity_style": {
            "status": style_status, "shared_theme_files": style_files_present,
            "static_candidates": style,
            "candidate_count": len(style),
            "truncated": False,
            "native_windows_visual": "NOT_RUN",
            "qt_screenshot_comparison": "NOT_RUN",
            "all_widget_states": "NOT_RUN",
            "launcher_tk_qt_parity": "NOT_RUN",
            "public_asset_fallback": "NOT_RUN",
            "visual_certified": False,
        },
        "runtime_scenario_coverage": "NOT_RUN",
        "json_semantic_audit": json_audit,
        "resource_link_audit": links_audit,
        "graph_architecture_audit": graph,
        "graph_runtime_correlation": "NOT_RUN",
        "tests_executed": False, "benchmark_executed": False,
        "complete_application_certified": False,
        "limits": [
            "Source scan is exhaustive only for Git-tracked Python files at this SHA",
            "Static absence of imports or calls does not prove dead code",
            "Qt dynamic callbacks and installed Windows UI need positive execution proof",
            "Unity static checks do not establish visual consistency or native DPI",
            "Source candidate findings are review leads, not automatic fixes",
        ],
    }


def write_full_scope_report(root: Path, output: Path, report: dict[str, Any]) -> Path:
    """Allow report writing under artifacts/ only; never touch user/app data."""
    root = root.resolve()
    output = output if output.is_absolute() else root / output
    dest = output.resolve()
    if not dest.is_relative_to(root / "artifacts") or dest.suffix != ".json":
        raise ValueError("Full scope report must be a JSON under artifacts/")
    if output.is_symlink() or dest.is_symlink():
        raise ValueError("Symlink reports are forbidden")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest
