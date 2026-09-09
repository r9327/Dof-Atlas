from __future__ import annotations

import argparse
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.check_generated_files import find_forbidden, find_sensitive_content, git_paths


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], root: Path) -> int:
    return subprocess.run(command, cwd=root, check=False).returncode


def staged_python_files(root: Path) -> list[Path]:
    return [root / path for path in git_paths(root, staged=True) if path.endswith(".py")]


def check_staged_syntax(root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="atlas-hook-") as directory:
        for index, path in enumerate(staged_python_files(root)):
            try:
                py_compile.compile(str(path), cfile=str(Path(directory) / f"{index}.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                print(exc, file=sys.stderr)
                return 1
    return 0


def pre_commit(root: Path) -> int:
    checks = (
        ("git diff --cached --check", ["git", "diff", "--cached", "--check"]),
        ("staged Python syntax", None),
        ("generated/runtime files", None),
        (
            "meta integrity",
            [sys.executable, "-m", "tools.atlas_meta_integrity", "--root", str(root), "--base-ref", "HEAD"],
        ),
    )
    for label, command in checks:
        print(f"[pre-commit] {label}")
        if label == "staged Python syntax":
            code = check_staged_syntax(root)
        elif label == "generated/runtime files":
            paths = git_paths(root, staged=True)
            findings = find_forbidden(paths) + find_sensitive_content(root, paths)
            for finding in findings:
                print(f"forbidden: {finding['path']} ({finding['reason']})", file=sys.stderr)
            code = 1 if findings else 0
        else:
            code = run(command or [], root)
        if code:
            print(f"[pre-commit] BLOCKED: {label}", file=sys.stderr)
            return code
    print("[pre-commit] PASS")
    return 0


def pre_push(root: Path) -> int:
    upstream = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    base_ref = upstream.stdout.strip() if upstream.returncode == 0 else "HEAD^"
    print(f"[pre-push] Atlas Integrity FAST (base={base_ref})")
    return run(
        [sys.executable, "-X", "faulthandler", "-m", "tools.atlas_integrity", "fast", "--base-ref", base_ref],
        root,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dofus Atlas repository Git hooks.")
    parser.add_argument("hook", choices=("pre-commit", "pre-push"))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    return pre_commit(root) if args.hook == "pre-commit" else pre_push(root)


if __name__ == "__main__":
    raise SystemExit(main())
