"""Run repeatable, local PR #254 pre-CI checks without launching GitHub CI.

Usage from repository root:
    py -3.13 -m tools.assets.unity_pre_ci --report artifacts/unity-pre-ci.json
    py -3.13 -m tools.assets.unity_pre_ci --qt --assets --report artifacts/unity-pre-ci-full.json

The first mode needs only Python and git. The second also needs the pinned
PySide6 runtime and local reference assets. Neither certifies Windows EXEs,
asset licences, DPI on physical monitors or the final CI SHA.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SOURCE_FILES = (
    "app/ui/unity_skin.py",
    "app/ui/theme.py",
    "app/modules/encyclopedia/views/encyclopedia_page.py",
    "app/modules/encyclopedia/views/guide_catalog_view.py",
    "app/modules/encyclopedia/views/guide_featured_home.py",
    "app/modules/encyclopedia/views/guides_view.py",
    "scripts/windows/package_release.py",
    "tools/assets/inspect_unity_assets.py",
    "tools/assets/unity_local_cycle_probe.py",
    "tests/test_guide_library_home.py",
    "tests/test_unity_skin.py",
    "tests/test_unity_assets_inventory.py",
    "tests/test_distribution_package.py",
    "tests/test_distribution_export.py",
    "tests/test_unity_pre_ci_runner.py",
)
STDLIB_TESTS = (
    "tests/test_unity_assets_inventory.py",
    "tests/test_distribution_package.py",
    "tests/test_distribution_export.py",
    "tests/test_unity_pre_ci_runner.py",
)
QT_TESTS = (
    "tests/test_unity_skin.py",
    "tests/test_guide_library_home.py",
    "tests/test_guide_home_two_columns.py",
)
# Running a test script via runpy avoids importing tests/__init__.py, which
# eagerly constructs a QApplication and requires PySide6 even for pure tests.
RUN_TEST = (
    "import runpy,sys; "
    "path=sys.argv[1];sys.argv=[path]; "
    "runpy.run_path(path,run_name='__main__')"
)


def _run(command: list[str], root: Path, *, qt: bool = False, timeout: int = 180) -> dict:
    environment = dict(os.environ)
    if qt:
        environment["QT_QPA_PLATFORM"] = "offscreen"
    try:
        done = subprocess.run(
            command, cwd=root, env=environment, text=True,
            encoding="utf-8", errors="replace", capture_output=True,
            timeout=timeout, check=False,
        )
        return {
            "status": "PASS" if done.returncode == 0 else "FAIL",
            "exit_code": done.returncode,
            "stdout_tail": done.stdout[-3000:],
            "stderr_tail": done.stderr[-3000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAIL", "error": str(exc)}


def examine(root: Path, *, qt: bool = False, assets: bool = False) -> dict:
    root = root.resolve()
    report: dict = {
        "status": "FAIL", "pre_ci_only": True, "github_ci_launched": False,
        "repo_root": str(root), "python": sys.version.split()[0],
        "qt_requested": qt, "assets_requested": assets,
        "checks": {}, "external_blockers": [
            "actual Windows display DPI and installed EXE not certified",
            "rights to redistributing DOFUS assets not established",
            "original Unity wallpaper not yet visually cleaned/approved",
            "final SHA-specific CI deliberately not launched",
        ],
    }
    if not root.is_dir():
        report["error"] = "repository root does not exist"
        return report
    revision = _run(["git", "rev-parse", "HEAD"], root)
    head = revision.get("stdout_tail", "").strip()
    valid_head = (revision["status"] == "PASS" and len(head) == 40
                  and all(char in "0123456789abcdef" for char in head))
    report["checks"]["git_revision"] = {
        "status": "PASS" if valid_head else "FAIL",
        "head_sha": head if valid_head else None,
    }
    if valid_head:
        report["head_sha"] = head
    # Only tracked changes matter; logs and screenshot evidence may be untracked.
    worktree = _run(["git", "diff", "--quiet"], root)
    index = _run(["git", "diff", "--cached", "--quiet"], root)
    report["checks"]["tracked_worktree_clean"] = {
        "status": ("PASS" if worktree["status"] == "PASS"
                   and index["status"] == "PASS" else "FAIL")
    }
    parse_failures = []
    for name in SOURCE_FILES:
        path = root / name
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=name)
        except (OSError, SyntaxError, UnicodeError) as exc:
            parse_failures.append(f"{name}: {exc}")
    report["checks"]["python_syntax"] = {
        "status": "FAIL" if parse_failures else "PASS",
        "files": len(SOURCE_FILES), "errors": parse_failures,
    }
    for name in STDLIB_TESTS:
        report["checks"][name] = _run(
            [sys.executable, "-c", RUN_TEST, name], root
        )
    if qt:
        if importlib.util.find_spec("PySide6") is None:
            report["checks"]["qt_runtime"] = {
                "status": "FAIL", "error": "PySide6 missing",
            }
        else:
            for name in QT_TESTS:
                report["checks"][name] = _run(
                    [sys.executable, "-c", RUN_TEST, name], root, qt=True,
                )
    else:
        report["checks"]["qt_tests"] = {"status": "NOT_RUN"}
    if assets:
        result = _run(
            [sys.executable, "-m", "tools.assets.inspect_unity_assets", "--json"],
            root,
        )
        report["checks"]["asset_integrity"] = result
    else:
        report["checks"]["asset_integrity"] = {"status": "NOT_RUN"}
    report["status"] = (
        "PASS" if all(
            item["status"] in ("PASS", "NOT_RUN")
            for item in report["checks"].values()
        ) else "FAIL"
    )
    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--qt", action="store_true", help="also execute local offscreen Qt tests")
    parser.add_argument("--assets", action="store_true", help="also audit local unlicensed reference assets")
    args = parser.parse_args()
    report = examine(args.root, qt=args.qt, assets=args.assets)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name, result in report["checks"].items():
        print(f"{result['status']:>7}  {name}")
    print(f"{report['status']} local pre-CI; report: {args.report}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
