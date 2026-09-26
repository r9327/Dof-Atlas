from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from tools import ai_context, atlas_integrity


ROOT = Path(__file__).resolve().parents[1]
CONTEXT_MAP = Path(".ai/context-map.yaml")


class AgentConfigError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AgentConfigError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _value(raw: str) -> Any:
    raw = raw.strip()
    if raw == "[]":
        return []
    return int(raw) if raw.isdigit() else raw


def _load_context_map(root: Path) -> dict[str, Any]:
    try:
        lines = (root / CONTEXT_MAP).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AgentConfigError(f"context map unavailable: {exc}") from exc

    payload: dict[str, Any] = {"rule_defaults": [], "scopes": {}}
    section = current_scope = current_list = ""
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            current_scope = current_list = ""
            if line.startswith("schema_version:"):
                payload["schema_version"] = _value(line.split(":", 1)[1])
            elif line == "rule_defaults:":
                section = "rule_defaults"
            elif line == "scopes:":
                section = "scopes"
            continue
        if section == "rule_defaults" and line.startswith("  - "):
            payload["rule_defaults"].append(line[4:].strip())
            continue
        if section != "scopes":
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
            current_scope = line.strip()[:-1]
            payload["scopes"][current_scope] = {}
            current_list = ""
            continue
        if not current_scope:
            continue
        if line.startswith("    ") and not line.startswith("      "):
            field = line.strip()
            if ": " in field:
                key, raw = field.split(": ", 1)
                payload["scopes"][current_scope][key] = _value(raw)
                current_list = ""
            elif field.endswith(":"):
                current_list = field[:-1]
                payload["scopes"][current_scope][current_list] = []
            continue
        if current_list and line.startswith("      - "):
            payload["scopes"][current_scope][current_list].append(line[8:].strip())

    if payload.get("schema_version") != 2 or not payload["scopes"]:
        raise AgentConfigError("context map must use schema_version 2 and declare scopes")
    return payload


def _load_manifest(root: Path, relative: str) -> dict[str, Any]:
    try:
        lines = (root / relative).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AgentConfigError(f"scope manifest unavailable: {relative}: {exc}") from exc

    payload: dict[str, Any] = {}
    current_list = ""
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            current_list = ""
            field = line.strip()
            if ": " in field:
                key, raw = field.split(": ", 1)
                payload[key] = _value(raw)
            elif field.endswith(":"):
                current_list = field[:-1]
                payload[current_list] = []
            continue
        if current_list and line.startswith("  - "):
            payload[current_list].append(line[4:].strip())

    if payload.get("schema_version") != 1:
        raise AgentConfigError(f"{relative}: schema_version must be 1")
    return payload


