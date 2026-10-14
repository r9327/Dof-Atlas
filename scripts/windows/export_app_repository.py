"""Explicit, fail-closed selection of application runtime files for the App mirror.

Development audit/certification stays in the canonical source repository.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

_META = frozenset({"main.py", "launch.py", "sitecustomize.py", "requirements-pyside.txt"})
_ESSENTIAL_ASSETS = frozenset({
    "data/images/misc/dofus_atlas_logo.png",
    "data/images/misc/dofus_atlas.ico",
    "data/local/zaaps.json",
    "data/dofus_atlas_world.db",
})
_DATA_ROOTS = ("data/encyclopedia/", "data/cartography/", "data/routes/")
_DATA_SUFFIXES = frozenset({".json", ".db", ".ini"})
_RUNTIME_ROOTS = ("app/", "local_dofus_data/")
_FORBIDDEN_COMPONENTS = frozenset({
    "__pycache__", ".cache", ".git", ".github", ".agents", ".ai", ".codex",
    "tests", "tools", "logs", "reports", "artifacts", ".venv", "venv", "local",
    "_rejected", "private", "debug", "temp", "tmp",
})
_PRIVATE_FILENAMES = frozenset({
    "client_profiles.json", "client_index.json", "client_index.ini",
    "network_character_bindings.json", "craft_selection.json",
    "quest_progress.json", "bootstrap_status.txt", "large_file_contracts.json",
})
_MAX_GIT_FILE = 95 * 1024 * 1024
_LFS_SIGNATURE = b"version https://git-lfs.github.com/spec/v1"
_SHA = re.compile(r"[a-f0-9]{40}\Z")


def selected_runtime_path(filename: str) -> bool:
    """One reviewable allowlist for code and public runtime data."""
    path = Path(filename)
    if (not filename or filename.startswith("/") or "\\" in filename
            or any(part in {"", ".", ".."} for part in filename.split("/"))
            or path.name.casefold() in _PRIVATE_FILENAMES
            or any(part.casefold() in _FORBIDDEN_COMPONENTS for part in path.parts)):
        return False
    if filename in _META or filename in _ESSENTIAL_ASSETS:
        return True
    if filename.startswith(_RUNTIME_ROOTS):
        return path.suffix.lower() == ".py"
    if filename.startswith(_DATA_ROOTS):
        return path.suffix.lower() in _DATA_SUFFIXES
    return False


def selected_runtime_files(root: Path) -> tuple[Path, ...]:
    """Tracked files only: do not copy untracked credentials or local data."""
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0")
    chosen = tuple(sorted({Path(name) for name in tracked if selected_runtime_path(name)},
                          key=lambda p: p.as_posix()))
    if not chosen or Path("main.py") not in chosen or Path("launch.py") not in chosen:
        raise RuntimeError("Missing mandatory application entry points; aborting mirror")
    normalized = [p.as_posix().casefold() for p in chosen]
    if len(normalized) != len(set(normalized)):
        raise RuntimeError("Windows case-insensitive collision in export")
    for relative in chosen:
        path = root / relative
        if (not path.is_file() or path.is_symlink()
                or any(parent.is_symlink() for parent in (root / relative).parents if parent != root)):
            raise RuntimeError(f"Unsafe runtime file: {relative}")
        if path.stat().st_size > _MAX_GIT_FILE:
            raise RuntimeError(f"Runtime Git file too large: {relative}")
        with path.open("rb") as stream:
            if stream.read(len(_LFS_SIGNATURE)) == _LFS_SIGNATURE:
                raise RuntimeError(f"Unresolved Git LFS pointer: {relative}")
    return chosen


def export(root: Path, destination: Path, source_sha: str) -> int:
    """Verify ALL source bytes before modifying the destination mirror."""
    if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
        raise ValueError("Invalid immutable source SHA")
    selected = selected_runtime_files(root)
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise RuntimeError("Refusing symlink distribution root")
    for folder in ("app", "local_dofus_data", "data"):
        target = destination / folder
        if target.is_symlink():
            raise RuntimeError("Refusing to clear linked runtime directory")
        if target.exists():
            shutil.rmtree(target)
    for f in _META:
        (destination / f).unlink(missing_ok=True)
    for relative in selected:
        source = root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (destination / "SOURCE_PROVENANCE.json").write_text(
        json.dumps({"source_repository": "r9327/Dof-Atlas", "source_sha": source_sha,
                    "runtime_files": len(selected)}, indent=2) + "\n", encoding="utf-8",
    )
    return len(selected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.root, args.destination, args.source_sha)} runtime files")


if __name__ == "__main__":
    main()
