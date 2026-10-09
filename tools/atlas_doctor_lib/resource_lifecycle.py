from __future__ import annotations

"""Advisory static evidence for Qt/WebEngine lifetime and Python cache bounds.

Never imports the application or starts Qt. Absence of evidence is not a leak.
"""
import ast
from pathlib import Path
from typing import Any

QT_TYPES = {"QWebEngineView", "QWebEnginePage", "QWebEngineProfile",
            "QThread", "QTimer", "QNetworkAccessManager"}
MAX_FILES, MAX_BYTES, MAX_RESULTS = 24, 512 * 1024, 80


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value) + "." + node.attr
    return ""


def inspect_resource_lifecycle(root: Path, paths: list[str]) -> dict[str, Any]:
    root = root.resolve()
    sources = sorted(set(paths))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    inspected: list[str] = []
    for relative in sources[:MAX_FILES]:
        path = Path(relative)
        if (path.is_absolute() or path.suffix != ".py" or
                "\\" in relative or ".." in path.parts):
            errors.append({"path": relative, "reason": "INVALID_PATH"})
            continue
        target = root / path
        if (target.is_symlink() or not target.is_file() or
                not target.resolve().is_relative_to(root)):
            errors.append({"path": relative, "reason": "MISSING_OR_SYMLINK"})
            continue
        try:
            if target.stat().st_size > MAX_BYTES:
                raise ValueError("SOURCE_TOO_LARGE")
            tree = ast.parse(target.read_text(encoding="utf-8-sig"), filename=relative)
        except (OSError, SyntaxError, UnicodeError, ValueError) as exc:
            errors.append({"path": relative, "reason": str(exc)[:80]})
            continue
        inspected.append(relative)
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (
                    node.module.startswith("PySide6.") or node.module.startswith("PyQt")):
                for alias in node.names:
                    if alias.name in QT_TYPES:
                        aliases[alias.asname or alias.name] = alias.name

        signals: set[str] = set()
        cleanup: set[str] = set()
        resources: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _name(node.func)
                method = name.rsplit(".", 1)[-1]
                if method in {"deleteLater", "setParent", "close", "clear", "cache_clear"}:
                    cleanup.add(method)
                if method == "connect" and isinstance(node.func, ast.Attribute):
                    signal = _name(node.func.value).rsplit(".", 1)[-1]
                    if signal in {"destroyed", "finished", "started", "aboutToQuit"}:
                        signals.add(signal)
                qt_type = aliases.get(name, method if method in QT_TYPES else None)
                if qt_type:
                    parent = next((keyword.value for keyword in node.keywords
                                   if keyword.arg == "parent"), None)
                    parent_evidence = ("KEYWORD_PARENT_PRESENT" if parent is not None
                                       and not (isinstance(parent, ast.Constant)
                                                and parent.value is None)
                                       else "PARENT_NOT_ESTABLISHED")
                    resources.append({
                        "path": relative, "line": node.lineno, "qt_type": qt_type,
                        "parent_evidence": parent_evidence,
                        "native_ownership_proven": False,
                        "confidence": "STATIC_AST_CONSTRUCTOR",
                    })
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    name = _name(decorator.func if isinstance(decorator, ast.Call)
                                 else decorator)
                    if name not in {"lru_cache", "functools.lru_cache", "cache",
                                    "functools.cache"}:
                        continue
                    bounded = False
                    if name.endswith("lru_cache") and isinstance(decorator, ast.Call):
                        values = [kw.value for kw in decorator.keywords if kw.arg == "maxsize"]
                        if not values and decorator.args:
                            values = decorator.args[:1]
                        bounded = any(isinstance(v, ast.Constant)
                                      and type(v.value) is int and v.value >= 0
                                      for v in values)
                        if not decorator.args and not decorator.keywords:
                            bounded = True
                    if not bounded:
                        results.append({
                            "path": relative, "line": node.lineno,
                            "symbol": node.name, "kind": "UNBOUNDED_CACHE_CANDIDATE",
                            "release_proven": False, "review_only": True,
                        })
        for resource in resources:
            resource["kind"] = "QT_RESOURCE_LIFECYCLE_CANDIDATE"
            resource["file_cleanup_calls"] = sorted(cleanup)
            resource["file_lifecycle_signals"] = sorted(signals)
            resource["review_only"] = True
            results.append(resource)
    truncated = len(sources) > MAX_FILES or len(results) > MAX_RESULTS
    return {
        "kind": "doctor_resource_lifecycle_review",
        "status": "REVIEW" if errors or results or truncated else "PASS",
        "files_inspected": inspected, "findings": results[:MAX_RESULTS],
        "errors": errors[:MAX_RESULTS], "truncated": truncated,
        "native_ownership_proven": False, "memory_leak_proven": False,
        "safe_to_delete": False, "tests_executed": False,
        "limits": "Bounded source-only hints, never proof of native QObject ownership or cache growth.",
    }