def _model(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    context_map = _load_context_map(root)
    manifests: dict[str, dict[str, Any]] = {}
    for scope, config in context_map["scopes"].items():
        relative = config.get("manifest")
        if not isinstance(relative, str) or not relative:
            raise AgentConfigError(f"{scope}: manifest path is missing")
        manifest = _load_manifest(root, relative)
        if manifest.get("scope") != scope or manifest.get("kind") != config.get("kind"):
            raise AgentConfigError(f"{scope}: manifest identity does not match context-map")
        manifests[scope] = manifest
    return context_map, manifests


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def doctor_payload(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    context_map, manifests = _model(root)
    errors: list[str] = []
    scopes = context_map["scopes"]
    for scope, manifest in manifests.items():
        declared = scopes[scope].get("implementation")
        if declared is not None and manifest.get("implementation") != declared:
            errors.append(f"{scope}: implementation mismatch")
        for dependency in manifest.get("shared_dependencies", []):
            config = scopes.get(dependency)
            if config is None:
                errors.append(f"{scope}: unknown shared dependency {dependency}")
            elif config.get("kind") != "shared_infrastructure":
                errors.append(f"{scope}: non-shared dependency {dependency}")

    index_current = ai_context.check_index(root)
    if not index_current:
        errors.append("committed context index is stale or missing")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "branch": _git(root, "branch", "--show-current"),
        "head": _git(root, "rev-parse", "HEAD"),
        "context_index_current": index_current,
        "scope_count": len(scopes),
        "errors": errors,
    }


def inspect_scope(root: Path, scope: str) -> dict[str, Any]:
    context_map, manifests = _model(root.resolve())
    config = context_map["scopes"].get(scope)
    if config is None:
        raise AgentConfigError(f"unknown scope: {scope}")
    manifest = manifests[scope]
    result = {
        "scope": scope,
        "kind": config.get("kind"),
        "manifest": config.get("manifest"),
        "rules": _unique([*context_map["rule_defaults"], *config.get("rule_entries", [])]),
        "canonical_entries": list(config.get("canonical_entries", [])),
        "working_set": list(manifest.get("working_set", [])),
        "shared_dependencies": list(manifest.get("shared_dependencies", [])),
        "context_entries": list(manifest.get("context_entries", [])),
    }
    implementation = config.get("implementation", manifest.get("implementation"))
    if implementation is not None:
        result["implementation"] = implementation
    return result


def _matches(path: str, anchor: str) -> bool:
    path = ai_context.normalize_path(path)
    anchor = ai_context.normalize_path(anchor)
    if anchor.endswith("/"):
        prefix = anchor.rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == anchor


def impact_payload(root: Path, paths: Iterable[str]) -> dict[str, Any]:
    root = root.resolve()
    normalized = _unique(ai_context.normalize_path(path) for path in paths)
    context_map, manifests = _model(root)
    matches: dict[str, list[str]] = {}
    scopes: list[str] = []
    for path in normalized:
        matched = [
            scope
            for scope, manifest in manifests.items()
            if any(_matches(path, anchor) for anchor in manifest.get("working_set", []))
        ]
        matches[path] = matched
        scopes.extend(scope for scope in matched if scope not in scopes)

    rules = list(context_map["rule_defaults"])
    canonical: list[str] = []
    dependencies: list[str] = []
    working_set: list[str] = []
    context_entries: list[str] = []
    for scope in scopes:
        config = context_map["scopes"][scope]
        manifest = manifests[scope]
        rules.extend(config.get("rule_entries", []))
        canonical.extend(config.get("canonical_entries", []))
        dependencies.extend(manifest.get("shared_dependencies", []))
        working_set.extend(manifest.get("working_set", []))
        context_entries.extend(manifest.get("context_entries", []))

    return {
        "paths": normalized,
        "domains": {path: ai_context.classify_path(path) for path in normalized},
        "scope_matches": matches,
        "scopes": scopes,
        "shared_dependencies": _unique(dependencies),
        "rules": _unique(rules),
        "canonical_entries": _unique(canonical),
        "working_set": _unique(working_set),
        "context_entries": _unique(context_entries),
        "recommended_tests": ai_context.recommended_tests(root, normalized),
    }


def _symbol_anchors(
    context_map: dict[str, Any],
    manifests: dict[str, dict[str, Any]],
    scope: str,
) -> list[str]:
    config = context_map["scopes"].get(scope)
    if config is None:
        raise AgentConfigError(f"unknown scope: {scope}")
    manifest = manifests[scope]
    return _unique(
        [
            *manifest.get("working_set", []),
            *manifest.get("context_entries", []),
            *config.get("canonical_entries", []),
        ]
    )


def _python_files_for_anchor(root: Path, anchor: str) -> list[str]:
    normalized = ai_context.normalize_path(anchor)
    target = root / normalized.rstrip("/")
    if target.is_file():
        return [normalized] if target.suffix.casefold() == ".py" else []
    if not target.is_dir():
        return []
    return [
        path.relative_to(root).as_posix()
        for path in sorted(target.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def symbol_files_for_scope(root: Path, scope: str) -> list[str]:
    root = root.resolve()
    context_map, manifests = _model(root)
    files: list[str] = []
    for anchor in _symbol_anchors(context_map, manifests, scope):
        files.extend(_python_files_for_anchor(root, anchor))
    return _unique(files)


def _python_symbols(root: Path, relative: str) -> list[dict[str, Any]]:
    source_path = root / relative
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AgentConfigError(f"python source unavailable: {relative}: {exc}") from exc
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        location = f"{relative}:{exc.lineno or '?'}"
        raise AgentConfigError(f"unable to parse Python source {location}: {exc.msg}") from exc

    symbols: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            kind = "class"
        elif isinstance(node, ast.AsyncFunctionDef):
            kind = "async_function"
        elif isinstance(node, ast.FunctionDef):
            kind = "function"
        else:
            continue
        symbols.append(
            {
                "name": node.name,
                "kind": kind,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            }
        )
    return symbols


def symbols_payload(root: Path, scope: str) -> dict[str, Any]:
    root = root.resolve()
    files = symbol_files_for_scope(root, scope)
    indexed: dict[str, list[dict[str, Any]]] = {}
    for relative in files:
        indexed[relative] = _python_symbols(root, relative)
    return {
        "schema_version": 1,
        "source": "scope-declared-python-ast",
        "scope": scope,
        "file_count": len(files),
        "symbol_count": sum(len(symbols) for symbols in indexed.values()),
        "files": indexed,
    }


def _print_payload(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"{key}:")
            for item in value:
                print(f"  - {item}")
        elif isinstance(value, dict):
            print(f"{key}:")
            for item, detail in value.items():
                print(f"  {item}: {detail}")
        else:
            print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal ROAD IA V2 agent helper.")
    commands = parser.add_subparsers(dest="command")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("scope")
    inspect.add_argument("--json", action="store_true")
    impact = commands.add_parser("impact")
    impact.add_argument("paths", nargs="+")
    impact.add_argument("--json", action="store_true")
    symbols = commands.add_parser("symbols")
    symbols.add_argument("scope")
    symbols.add_argument("--json", action="store_true")
    validate = commands.add_parser("validate")
    validate.add_argument("integrity_args", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    command = args.command or "doctor"
    try:
        if command == "validate":
            return atlas_integrity.main(list(args.integrity_args) or ["fast"])
        if command == "doctor":
            payload = doctor_payload(ROOT)
            exit_code = 0 if payload["status"] == "PASS" else 1
        elif command == "inspect":
            payload = inspect_scope(ROOT, args.scope)
            exit_code = 0
        elif command == "impact":
            payload = impact_payload(ROOT, args.paths)
            exit_code = 0
        elif command == "symbols":
            payload = symbols_payload(ROOT, args.scope)
            exit_code = 0
        else:
            parser.error(f"unsupported command: {command}")
            return 2
    except (AgentConfigError, RuntimeError, OSError) as exc:
        print(f"agent error: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_payload(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
