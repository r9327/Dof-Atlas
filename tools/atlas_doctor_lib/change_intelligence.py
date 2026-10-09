from __future__ import annotations

"""Bounded, read-only Doctor diff triage. No graph generation or tests run."""
import ast
import subprocess
from pathlib import Path
from typing import Any

MAX_CHANGED = 100
MAX_REMOVED = 12
MAX_CONSUMERS = 120
MAX_GRAPH_PATHS = 24


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git {' '.join(args)}: {exc}") from exc
    if result.returncode not in (0,):
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result


def removed_python_modules(root: Path, base_ref: str) -> list[str]:
    """Find old module names from committed, staged and unstaged deletions/renames."""
    old: set[str] = set()
    for args in (
        ("diff", "--name-status", "--find-renames", f"{base_ref}...HEAD"),
        ("diff", "--name-status", "--find-renames", "HEAD"),
    ):
        for line in _git(root, *args).stdout.splitlines():
            fields = line.split("\t")
            if len(fields) < 2 or not fields[0].startswith(("D", "R")):
                continue
            path = fields[1].replace("\\", "/")
            if path.endswith(".py") and (path.startswith("app/") or path.startswith("tools/")):
                old.add(path)
    return sorted(old)


def _imports_deleted_module(tree: ast.AST, source: str, module: str) -> list[int]:
    lines: set[int] = set()
    package, _, leaf = module.rpartition(".")
    current_package = source.removesuffix(".py").replace("/", ".").rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module or alias.name.startswith(module + ".") for alias in node.names):
                lines.add(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            imported = node.module or ""
            if node.level:
                parts = current_package.split(".")
                parts = parts[:max(0, len(parts) - node.level + 1)]
                imported = ".".join([*parts, *([imported] if imported else [])])
            if imported == module or imported.startswith(module + ".") or (
                imported == package and any(alias.name == leaf for alias in node.names)
            ):
                lines.add(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            if name in {"import_module", "__import__"} and node.args and isinstance(node.args[0], ast.Constant):
                if node.args[0].value == module:
                    lines.add(node.lineno)
    return sorted(lines)


def stale_removed_imports(root: Path, old_paths: list[str]) -> dict[str, Any]:
    """Git grep narrows the AST scan; only current source imports become findings."""
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    examined = 0
    truncated = len(old_paths) > MAX_REMOVED
    for path in old_paths[:MAX_REMOVED]:
        module = path[:-3].removesuffix("/__init__").replace("/", ".")
        leaf = module.rsplit(".", 1)[-1]
        try:
            result = subprocess.run(
                ["git", "grep", "-l", "-z", "-F", "-e", leaf, "--", "*.py"],
                cwd=root, capture_output=True, check=False, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{path}: {exc}")
            continue
        if result.returncode == 1:
            continue
        if result.returncode != 0:
            errors.append(f"{path}: git grep failed ({result.returncode})")
            continue
        candidates = sorted({item.decode("utf-8", errors="replace") for item in result.stdout.split(b"\0") if item})
        if len(candidates) > MAX_CONSUMERS:
            truncated = True
        for candidate in candidates[:MAX_CONSUMERS]:
            source = root / candidate
            if not source.is_file():
                continue
            examined += 1
            try:
                tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=candidate)
            except (OSError, UnicodeError, SyntaxError) as exc:
                errors.append(f"{candidate}: {exc}")
                continue
            for line in _imports_deleted_module(tree, candidate, module):
                findings.append({
                    "consumer": candidate, "line": line, "removed_module": module,
                    "evidence": "CURRENT_SOURCE_IMPORT", "confidence": "CONFIRMED_STATIC",
                })
    return {"findings": sorted(findings, key=lambda f: (f["consumer"], f["line"], f["removed_module"])),
            "examined_files": examined, "truncated": truncated, "errors": errors,
            "limits": "Literal imports only. Runtime plugin discovery and reflective consumers require runtime evidence."}


def build_change_plan(root: Path, *, base_ref: str,
                      cost_reports: list[Path] | None = None) -> dict[str, Any]:
    """Compose existing Agent/Graphify engines without spawning validation suites."""
    from tools import agent, atlas_integrity
    from tools.atlas_doctor_lib.architecture import graph_status
    from tools.atlas_doctor_lib.core import git_state

    root = root.resolve()
    atlas_integrity.resolve_base_ref(root, base_ref)
    base_sha = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}").stdout.strip()
    changed = atlas_integrity.changed_files(root, base_ref)
    state = git_state(root)
    payload: dict[str, Any] = {
        "schema_version": 1, "kind": "doctor_change_plan", "base_ref": base_ref,
        "base_sha": base_sha, "candidate_sha": state["head"], "dirty": state["dirty"],
        "paths": changed, "read_only": True, "tests_executed": False,
        "graph_rebuilt": False, "status": "REVIEW",
    }
    if not changed:
        payload.update(status="READY", reason="No changes to inspect.",
                       graph={"status": "NOT_REQUIRED"}, targeted_tests=[],
                       full_suite={"status": "NOT_REQUIRED"}, structural_findings=[])
        return payload
    if len(changed) > MAX_CHANGED:
        payload.update(reason=f"{len(changed)} paths exceed the {MAX_CHANGED}-path inspection budget; partition the change.",
                       graph={"status": "NOT_RUN"}, targeted_tests=[],
                       full_suite={"status": "DEFERRED_NOT_WAIVED"}, structural_findings=[])
        return payload

    old_paths = removed_python_modules(root, base_ref)
    stale = stale_removed_imports(root, old_paths)
    # Agent owns scope/risk/targeted-test planning. Keep its FULL gate intact.
    plan = agent.plan_payload(root, changed, base_ref=base_ref, structural=bool(old_paths))
    preflight = plan.get("architecture_preflight") or {}
    graph_evidence = preflight.get("graph")
    graph_impact = preflight.get("impact")
    if graph_evidence is None:
        graph_evidence = graph_status(root)
    current_python = [p for p in changed if p.endswith(".py") and (root / p).is_file()]
    if graph_evidence.get("status") == "PASS" and graph_impact is None and current_python:
        graph_impact = agent.reverse_impact_payload(root, current_python[:MAX_GRAPH_PATHS], depth=1)
    graph_truncated = len(current_python) > MAX_GRAPH_PATHS or bool((graph_impact or {}).get("truncated"))
    missing_graph = bool(current_python) and (
        graph_evidence.get("status") != "PASS" or
        (graph_impact or {}).get("status") not in {"PASS", "REVIEW"}
    )
    confirmation = (graph_impact or {}).get("confirmed_relationships", [])
    # Keep tests selected by canonical planner; never substitute a FULL suite
    # command as a quick test when HARD/FULL/DEEP is required.
    tests = list(plan.get("execution_tests") or [])
    full_required = plan.get("integrity_mode") in {"FULL", "DEEP"}
    review = bool(stale["errors"] or stale["truncated"] or graph_truncated or missing_graph
                  or plan.get("status") != "READY" or old_paths)
    payload.update(
        status="BLOCKED" if stale["findings"] else "REVIEW" if review else "READY",
        reason="Confirmed imports of a deleted/moved module." if stale["findings"] else
               "Unconfirmed architecture/ownership/structural evidence requires review." if review else
               "Bounded change inspection completed; tests proposed, not executed.",
        removed_or_renamed_modules=old_paths, structural_findings=stale["findings"],
        structural_scan={key: value for key, value in stale.items() if key != "findings"},
        graph={"status": graph_evidence.get("status"),
               "reason": graph_evidence.get("reason"),
               "rebuild_command": graph_evidence.get("rebuild_command")},
        graph_consumer_evidence={
            "status": (graph_impact or {}).get("status", "NOT_RUN"),
            "confirmed": confirmation[:40],
            "confirmed_total": len(confirmation),
            "unconfirmed_total": len((graph_impact or {}).get("unconfirmed_relationships", [])),
            "truncated": graph_truncated,
        },
        scope=plan.get("scopes", []), risk=plan.get("risk"),
        targeted_tests=tests, target_test_command=plan.get("test_command") if tests else [],
        required_groups=plan.get("required_groups", []),
        full_suite={"status": "DEFERRED_NOT_WAIVED" if full_required else "POLICY_DEPENDENT",
                    "minimum_integrity_mode": plan.get("integrity_mode"),
                    "reason": "Certification owned by Atlas Integrity, not run by change-plan."},
        planning_status=plan.get("status"),
        limitations=["Graph edges require current AST import confirmation; reflective/Qt consumers are not yet fully observable.",
                     "No test result, measured speedup or runtime dependency is claimed by this plan."],
    )
    if cost_reports:
        from .test_intelligence import suggest_targeted_test_order, test_cost_report
        costs = test_cost_report(root, cost_reports)
        payload["historical_test_costs"] = costs
        payload["test_execution_order_advice"] = suggest_targeted_test_order(
            list(plan.get("required_groups") or []), costs)
    return payload
