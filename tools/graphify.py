from __future__ import annotations

"""Canonical pinned Graphify command sequence; no installation or Git hooks."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from importlib import metadata
from pathlib import Path
from typing import Any

PINNED_VERSION = "0.9.72"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("graphify-out")
OUTPUT_FILES = ("graph.json", "GRAPH_REPORT.md", "graph.html")


def _tool_environment() -> tuple[str | None, str | None]:
    scripts = Path(sysconfig.get_path("scripts"))
    executable = scripts / ("graphify.exe" if os.name == "nt" else "graphify")
    try:
        version = metadata.version("graphifyy")
    except metadata.PackageNotFoundError:
        version = None
    current = (str(executable), version) if version and executable.is_file() else (None, None)
    if current[0] and version == PINNED_VERSION:
        return current
    uv = shutil.which("uv")
    if uv:
        result = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True, check=False, timeout=15)
        if result.returncode == 0:
            home = Path(result.stdout.strip()) / "graphifyy"
            binary = home / ("Scripts" if os.name == "nt" else "bin")
            python = binary / ("python.exe" if os.name == "nt" else "python")
            executable = binary / ("graphify.exe" if os.name == "nt" else "graphify")
            if python.is_file() and executable.is_file():
                result = subprocess.run(
                    [str(python), "-c", "from importlib.metadata import version; print(version('graphifyy'))"],
                    capture_output=True, text=True, check=False, timeout=15,
                )
                if result.returncode == 0:
                    return str(executable), result.stdout.strip()
    return current


def detect(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    try:
        executable, version = _tool_environment()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "UNAVAILABLE", "expected_version": PINNED_VERSION, "reason": str(exc)}
    configured = (root / ".graphifyignore").is_file()
    status = "MISSING" if not executable else ("PASS" if version == PINNED_VERSION else "WRONG_VERSION")
    if not configured:
        status = "INVALID_CONFIG"
    return {
        "schema_version": 1, "status": status, "available": bool(executable),
        "executable": executable, "version": version, "expected_version": PINNED_VERSION,
        "configuration": ".graphifyignore", "configuration_present": configured,
        "mode": "code-only / AST / no-label", "installs_hooks": False,
        "setup": "powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify.ps1",
    }


def install_graphify() -> dict[str, Any]:
    uv = shutil.which("uv")
    if not uv:
        return {"schema_version": 1, "status": "BLOCKED", "reason": "uv required; install with winget install astral-sh.uv"}
    try:
        result = subprocess.run(
            [uv, "tool", "install", "--force", f"graphifyy=={PINNED_VERSION}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=False, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"schema_version": 1, "status": "FAIL", "reason": str(exc)}
    return {"schema_version": 1, "status": "PASS" if result.returncode == 0 else "FAIL",
            "reason": (result.stderr or result.stdout)[-2000:]}


def commands(executable: str) -> list[list[str]]:
    return [
        [executable, "extract", ".", "--code-only"],
        [executable, "cluster-only", ".", "--no-label"],
        [executable, "export", "html", "--graph", "graphify-out/graph.json"],
    ]


def build_graph(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    tool = detect(root)
    if tool["status"] != "PASS":
        return {"schema_version": 1, "status": "BLOCKED", "tool": tool, "reason": "Pinned Graphify and .graphifyignore are required."}
    ignored = subprocess.run(["git", "check-ignore", "-q", "--", "graphify-out/graph.json"], cwd=root, check=False)
    tracked = subprocess.run(["git", "ls-files", "--", "graphify-out"], cwd=root, capture_output=True, text=True, check=False)
    if ignored.returncode != 0 or tracked.returncode != 0 or tracked.stdout.strip():
        return {"schema_version": 1, "status": "BLOCKED", "tool": tool, "reason": "Graphify output must be ignored and untracked."}
    for command in commands(tool["executable"]):
        try:
            result = subprocess.run(
                command, cwd=root, capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=False, timeout=1200,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"schema_version": 1, "status": "FAIL", "tool": tool, "command": command, "reason": str(exc)}
        if result.returncode:
            return {"schema_version": 1, "status": "FAIL", "tool": tool, "command": command,
                    "returncode": result.returncode, "reason": (result.stderr or result.stdout)[-4000:]}
    missing = [name for name in OUTPUT_FILES if not (root / OUTPUT / name).is_file()]
    return {"schema_version": 1, "status": "FAIL" if missing else "PASS", "tool": tool,
            "missing_outputs": missing, "html": str(root / OUTPUT / "graph.html")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "build", "install"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = install_graphify() if args.command == "install" else (build_graph() if args.command == "build" else detect())
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
