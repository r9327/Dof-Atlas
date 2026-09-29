from __future__ import annotations

"""Read-only inventory of Dofus Atlas repository tooling.

The audit is deliberately informational. It discovers consolidation candidates
without deleting files, rewriting contracts or deciding that an unreferenced
maintenance tool is dead. Deletion still requires an explicit zero-consumer
review in a dedicated micro-lot.
"""

import argparse
import ast
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
_TOOL_SUFFIXES = {".py", ".ps1", ".sh", ".bat", ".cmd"}
_TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".sh",
    ".bat",
    ".cmd",
    ".yml",
    ".yaml",
    ".md",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
}
_REFERENCE_ROOTS = ("tools/", "tests/", ".github/", ".githooks/", "scripts/", "app/", "local_dofus_data/")
_MAX_TEXT_BYTES = 768 * 1024
_VERSION_RE = re.compile(r"^(?P<base>.+)_v(?P<version>\d+)$", flags=re.IGNORECASE)
_MUTATION_MARKERS = (
    ".write_text(",
    ".write_bytes(",
    ".unlink(",
    ".rename(",
    "os.replace(",
    "shutil.copy",
    "shutil.move",
    "set-content",
    "remove-item",
    "copy-item",
    "move-item",
)
_MUTATION_GATES = (
    "--apply",
    "--write",
    "--fix",
    "--repair",
    "--promote",
    "--sync",
    "--stage",
    "--output",
    "--json-output",
)


