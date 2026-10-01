from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from tools import agent_planner, ai_context, atlas_integrity


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


def _test_module_path(module: str) -> Path:
    return Path(*module.split(".")).with_suffix(".py")


def _scope_test_mapping_errors(root: Path, context_map: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for scope, config in context_map["scopes"].items():
        tests = config.get("test_entries")
        if not isinstance(tests, list):
            errors.append(f"{scope}: test_entries must be an explicit list")
            continue
        if len(tests) != len(_unique(str(module) for module in tests)):
            errors.append(f"{scope}: duplicate test_entries")
        for module in tests:
            if not isinstance(module, str) or not module.startswith("tests."):
                errors.append(f"{scope}: invalid test module {module}")
                continue
            if not (root / _test_module_path(module)).is_file():
                errors.append(f"{scope}: missing test module {module}")
    return errors


def doctor_payload(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    context_map, manifests = _model(root)
    errors: list[str] = []
    scopes = context_map["scopes"]
    errors.extend(_scope_test_mapping_errors(root, context_map))
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

    conflicts = _declared_ownership_conflicts(context_map, manifests)
    for conflict in conflicts:
        errors.append(
            "ambiguous working_set anchor "
            f"{conflict['anchor']}: {', '.join(conflict['scopes'])}"
        )

    index_current = ai_context.check_index(root)
    if not index_current:
        errors.append("committed context index is stale or missing")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "branch": _git(root, "branch", "--show-current"),
        "head": _git(root, "rev-parse", "HEAD"),
        "context_index_current": index_current,
        "scope_count": len(scopes),
        "ownership_conflicts": conflicts,
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
        "test_entries": list(config.get("test_entries", [])),
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


def _scope_implementation(config: dict[str, Any], manifest: dict[str, Any]) -> str:
    implementation = config.get("implementation", manifest.get("implementation"))
    return str(implementation or "")


def _anchor_specificity(anchor: str) -> tuple[int, int, int]:
    normalized = ai_context.normalize_path(anchor)
    trimmed = normalized.rstrip("/")
    parts = [part for part in trimmed.split("/") if part]
    exact = 0 if normalized.endswith("/") else 1
    return len(parts), exact, len(trimmed)


def _scope_match_details(
    context_map: dict[str, Any],
    manifests: dict[str, dict[str, Any]],
    path: str,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for scope, manifest in manifests.items():
        matching_anchors = [
            anchor
            for anchor in manifest.get("working_set", [])
            if _matches(path, anchor)
        ]
        if not matching_anchors:
            continue
        anchor = max(matching_anchors, key=_anchor_specificity)
        config = context_map["scopes"][scope]
        details.append(
            {
                "scope": scope,
                "kind": config.get("kind"),
                "anchor": ai_context.normalize_path(anchor),
                "manifest": config.get("manifest"),
                "implementation": _scope_implementation(config, manifest),
            }
        )
    return details


def _ownership_detail(
    context_map: dict[str, Any],
    manifests: dict[str, dict[str, Any]],
    path: str,
) -> dict[str, Any]:
    matched = _scope_match_details(context_map, manifests, path)
    active = [detail for detail in matched if detail["implementation"] != "placeholder"]
    placeholders = [detail for detail in matched if detail["implementation"] == "placeholder"]

    candidates: list[dict[str, Any]] = []
    if active:
        best = max(_anchor_specificity(detail["anchor"]) for detail in active)
        candidates = [
            detail
            for detail in active
            if _anchor_specificity(detail["anchor"]) == best
        ]

    if not candidates:
        status = "UNOWNED"
        primary = None
        maintenance_hint = "assign one primary scope working_set; create a scope only if no existing scope fits"
    elif len(candidates) == 1:
        status = "OWNED"
        primary = candidates[0]
        maintenance_hint = ""
    else:
        status = "AMBIGUOUS"
        primary = None
        maintenance_hint = (
            "keep one primary working_set owner; move secondary use to context_entries "
            "or shared_dependencies"
        )

    candidate_scopes = [detail["scope"] for detail in candidates]
    return {
        "status": status,
        "primary_scope": primary["scope"] if primary else None,
        "primary_anchor": primary["anchor"] if primary else None,
        "candidate_scopes": candidate_scopes,
        "matched_scopes": [detail["scope"] for detail in matched],
        "shadowed_scopes": [
            detail["scope"]
            for detail in active
            if detail["scope"] not in candidate_scopes
        ],
        "placeholder_scopes": [detail["scope"] for detail in placeholders],
        "review_manifests": _unique(
            str(detail["manifest"])
            for detail in candidates
            if detail.get("manifest")
        ),
        "maintenance_hint": maintenance_hint,
    }


def ownership_payload(root: Path, paths: Iterable[str]) -> dict[str, Any]:
    root = root.resolve()
    normalized = _unique(ai_context.normalize_path(path) for path in paths)
    context_map, manifests = _model(root)
    details = {
        path: _ownership_detail(context_map, manifests, path)
        for path in normalized
    }
    unowned = [path for path, detail in details.items() if detail["status"] == "UNOWNED"]
    ambiguous = [path for path, detail in details.items() if detail["status"] == "AMBIGUOUS"]
    return {
        "schema_version": 1,
        "source": "scope-working-set-ownership",
        "status": "WARN" if unowned or ambiguous else "PASS",
        "paths": details,
        "unowned_paths": unowned,
        "ambiguous_paths": ambiguous,
    }


def _declared_ownership_conflicts(
    context_map: dict[str, Any],
    manifests: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    owners: dict[str, list[str]] = {}
    for scope, manifest in manifests.items():
        config = context_map["scopes"][scope]
        if _scope_implementation(config, manifest) == "placeholder":
            continue
        for anchor in manifest.get("working_set", []):
            normalized = ai_context.normalize_path(anchor)
            owners.setdefault(normalized, []).append(scope)

    conflicts: list[dict[str, Any]] = []
    for anchor, scopes in sorted(owners.items()):
        unique_scopes = _unique(scopes)
        if len(unique_scopes) < 2:
            continue
        conflicts.append(
            {
                "anchor": anchor,
                "scopes": unique_scopes,
                "manifests": [
                    context_map["scopes"][scope]["manifest"]
                    for scope in unique_scopes
                ],
            }
        )
    return conflicts


def ownership_conflicts(root: Path = ROOT) -> list[dict[str, Any]]:
    context_map, manifests = _model(root.resolve())
    return _declared_ownership_conflicts(context_map, manifests)


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
    scope_tests: list[str] = []
    for scope in scopes:
        config = context_map["scopes"][scope]
        manifest = manifests[scope]
        rules.extend(config.get("rule_entries", []))
        canonical.extend(config.get("canonical_entries", []))
        scope_tests.extend(config.get("test_entries", []))
        dependencies.extend(manifest.get("shared_dependencies", []))
        working_set.extend(manifest.get("working_set", []))
        context_entries.extend(manifest.get("context_entries", []))

    ownership = {
        path: _ownership_detail(context_map, manifests, path)
        for path in normalized
    }
    explicit_tests = _unique(scope_tests)
    fallback_tests = ai_context.recommended_tests(root, normalized)
    return {
        "paths": normalized,
        "domains": {path: ai_context.classify_path(path) for path in normalized},
        "scope_matches": matches,
        "scopes": scopes,
        "ownership": ownership,
        "unowned_paths": [
            path for path, detail in ownership.items() if detail["status"] == "UNOWNED"
        ],
        "ambiguous_paths": [
            path for path, detail in ownership.items() if detail["status"] == "AMBIGUOUS"
        ],
        "shared_dependencies": _unique(dependencies),
        "rules": _unique(rules),
        "canonical_entries": _unique(canonical),
        "working_set": _unique(working_set),
        "context_entries": _unique(context_entries),
        "scope_tests": explicit_tests,
        "recommended_tests": _unique([*explicit_tests, *fallback_tests]),
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


def _parse_python_ast(root: Path, relative: str) -> ast.Module:
    source_path = root / relative
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AgentConfigError(f"python source unavailable: {relative}: {exc}") from exc
    try:
        return ast.parse(source, filename=relative)
    except SyntaxError as exc:
        location = f"{relative}:{exc.lineno or '?'}"
        raise AgentConfigError(f"unable to parse Python source {location}: {exc.msg}") from exc


def _python_symbols(root: Path, relative: str) -> list[dict[str, Any]]:
    tree = _parse_python_ast(root, relative)
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


def _working_set_python_files(root: Path, manifest: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for anchor in manifest.get("working_set", []):
        files.extend(_python_files_for_anchor(root, anchor))
    return _unique(files)


def _module_path(root: Path, module: str) -> str | None:
    if not module:
        return None
    target = root.joinpath(*module.split("."))
    module_file = target.with_suffix(".py")
    if module_file.is_file():
        return module_file.relative_to(root).as_posix()
    package_file = target / "__init__.py"
    if package_file.is_file():
        return package_file.relative_to(root).as_posix()
    return None


def _import_from_module(relative: str, node: ast.ImportFrom) -> str:
    if node.level:
        package = list(Path(relative).with_suffix("").parent.parts)
        trim = node.level - 1
        if trim > len(package):
            return ""
        prefix = package[: len(package) - trim] if trim else package
    else:
        prefix = []
    suffix = node.module.split(".") if node.module else []
    return ".".join([*prefix, *suffix])


def _internal_imports(root: Path, relative: str) -> list[str]:
    tree = _parse_python_ast(root, relative)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _module_path(root, alias.name)
                if resolved:
                    imports.append(resolved)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        module = _import_from_module(relative, node)
        if node.module is None:
            for alias in node.names:
                child = ".".join(part for part in (module, alias.name) if part)
                resolved = _module_path(root, child)
                if resolved:
                    imports.append(resolved)
            continue
        resolved = _module_path(root, module)
        if resolved:
            imports.append(resolved)
        # from package import submodule also imports the existing child module.
        for alias in node.names:
            child = ".".join(part for part in (module, alias.name) if part)
            resolved = _module_path(root, child)
            if resolved:
                imports.append(resolved)
    return _unique(imports)


def imports_payload(root: Path, scope: str) -> dict[str, Any]:
    root = root.resolve()
    context_map, manifests = _model(root)
    if scope not in context_map["scopes"]:
        raise AgentConfigError(f"unknown scope: {scope}")
    manifest = manifests[scope]
    working_set = list(manifest.get("working_set", []))
    source_files = _working_set_python_files(root, manifest)
    edges: dict[str, list[str]] = {}
    dependencies: list[str] = []
    for relative in source_files:
        resolved = _internal_imports(root, relative)
        edges[relative] = resolved
        dependencies.extend(
            path
            for path in resolved
            if not any(_matches(path, anchor) for anchor in working_set)
        )
    import_dependencies = _unique(dependencies)
    return {
        "schema_version": 1,
        "source": "scope-working-set-python-imports",
        "scope": scope,
        "file_count": len(source_files),
        "edge_count": sum(len(paths) for paths in edges.values()),
        "files": edges,
        "import_dependencies": import_dependencies,
        "enriched_working_set": _unique([*working_set, *import_dependencies]),
    }


def reverse_impact_payload(
    root: Path, paths: Iterable[str], *, symbol: str | None = None, depth: int = 1,
) -> dict[str, Any]:
    """Compose graph candidates with the existing Agent source/context engines."""
    from tools.agent_graph import reverse_impact

    try:
        return reverse_impact(
            root, list(paths), symbol=symbol, depth=depth,
            imports_resolver=_internal_imports, symbols_resolver=_python_symbols,
            impact_resolver=impact_payload,
        )
    except ValueError as exc:
        raise AgentConfigError(str(exc)) from exc


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
    reverse = commands.add_parser("reverse-impact", help="Read a current graph; confirm bounded consumer imports without rebuilding.")
    reverse.add_argument("paths", nargs="+")
    reverse.add_argument("--symbol", help="Top-level symbol candidates; requires review of binding.")
    reverse.add_argument("--depth", type=int, choices=(1, 2), default=1)
    reverse.add_argument("--json", action="store_true")
    ownership = commands.add_parser("ownership")
    ownership.add_argument("paths", nargs="+")
    ownership.add_argument("--json", action="store_true")
    symbols = commands.add_parser("symbols")
    symbols.add_argument("scope")
    symbols.add_argument("--json", action="store_true")
    imports = commands.add_parser("imports")
    imports.add_argument("scope")
    imports.add_argument("--json", action="store_true")
    plan = commands.add_parser("plan")
    plan.add_argument("paths", nargs="+")
    plan.add_argument("--json", action="store_true")
    levels = plan.add_mutually_exclusive_group()
    levels.add_argument("--soft", dest="level", action="store_const", const="SOFT")
    levels.add_argument("--medium", dest="level", action="store_const", const="MEDIUM")
    levels.add_argument("--hard", dest="level", action="store_const", const="HARD")
    plan.add_argument("--structural", action="store_true", help="Refactor, module move/deletion, consumers, cycles or dependency cleanup: require Graphify preflight.")
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
        elif command == "reverse-impact":
            payload = reverse_impact_payload(ROOT, args.paths, symbol=args.symbol, depth=args.depth)
            exit_code = 0 if payload["status"] == "PASS" else 1
        elif command == "ownership":
            payload = ownership_payload(ROOT, args.paths)
            exit_code = 0
        elif command == "symbols":
            payload = symbols_payload(ROOT, args.scope)
            exit_code = 0
        elif command == "imports":
            payload = imports_payload(ROOT, args.scope)
            exit_code = 0
        elif command == "plan":
            impact = impact_payload(ROOT, args.paths)
            graph_impact = None
            if args.structural:
                graph_impact = reverse_impact_payload(ROOT, args.paths)
                impact["recommended_tests"] = _unique([
                    *impact.get("recommended_tests", []),
                    *graph_impact.get("recommended_tests", []),
                ])
                impact["scopes"] = _unique([
                    *impact.get("scopes", []), *graph_impact.get("scopes", []),
                ])
            options = {}
            if args.level:
                options["level"] = args.level
            if args.structural:
                options["structural"] = True
            payload = agent_planner.build_plan(ROOT, args.paths, impact, **options)
            graph = graph_impact["graph"] if graph_impact else None
            payload["architecture_preflight"] = {
                "required": args.structural,
                "status": graph["status"] if graph else "OPTIONAL",
                "graph": graph,
                "impact": graph_impact,
                "diagnostic_command": ["py", "-3.13", "-m", "tools.atlas_doctor", "graph", "--json"],
                "rebuild_command": ["py", "-3.13", "-m", "tools.atlas_doctor", "graph", "--rebuild", "--json"],
                "rule": "Confirm graph relationships against source, consumers, tests and Atlas Integrity before structural changes.",
            }
            if args.structural and (graph["status"] != "PASS" or graph_impact["status"] != "PASS"):
                payload["status"] = "REVIEW_REQUIRED"
                payload["automation_safe"] = False
                payload.setdefault("policy", {})["automatic_editing"] = "requires_human_or_agent_review"
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