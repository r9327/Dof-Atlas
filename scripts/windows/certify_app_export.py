"""Certify the Atlas App mirror; no Doctor/Graphify executable ships to App.

Uses the source inventory (Doctor-style policy) and the source Python import
graph (Graphify-style structural evidence). No claim of full runtime reachability.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path

from .export_app_repository import selected_runtime_files, selected_runtime_path

_RESERVED = frozenset({"README.md", ".gitignore", "SOURCE_PROVENANCE.json"})
_RUNTIME_PACKAGES = ("app", "local_dofus_data")


class TransferCertificationError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _module(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _candidate_modules(node: ast.AST, module: str, is_package: bool) -> set[str]:
    if isinstance(node, ast.Import):
        return {a.name for a in node.names}
    if not isinstance(node, ast.ImportFrom):
        return set()
    base = node.module or ""
    if node.level:
        package = module.split(".") if is_package else module.split(".")[:-1]
        climbs = node.level - 1
        if climbs >= len(package):
            return set()
        base = ".".join(package[:len(package) - climbs] + ([base] if base else []))
    result = {base} if base else set()
    result.update(base + "." + name.name for name in node.names
                  if base and name.name != "*")
    return result


def _resolve(root: Path, name: str) -> Path | None:
    parts = name.split(".")
    if not parts or parts[0] not in _RUNTIME_PACKAGES:
        return None
    py = Path(*parts).with_suffix(".py")
    init = Path(*parts) / "__init__.py"
    if (root / py).is_file():
        return py
    if (root / init).is_file():
        return init
    return None


def _walk_mirror(root: Path) -> set[Path]:
    files = set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        if base != root and base.is_symlink():
            raise TransferCertificationError(f"Linked App directory: {base}")
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in dirs:
            if (base / name).is_symlink():
                raise TransferCertificationError(f"Linked App directory: {base / name}")
        for name in names:
            file = base / name
            if file.is_symlink() or not file.is_file():
                raise TransferCertificationError(f"Linked/non-file App entry: {file}")
            files.add(file.relative_to(root))
    return files


def certify(source: Path, destination: Path, expected_sha: str,
            *, check_checkout: bool = True) -> dict:
    """Fail closed on unshipped imports, private files and stale/mutated mirror."""
    source = source.resolve()
    # Resolve only after checking the original path: resolve() hides a symlink.
    if destination.is_symlink():
        raise TransferCertificationError("Linked App destination is forbidden")
    destination = destination.resolve()
    if check_checkout:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, text=True
        ).strip()
        if sha != expected_sha:
            raise TransferCertificationError("Source checkout SHA does not match certificate")
    selected = selected_runtime_files(source)
    wanted = set(selected)
    if not destination.is_dir() or destination.is_symlink():
        raise TransferCertificationError("Missing/linked App destination")
    found = _walk_mirror(destination)
    unexpected = found - wanted - {Path(x) for x in _RESERVED}
    missing = wanted - found
    if missing or unexpected:
        raise TransferCertificationError(
            f"App mirror mismatch: missing={sorted(map(str, missing))[:8]}, "
            f"unexpected={sorted(map(str, unexpected))[:8]}"
        )
    if any(not selected_runtime_path(x.as_posix()) for x in found
           if x.as_posix() not in _RESERVED):
        raise TransferCertificationError("Unapproved file found in App mirror")
    try:
        provenance = json.loads((destination / "SOURCE_PROVENANCE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TransferCertificationError("Missing/invalid provenance") from exc
    if (provenance.get("source_repository") != "r9327/Dof-Atlas"
            or provenance.get("source_sha") != expected_sha
            or provenance.get("runtime_files") != len(selected)):
        raise TransferCertificationError("Stale or untrusted mirror provenance")
    total = 0
    for relative in selected:
        source_file = source / relative
        copied = destination / relative
        if source_file.stat().st_size != copied.stat().st_size or _digest(source_file) != _digest(copied):
            raise TransferCertificationError(f"Mirror content digest mismatch: {relative}")
        total += source_file.stat().st_size

    static_edges = set()
    python_files = [p for p in selected if p.suffix.lower() == ".py"]
    for relative in python_files:
        try:
            parsed = ast.parse((source / relative).read_text(encoding="utf-8"),
                               filename=relative.as_posix())
        except (SyntaxError, UnicodeError) as exc:
            raise TransferCertificationError(f"Invalid runtime Python module: {relative}") from exc
        parent = _module(relative)
        is_package = relative.name == "__init__.py"
        for node in ast.walk(parsed):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _candidate_modules(node, parent, is_package):
                candidate = _resolve(source, imported)
                if candidate is None:
                    continue
                if candidate not in wanted:
                    raise TransferCertificationError(
                        f"Runtime import excluded by transfer allowlist: {relative} -> {candidate}"
                    )
                static_edges.add((relative.as_posix(), candidate.as_posix()))
    return {
        "status": "PASS", "schema_version": 1, "source_sha": expected_sha,
        "file_count": len(selected), "python_modules": len(python_files),
        "total_bytes": total, "static_import_edges": len(static_edges),
        "checks": ["tracked_runtime_allowlist", "private_file_exclusion",
                   "exact_source_sha", "source_destination_sha256",
                   "mirror_inventory", "static_python_dependency_closure"],
        "limitations": ["Graphify AST edges do not prove dynamic imports, Qt signals, "
                        "reflection, external data asset completeness or runtime behavior",
                        "Doctor full certification and actual Windows smoke remain separate"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Certify App-only transfer, without installing Doctor")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = certify(args.root, args.destination, args.source_sha)
    except (TransferCertificationError, RuntimeError, OSError, ValueError) as exc:
        print(f"TRANSFER BLOCKED: {exc}")
        return 1
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
