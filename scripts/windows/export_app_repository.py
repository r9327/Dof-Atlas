"""Export only runtime source/contracts into the separately managed App repository."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

_META = {"main.py", "launch.py", "sitecustomize.py", "requirements-pyside.txt"}
_DATA_SUFFIXES = {".json", ".db", ".ini"}
_RUNTIME_ROOTS = ("app/", "local_dofus_data/")
_FORBIDDEN = {"__pycache__", ".cache", ".git", "logs", "tests", "tools",
              ".github", ".agents", ".ai", ".codex", "reports", "local"}


def export(root: Path, destination: Path, source_sha: str) -> int:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0")
    selected: list[Path] = []
    for filename in tracked:
        if not filename:
            continue
        relative = Path(filename)
        if set(relative.parts) & _FORBIDDEN or relative.suffix == ".pyc":
            continue
        if filename in _META or filename.startswith(_RUNTIME_ROOTS):
            if relative.name == "AGENTS.md" or relative.suffix in (".md", ".rst"):
                continue
            selected.append(relative)
        elif filename.startswith("data/") and relative.suffix.lower() in _DATA_SUFFIXES:
            selected.append(relative)
    if not selected:
        raise RuntimeError("No runtime files found; refusing to wipe App repo")
    expected = {p.as_posix() for p in selected}
    expected.add("SOURCE_PROVENANCE.json")
    destination.mkdir(parents=True, exist_ok=True)
    # Remove only previously tracked runtime outputs; preserve the App repository .git.
    for folder in ("app", "local_dofus_data", "data"):
        target = destination / folder
        if target.exists():
            shutil.rmtree(target)
    for f in _META:
        (destination / f).unlink(missing_ok=True)
    count = 0
    for relative in selected:
        source = root / relative
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"Unexpected symlink/missing tracked source: {relative}")
        if source.stat().st_size > 50 * 1024 * 1024:
            raise RuntimeError(f"Runtime source unexpectedly exceeds 50 MiB: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
    (destination / "SOURCE_PROVENANCE.json").write_text(
        json.dumps({"source_repository": "r9327/Dof-Atlas", "source_sha": source_sha,
                    "runtime_files": count}, indent=2) + "\n",
        encoding="utf-8",
    )
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.root, args.destination, args.source_sha)} runtime files")


if __name__ == "__main__":
    main()
