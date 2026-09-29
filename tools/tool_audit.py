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
        # utf-8-sig accepts normal UTF-8 while stripping an optional BOM.
        # Python itself accepts BOM-marked UTF-8 source, so the tooling audit
        # must not report those files as AST parse errors.
        return path.read_text(encoding="utf-8-sig", errors="replace")
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
    if row.get("parse_error"):
        return "review_parse_error"
    if row.get("mutation_capable") and not row.get("explicit_mutation_gate"):
        return "review_mutation_safety"
    if path in version_members:
        return "review_version_family"
    if row.get("wrapper"):
        return "review_wrapper_absorption"
    if row.get("executable") and not row.get("references"):
        return "review_unreferenced_entrypoint"
    if row.get("path_hack"):
        return "review_import_path_hack"
    if row.get("cwd_dependency"):
        return "review_cwd_dependency"
    if row.get("executable") and not row.get("test_references"):
        return "review_targeted_test_gap"
    return "keep_or_review_manually"


def _tool_row(
    *,
    root: Path,
    path: str,
    references: dict[str, Any],
) -> dict[str, Any]:
    source = _read_text(root, path)
    suffix = Path(path).suffix.casefold()
    shape = _python_shape(source) if suffix == ".py" else {
        "parse_error": False,
        "has_main": False,
        "imports_tools": False,
    }
    lowered = source.casefold()
    mutation_capable = any(marker in lowered for marker in _MUTATION_MARKERS)
    explicit_mutation_gate = mutation_capable and any(
        marker in lowered for marker in _MUTATION_GATES
    )
    cwd_dependency = "path.cwd(" in lowered or "get-location" in lowered or "$pwd" in lowered
    path_hack = "sys.path.insert" in lowered or "sys.path.append" in lowered
    row = {
        "path": path,
        "kind": suffix.lstrip("."),
        "line_count": _nonblank_line_count(source),
        "parse_error": bool(shape.get("parse_error")),
        "executable": _is_executable(path, source, shape),
        "wrapper": _is_wrapper(path, source, shape),
        "path_hack": path_hack,
        "cwd_dependency": cwd_dependency,
        "mutation_capable": mutation_capable,
        "explicit_mutation_gate": explicit_mutation_gate,
        "references": list(references.get("references", [])),
        "test_references": list(references.get("test_references", [])),
    }
    return row


def audit(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    tracked = _git_tracked_paths(root)
    tool_paths = _tool_paths(tracked)
    reference_paths = _reference_paths(tracked)
    references = _reference_counts(
        root=root,
        tool_paths=tool_paths,
        reference_paths=reference_paths,
    )
    families = _versioned_families(tool_paths)
    version_members = {
        path
        for family in families
        for path in family["members"]
    }
    tools = [
        _tool_row(root=root, path=path, references=references[path])
        for path in tool_paths
    ]
    for row in tools:
        row["recommendation"] = _suggestion(row, version_members)

    parse_errors = [row["path"] for row in tools if row["parse_error"]]
    wrappers = [row["path"] for row in tools if row["wrapper"]]
    path_hacks = [row["path"] for row in tools if row["path_hack"]]
    cwd_dependencies = [row["path"] for row in tools if row["cwd_dependency"]]
    mutation_capable = [row["path"] for row in tools if row["mutation_capable"]]
    mutation_without_gate = [
        row["path"]
        for row in tools
        if row["mutation_capable"] and not row["explicit_mutation_gate"]
    ]
    unreferenced_entrypoints = [
        row["path"]
        for row in tools
        if row["executable"] and not row["references"]
    ]
    targeted_test_gaps = [
        row["path"]
        for row in tools
        if row["executable"] and not row["test_references"]
    ]
    review_candidates = [
        row["path"]
        for row in tools
        if row["recommendation"] != "keep_or_review_manually"
    ]
    return {
        "schema_version": 1,
        "source": "tracked-repository-tooling",
        "read_only": True,
        "blocking": False,
        "status": "REVIEW_REQUIRED" if review_candidates else "CLEAN",
        "note": (
            "Findings are consolidation review candidates only. Zero references, "
            "wrapper status or a versioned filename is not proof that a tool is dead."
        ),
        "tool_count": len(tools),
        "versioned_family_count": len(families),
        "wrapper_count": len(wrappers),
        "parse_error_count": len(parse_errors),
        "path_hack_count": len(path_hacks),
        "cwd_dependency_count": len(cwd_dependencies),
        "mutation_capable_count": len(mutation_capable),
        "mutation_without_gate_count": len(mutation_without_gate),
        "unreferenced_entrypoint_count": len(unreferenced_entrypoints),
        "targeted_test_gap_count": len(targeted_test_gaps),
        "review_candidate_count": len(review_candidates),
        "versioned_families": families,
        "wrappers": wrappers,
        "parse_errors": parse_errors,
        "path_hacks": path_hacks,
        "cwd_dependencies": cwd_dependencies,
        "mutation_capable": mutation_capable,
        "mutation_without_gate": mutation_without_gate,
        "unreferenced_entrypoints": unreferenced_entrypoints,
        "targeted_test_gaps": targeted_test_gaps,
        "review_candidates": review_candidates,
        "tools": tools,
    }


def _print_list(label: str, values: Iterable[str]) -> None:
    rows = list(values)
    if not rows:
        return
    print(f"{label} ({len(rows)}):")
    for value in rows:
        print(f"  - {value}")


def _print_human(report: dict[str, Any]) -> None:
    print("TOOLING CONSOLIDATION AUDIT")
    print()
    print(f"Tools                       {report['tool_count']}")
    print(f"Versioned families          {report['versioned_family_count']}")
    print(f"Thin wrappers               {report['wrapper_count']}")
    print(f"Parse errors                {report['parse_error_count']}")
    print(f"sys.path hacks              {report['path_hack_count']}")
    print(f"cwd-coupled tools           {report['cwd_dependency_count']}")
    print(f"Mutation-capable            {report['mutation_capable_count']}")
    print(f"Mutators without gate       {report['mutation_without_gate_count']}")
    print(f"Unreferenced entrypoints    {report['unreferenced_entrypoint_count']}")
    print(f"Targeted-test gaps          {report['targeted_test_gap_count']}")
    print(f"Review candidates           {report['review_candidate_count']}")
    print()
    for family in report["versioned_families"]:
        print(
            f"VERSION FAMILY {family['family']}: "
            f"{', '.join(str(version) for version in family['versions'])}"
        )
        for member in family["members"]:
            print(f"  - {member}")
    _print_list("WRAPPERS", report["wrappers"])
    _print_list("PARSE ERRORS", report["parse_errors"])
    _print_list("PATH HACKS", report["path_hacks"])
    _print_list("CWD DEPENDENCIES", report["cwd_dependencies"])
    _print_list("MUTATORS WITHOUT EXPLICIT GATE", report["mutation_without_gate"])
    _print_list("UNREFERENCED ENTRYPOINTS (review only)", report["unreferenced_entrypoints"])
    _print_list("TARGETED TEST GAPS", report["targeted_test_gaps"])
    print()
    print("NOTE:")
    print(report["note"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only inventory of repository tooling consolidation candidates."
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit(ROOT)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