def _normalized(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _git_tracked_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        text=False,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return sorted(
            item.decode("utf-8", errors="surrogateescape")
            for item in completed.stdout.split(b"\0")
            if item
        )
    result: list[str] = []
    for path in root.rglob("*"):
        try:
            is_file = path.is_file()
        except OSError:
            continue
        if not is_file or ".git" in path.parts:
            continue
        result.append(path.relative_to(root).as_posix())
    return sorted(result)


def _read_text(root: Path, relative: str) -> str:
    path = root / relative
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _tool_paths(tracked: Iterable[str]) -> list[str]:
    return sorted(
        path
        for path in tracked
        if path.startswith("tools/") and Path(path).suffix.casefold() in _TOOL_SUFFIXES
    )


def _reference_paths(tracked: Iterable[str]) -> list[str]:
    rows: list[str] = []
    for path in tracked:
        suffix = Path(path).suffix.casefold()
        if suffix not in _TEXT_SUFFIXES:
            continue
        if path.startswith(_REFERENCE_ROOTS) or "/" not in path:
            rows.append(path)
    return rows


def _python_shape(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"parse_error": True, "has_main": False, "imports_tools": False}
    has_main = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        for node in tree.body
    )
    has_main_guard = False
    imports_tools = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            try:
                test = ast.unparse(node.test)
            except Exception:
                test = ""
            if "__name__" in test and "__main__" in test:
                has_main_guard = True
        elif isinstance(node, ast.Import):
            imports_tools = imports_tools or any(
                alias.name == "tools" or alias.name.startswith("tools.")
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imports_tools = imports_tools or bool(
                node.module and (node.module == "tools" or node.module.startswith("tools."))
            )
    return {
        "parse_error": False,
        "has_main": has_main or has_main_guard,
        "imports_tools": imports_tools,
    }


def _nonblank_line_count(source: str) -> int:
    return sum(1 for line in source.splitlines() if line.strip())


def _is_executable(path: str, source: str, shape: dict[str, Any]) -> bool:
    suffix = Path(path).suffix.casefold()
    if suffix == ".py":
        return bool(shape.get("has_main"))
    return suffix in {".ps1", ".sh", ".bat", ".cmd"}


def _is_wrapper(path: str, source: str, shape: dict[str, Any]) -> bool:
    line_count = _nonblank_line_count(source)
    suffix = Path(path).suffix.casefold()
    lowered = source.casefold().replace("\\", "/")
    if suffix == ".py":
        delegates = (
            ".main(" in source
            or "raise systemexit(" in lowered
            or "systemexit(main(" in lowered
        )
        return line_count <= 140 and bool(shape.get("imports_tools")) and delegates
    if suffix in {".ps1", ".sh", ".bat", ".cmd"}:
        delegates = "tools/" in lowered or "tools." in lowered
        return line_count <= 40 and delegates
    return False


def _reference_tokens(path: str) -> tuple[str, ...]:
    posix = _normalized(path)
    tokens = [posix, posix.replace("/", "\\")]
    if posix.endswith(".py"):
        tokens.append(posix[:-3].replace("/", "."))
    elif posix.endswith(".ps1"):
        tokens.append(Path(posix).name)
    # The stem alone is intentionally not used: short/generic stems generate
    # too many false positives in docs and test names.
    return tuple(dict.fromkeys(tokens))


def _reference_counts(
    *,
    root: Path,
    tool_paths: list[str],
    reference_paths: list[str],
) -> dict[str, dict[str, Any]]:
    corpus: dict[str, str] = {}
    for relative in reference_paths:
        text = _read_text(root, relative)
        if text:
            corpus[relative] = text

    result: dict[str, dict[str, Any]] = {}
    for tool in tool_paths:
        tokens = _reference_tokens(tool)
        refs: list[str] = []
        test_refs: list[str] = []
        for relative, text in corpus.items():
            if relative == tool:
                continue
            if any(token in text for token in tokens):
                refs.append(relative)
                if relative.startswith("tests/"):
                    test_refs.append(relative)
        result[tool] = {
            "references": sorted(refs),
            "test_references": sorted(test_refs),
        }
    return result


def _versioned_families(tool_paths: Iterable[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for path in tool_paths:
        candidate = Path(path)
        match = _VERSION_RE.match(candidate.stem)
        if not match:
            continue
        grouped[(candidate.parent.as_posix(), match.group("base"))].append(
            (int(match.group("version")), path)
        )

    families: list[dict[str, Any]] = []
    for (parent, base), rows in sorted(grouped.items()):
        if len(rows) < 2:
            continue
        rows.sort()
        families.append(
            {
                "family": f"{parent}/{base}" if parent != "." else base,
                "versions": [version for version, _ in rows],
                "members": [path for _, path in rows],
                "recommendation": "consolidate_after_contract_and_consumer_review",
            }
        )
    return families


def _suggestion(row: dict[str, Any], version_members: set[str]) -> str:
    path = str(row["path"])
    if path in version_members:
        return "consolidate_version_family"
    if row["wrapper"]:
        return "review_wrapper_for_absorption"
    if row["path_hack"]:
        return "remove_import_path_hack"
    if row["executable"] and not row["references"] and not row["test_references"]:
        return "review_unreferenced_entrypoint"
    if row["executable"] and not row["test_references"]:
        return "add_or_confirm_targeted_test_coverage"
    return "keep_or_review_in_place"


def audit(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    tracked = _git_tracked_paths(root)
    tool_paths = _tool_paths(tracked)
    refs = _reference_counts(
        root=root,
        tool_paths=tool_paths,
        reference_paths=_reference_paths(tracked),
    )
    families = _versioned_families(tool_paths)
    version_members = {
        member
        for family in families
        for member in family["members"]
    }

    tools: list[dict[str, Any]] = []
    for path in tool_paths:
        source = _read_text(root, path)
        suffix = Path(path).suffix.casefold()
        shape = (
            _python_shape(source)
            if suffix == ".py"
            else {"parse_error": False, "has_main": True, "imports_tools": False}
        )
        lowered = source.casefold()
        executable = _is_executable(path, source, shape)
        row = {
            "path": path,
            "kind": "python" if suffix == ".py" else "script",
            "line_count": _nonblank_line_count(source),
            "executable": executable,
            "library": suffix == ".py" and not executable,
            "wrapper": _is_wrapper(path, source, shape),
            "path_hack": "sys.path.insert" in source or "sys.path.append" in source,
            "cwd_dependency": "path.cwd()" in lowered or "os.getcwd()" in lowered,
            "mutation_capable": any(marker in lowered for marker in _MUTATION_MARKERS),
            "explicit_mutation_gate": any(flag in lowered for flag in _MUTATION_GATES),
            "references": refs[path]["references"],
            "test_references": refs[path]["test_references"],
            "parse_error": bool(shape.get("parse_error")),
        }
        row["recommendation"] = _suggestion(row, version_members)
        tools.append(row)

    wrappers = [row["path"] for row in tools if row["wrapper"]]
    path_hacks = [row["path"] for row in tools if row["path_hack"]]
    cwd_dependencies = [row["path"] for row in tools if row["cwd_dependency"]]
    mutation_capable = [row["path"] for row in tools if row["mutation_capable"]]
    mutation_without_gate = [
        row["path"]
        for row in tools
        if row["mutation_capable"] and not row["explicit_mutation_gate"]
    ]
    unreferenced = [
        row["path"]
        for row in tools
        if row["executable"] and not row["references"] and not row["test_references"]
    ]
    test_gaps = [
        row["path"]
        for row in tools
        if row["executable"] and not row["test_references"]
    ]
    parse_errors = [row["path"] for row in tools if row["parse_error"]]

    review_count = sum(
        bool(group)
        for group in (
            families,
            wrappers,
            path_hacks,
            cwd_dependencies,
            mutation_without_gate,
            unreferenced,
            test_gaps,
            parse_errors,
        )
    )
    return {
        "schema_version": 1,
        "status": "REVIEW_REQUIRED" if review_count else "CLEAN",
        "blocking": False,
        "source": "tracked_repository_tool_inventory",
        "tool_count": len(tools),
        "executable_count": sum(1 for row in tools if row["executable"]),
        "library_count": sum(1 for row in tools if row["library"]),
        "versioned_family_count": len(families),
        "wrapper_count": len(wrappers),
        "path_hack_count": len(path_hacks),
        "cwd_dependency_count": len(cwd_dependencies),
        "mutation_capable_count": len(mutation_capable),
        "mutation_without_gate_count": len(mutation_without_gate),
        "unreferenced_executable_count": len(unreferenced),
        "targeted_test_gap_count": len(test_gaps),
        "parse_error_count": len(parse_errors),
        "versioned_families": families,
        "wrappers": wrappers,
        "path_hacks": path_hacks,
        "cwd_dependencies": cwd_dependencies,
        "mutation_capable": mutation_capable,
        "mutation_without_gate": mutation_without_gate,
        "unreferenced_executables": unreferenced,
        "targeted_test_gaps": test_gaps,
        "parse_errors": parse_errors,
        "tools": tools,
        "note": (
            "Informational only. A zero-reference result is a review candidate, not proof that a tool is dead. "
            "Deletion still requires explicit consumer and contract review."
        ),
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"tooling audit: {report['status']} (blocking={report['blocking']})")
    print(
        "tools={tool_count} executable={executable_count} libraries={library_count} "
        "version_families={versioned_family_count} wrappers={wrapper_count} "
        "path_hacks={path_hack_count} unreferenced={unreferenced_executable_count} "
        "test_gaps={targeted_test_gap_count}".format(**report)
    )
    if report["versioned_families"]:
        print("versioned families:")
        for family in report["versioned_families"]:
            print(f"  - {family['family']}: {', '.join(family['members'])}")
    if report["path_hacks"]:
        print("import path hacks:")
        for path in report["path_hacks"]:
            print(f"  - {path}")
    if report["unreferenced_executables"]:
        print("unreferenced entrypoints to review:")
        for path in report["unreferenced_executables"]:
            print(f"  - {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Dofus Atlas tooling consolidation audit."
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional UTF-8 JSON report path.",
    )
    args = parser.parse_args(argv)

    report = audit(ROOT)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    # This first audit is intentionally non-blocking. It informs later cleanup
    # micro-lots but never makes CI green/red by itself.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
