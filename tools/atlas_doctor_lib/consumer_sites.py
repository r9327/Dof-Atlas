from __future__ import annotations

"""Bounded consumer investigation; dynamic sites remain candidates."""
import ast
import subprocess
from pathlib import Path
from typing import Any

MAX_FILES = 120
MAX_SIZE = 256 * 1024
MAX_ROWS = 100


def _candidate_files(root: Path, leaf: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "grep", "-l", "-z", "-F", "-e", leaf, "-e", "import_module", "-e", "__import__(", "-e", ".connect(", "-e", "getattr(", "--", "*.py"],
            cwd=root, capture_output=True, check=False, timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Consumer prefilter unavailable") from exc
    if result.returncode == 1:
        return []
    if result.returncode:
        raise RuntimeError("Consumer prefilter failed")
    candidates = {b.decode("utf-8", errors="replace") for b in result.stdout.split(b"\\0") if b}
    # Target-specific references must not be starved by generic dynamic calls.
    try:
        direct = subprocess.run(
            ["git", "grep", "-l", "-z", "-F", "-e", leaf, "--", "*.py"],
            cwd=root, capture_output=True, check=False, timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Consumer prefilter unavailable") from exc
    if direct.returncode not in {0, 1}:
        raise RuntimeError("Consumer prefilter failed")
    prioritized = sorted({b.decode("utf-8", errors="replace")
                          for b in direct.stdout.split(b"\\0") if b})
    return prioritized + sorted(candidates.difference(prioritized))


def _literal_string(node: ast.AST | None) -> str | None:
    """Fold only constant strings, without executing project code."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_string(node.left), _literal_string(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = [_literal_string(value) for value in node.values]
        if all(value is not None for value in parts):
            return "".join(parts)
    return None


def inspect_consumer_sites(root: Path, target: str) -> dict[str, Any]:
    """Search actual source candidates, without loading application modules."""
    from tools import agent
    root = root.resolve()
    value = Path(target.replace("\\", "/"))
    if value.is_absolute() or ".." in value.parts or value.suffix != ".py":
        raise ValueError("Expected a repository-relative Python module")
    target = value.as_posix()
    module = target.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
    leaf = module.rsplit(".", 1)[-1]
    candidates = _candidate_files(root, leaf)
    leads, errors = [], []
    for name in candidates[:MAX_FILES]:
        p = (root / name).resolve()
        if not p.is_relative_to(root) or not p.is_file() or p.is_symlink():
            errors.append({"path": name, "reason": "Unsafe or missing path"})
            continue
        try:
            if p.stat().st_size > MAX_SIZE:
                errors.append({"path": name, "reason": "Source exceeds bounded AST budget"})
                continue
            tree = ast.parse(p.read_text(encoding="utf-8-sig"), filename=name)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({"path": name, "reason": type(exc).__name__})
            continue
        import_aliases = {
            alias.asname or alias.name
            for statement in ast.walk(tree)
            if isinstance(statement, ast.ImportFrom) and statement.module == "importlib"
            for alias in statement.names if alias.name == "import_module"
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name_called = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else "")
            first = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg == "name"), None
            )
            if name_called in {"import_module", "__import__"} or name_called in import_aliases:
                literal = _literal_string(first)
                if literal is not None:
                    if literal == module or literal.startswith(module + "."):
                        leads.append({"source": name, "line": node.lineno, "kind": "LITERAL_IMPORT",
                                      "confidence": "SOURCE_PATTERN_NOT_EXECUTED"})
                elif first is not None:
                    leads.append({"source": name, "line": node.lineno, "kind": "DYNAMIC_IMPORT_UNRESOLVED",
                                  "confidence": "UNKNOWN_TARGET"})
            elif name_called == "connect" and isinstance(func, ast.Attribute):
                if leaf in ast.unparse(node):
                    leads.append({"source": name, "line": node.lineno, "kind": "QT_CONNECT_CANDIDATE",
                                  "confidence": "UNKNOWN_SIGNAL_RECEIVER"})
            elif name_called == "getattr" and any(
                isinstance(arg, ast.Constant) and arg.value == leaf for arg in node.args
            ):
                leads.append({"source": name, "line": node.lineno, "kind": "REFLECTIVE_CANDIDATE",
                              "confidence": "UNKNOWN_OBJECT_IDENTITY"})
    static = {"status": "NOT_RUN", "confirmed_relationships": []}
    if (root / target).is_file():
        try:
            static = agent.reverse_impact_payload(root, [target], depth=1)
        except (RuntimeError, ValueError) as exc:
            static = {"status": "REVIEW", "reason": str(exc), "confirmed_relationships": []}
    confirmed = static.get("confirmed_relationships", [])
    return {
        "schema_version": 1, "kind": "doctor_consumer_sites",
        "status": "REVIEW", "target": target,
        "static_status": static.get("status"), "static_confirmed": confirmed[:MAX_ROWS],
        "static_confirmed_count": len(confirmed),
        "dynamic_leads": leads[:MAX_ROWS], "dynamic_lead_count": len(leads),
        "candidate_files": len(candidates),
        "truncated": len(candidates) > MAX_FILES or len(leads) > MAX_ROWS,
        "candidate_scan_complete": len(candidates) <= MAX_FILES and not errors,
        "source_errors": errors[:MAX_ROWS],
        "safe_to_delete": False, "dead_code_proven": False,
        "tests_executed": False, "graph_rebuilt": False,
        "limits": "Literal grep prefilter can miss runtime-generated imports, Qt registrations and plugin discovery. No leads does not prove zero consumers.",
    }
