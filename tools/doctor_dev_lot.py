from __future__ import annotations

"""Optional exact-SHA development-lot tests, never a PR/Phase certification.

The trusted-main ci_scope_gate and Phase Certification still decide whether the
*entire* pull request needs FULL. This module only tests a bounded ancestor
delta on the immutable PR checkout, without credentials or arbitrary commands.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools import ai_context, ci_scope_gate

ROOT = Path(__file__).resolve().parents[1]
MAX_COMMITS = 20
MAX_FILES = 16
MAX_MODULES = 12

# A direct owner is mandatory for executable files: domain smokes alone do not
# prove a changed source. Extend this map only with existing, reviewed tests.
DIRECT_OWNERS = {
    # Shared name normalization has dedicated, Qt-free regression contracts.
    # This development owner does not waive the global PR FULL requirement.
    "app/core/text.py": ("tests.test_core_text",),
    # The canonical lease, stop and generation tests exercise this owner.
    # A domain-level Organizer smoke alone is not an adequate substitute.
    "app/core/macro_lock.py": (
        "tests.test_organizer_macro_generation",
    ),
    # Both modules are exercised by real mouse-hook + collision/Stop tests;
    # test-module existence and actual execution are still mandatory.
    "app/input/input_state.py": (
        "tests.test_organizer_sendinput",
        "tests.test_organizer_mirror_ui",
    ),
    "app/input/mouse_hooks.py": (
        "tests.test_organizer_sendinput",
        "tests.test_organizer_mirror_ui",
    ),
    "app/macros/mirror_input.py": (
        "tests.test_organizer_mirror_ui",
    ),
    # Existing Qt and pure-geometry tests directly exercise both wheel
    # owners. Do not require unrelated FULL smoke to approve a local lot.
    "app/pages/organizer/radial_overlay.py": (
        "tests.test_organizer_radial_overlay",
    ),
    "app/pages/organizer/radial_selection.py": (
        "tests.test_organizer_radial_overlay",
    ),
    "app/macros/switch_click.py": (
        "tests.test_organizer_macro_reliability",
        "tests.test_organizer_mirror_ui",
    ),
    # Only this reviewed development helper is allowed as a tool-side
    # executable owner. The global PR FULL requirement is unaffected.
    "tools/organizer_mirror_log_report.py": (
        "tests.test_organizer_mirror_log_report",
    ),
    # Reviewed developer-only OSS owners: narrow exact paths, never a
    # tools/ wildcard. Missing modules still block or require review.
    "tools/atlas_doctor_lib/oss_router.py": (
        "tests.test_doctor_oss_routing",
        "tests.test_doctor_oss_live",
        "tests.test_doctor_oss_intelligence",
    ),
    "tools/atlas_doctor_lib/oss_intelligence.py": (
        "tests.test_doctor_oss_intelligence",
    ),
    "tools/atlas_json_benchmark.py": (
        "tests.test_atlas_json_benchmark",
    ),
    "tools/doctor_oss_wheels.py": (
        "tests.test_doctor_oss_wheels",
    ),
}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, timeout=30,
    )
    if result.returncode:
        raise ValueError("Git revision / ancestry validation failed")
    return result.stdout.strip()


def _test_path(module: str) -> Path:
    return Path(*module.split(".")).with_suffix(".py")


def plan_lot(root: Path, *, lot_base: str, pr_base: str, head: str) -> dict:
    root = root.resolve()
    sha = lambda value: (len(value) == 40 and
                         all(c in "0123456789abcdef" for c in value))
    if not all(sha(v) for v in (lot_base, pr_base, head)):
        raise ValueError("All revisions must be exact lowercase 40-hex SHAs")
    if _git(root, "rev-parse", "HEAD") != head:
        raise ValueError("Candidate checkout is not the requested HEAD")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked checkout is dirty")
    for ref in (lot_base, pr_base):
        if _git(root, "rev-parse", "--verify", ref + "^{commit}") != ref:
            raise ValueError("Non-commit or non-canonical revision")
    if lot_base == head:
        raise ValueError("Empty development lot")
    _git(root, "merge-base", "--is-ancestor", lot_base, head)
    commits = int(_git(root, "rev-list", "--count", lot_base + ".." + head))
    if not 1 <= commits <= MAX_COMMITS:
        raise ValueError("Development lot exceeds 20 commits")
    changed, deleted = ci_scope_gate.changed_paths(root, lot_base)
    if not changed or len(changed) > MAX_FILES or deleted:
        raise ValueError("Empty, oversized, deleted or renamed development lot")

    # The global PR verdict is computed from its *actual* PR base, not the
    # convenient lot base; never use a small lot to downgrade FULL.
    global_paths, global_deleted = ci_scope_gate.changed_paths(root, pr_base)
    global_scope = ci_scope_gate.classify_diff(
        root, global_paths, before_sha=pr_base,
        deletion_paths=global_deleted, head=head,
    )
    owned: set[str] = set()
    uncovered: list[str] = []
    unsupported: list[str] = []
    for path in changed:
        if path == ".ai/context_index.json" or (
                path.startswith("docs/") and path.endswith(".md")):
            continue
        if (path in ci_scope_gate.FULL_ONLY_PATHS
                or not (
                    path.startswith("app/") or path.startswith("tests/")
                    or (path.startswith("tools/") and path in DIRECT_OWNERS)
                )
                or not path.endswith(".py")):
            unsupported.append(path)
            continue
        if path.startswith("tests/test_"):
            candidates = (".".join(Path(path).with_suffix("").parts),)
        else:
            candidates = DIRECT_OWNERS.get(path) or tuple(
                name for name in ai_context.recommended_tests(root, [path])
                if name == "tests.test_" + Path(path).stem
            )
            candidates += ci_scope_gate.KNOWN_COUPLED_MODULES.get(path, ())
        candidates = tuple(dict.fromkeys(candidates))
        valid = [name for name in candidates
                 if (root / _test_path(name)).is_file()
                 and not (root / _test_path(name)).is_symlink()]
        if not valid:
            uncovered.append(path)
        owned.update(valid)
    modules = sorted(owned)
    if len(modules) > MAX_MODULES:
        unsupported.append("TOO_MANY_TEST_MODULES")
    state = ("BLOCKED" if unsupported else
             "REVIEW" if uncovered or not modules else "READY")
    return {
        "schema_version": 1,
        "kind": "doctor-development-lot/v1",
        "status": state,
        "candidate_sha": head,
        "lot_base_sha": lot_base,
        "pr_base_sha": pr_base,
        "lot_commits": commits,
        "lot_changed_paths": changed,
        "test_modules": modules,
        "uncovered_paths": uncovered,
        "unsupported_paths": unsupported,
        "global_scope_status": global_scope["status"],
        "global_full_required": global_scope["full_required"],
        "global_scope_reasons": global_scope["reasons"],
        "full_suite_executed": False,
        "full_suite_waived": False,
        "phase_certified": False,
        "certified": False,
        "execution": {"status": "NOT_RUN", "exit_code": None},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT,
                        help="Immutable PR checkout; selector code may live in trusted main")
    parser.add_argument("--lot-base", required=True)
    parser.add_argument("--pr-base", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = plan_lot(args.repo_root, lot_base=args.lot_base,
                          pr_base=args.pr_base, head=args.expected_sha)
        if args.run and report["status"] in {"READY", "REVIEW"} and report["test_modules"]:
            try:
                code = ci_scope_gate._run_scoped_modules(args.repo_root.resolve(), report["test_modules"])
            except (OSError, subprocess.TimeoutExpired) as exc:
                report["execution"] = {"status": "BLOCKED", "reason": type(exc).__name__}
            else:
                report["execution"] = {
                    "status": "PASS" if code == 0 else "FAIL",
                    "exit_code": code,
                    "executed_modules": report["test_modules"],
                }
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report = {
            "schema_version": 1, "kind": "doctor-development-lot/v1",
            "status": "BLOCKED", "reason": str(exc),
            "candidate_sha": args.expected_sha,
            "full_suite_waived": False, "phase_certified": False,
            "certified": False, "execution": {"status": "NOT_RUN"},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if report["status"] == "BLOCKED" or report["execution"]["status"] == "BLOCKED":
        return 2
    if report["status"] == "REVIEW" or report["execution"]["status"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
