from __future__ import annotations

"""Choose a quick, proven minimum for routine diffs; never grant certification.

HIGH/CRITICAL/unknown/deleted/broad changes retain the canonical FULL job.
The independent PR Doctor FAST gate stays mandatory and unchanged.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from tools import ai_context
from tools.atlas_integrity import classify_risk


ROOT = Path(__file__).resolve().parents[1]
MAX_ROUTINE_CHANGED_FILES = 12
MAX_ROUTINE_MODULES = 12
KNOWN_COUPLED_MODULES = {
    "app/modules/encyclopedia/services/guide_path_profiles.py": (
        "tests.test_guide_prerequisite_lookup",
    ),
    "app/modules/encyclopedia/services/guide_catalog_builder.py": (
        "tests.test_guide_prerequisite_lookup",
    ),
    "tools/ci_scope_gate.py": ("tests.test_ci_scope_gate",),
    "tools/ci_dev_tests.py": ("tests.test_ci_dev_tests",),
    "tools/atlas_doctor_lib/ci_history.py": ("tests.test_ci_history",),
}
class ScopeError(ValueError):
    pass


def _path_has_direct_test_coverage(root: Path, path: str) -> bool:
    """Require evidence for every changed file, not merely its broad domain.

    DOMAIN_TEST_MODULES are useful regression smoke tests but don't prove
    that an unrelated source file has a direct test. Generated top-level AI
    index metadata is checked separately by the mandatory integrity gates.
    """
    if path == ".ai/context_index.json":
        return True
    selected = set(ai_context.recommended_tests(root, [path]))
    if path.startswith("tests/test_") and path.endswith(".py"):
        exact = ".".join(Path(path).with_suffix("").parts)
        return exact in selected and (root / path).is_file()
    if path.endswith(".py"):
        name = "tests.test_" + Path(path).stem
        if name in selected:
            return True
    return bool(set(KNOWN_COUPLED_MODULES.get(path, ())) & selected)


def classify_diff(root: Path, paths: Iterable[str], *, before_sha: str = "",
                  deletion_paths: Iterable[str] = (), head: str = "") -> dict[str, object]:
    changed = sorted({ai_context.normalize_path(p) for p in paths})
    deleted = sorted({ai_context.normalize_path(p) for p in deletion_paths})
    reasons: list[str] = []
    if not changed:
        reasons.append("EMPTY_DIFF")
    if not before_sha or set(before_sha) == {"0"}:
        reasons.append("NO_COMPARABLE_BASE")
    if len(changed) > MAX_ROUTINE_CHANGED_FILES:
        reasons.append("BROAD_CHANGE")
    if deleted:
        reasons.append("REMOVED_OR_RENAMED_FILES")
    if any(not p or p.startswith("/") or p.startswith("../") or "/../" in p for p in changed):
        reasons.append("INVALID_PATH")

    risks = classify_risk(changed)
    if risks["risk"] in {"HIGH", "CRITICAL"}:
        reasons.append(f"RISK_{risks['risk']}")
    unclassified = [p for p in changed if ai_context.classify_path(p) == "repository"]
    if unclassified:
        reasons.append("UNCLASSIFIED_PATHS")
    # Domain-level smoke tests are not sufficient to approve a mixed diff.
    # Every file must have an exact/co-located or explicitly coupled test,
    # except the generated index checked by the unchanged integrity gates.
    uncovered = [p for p in changed if not _path_has_direct_test_coverage(root, p)]
    if uncovered:
        reasons.append("INSUFFICIENT_PATH_COVERAGE")

    recommended = list(ai_context.recommended_tests(root, changed))
    for path in changed:
        for module in KNOWN_COUPLED_MODULES.get(path, ()):
            if (root / Path(*module.split(".")).with_suffix(".py")).is_file():
                recommended.append(module)
    modules = list(dict.fromkeys(recommended))
    if not modules or len(modules) > MAX_ROUTINE_MODULES:
        reasons.append("UNCERTAIN_TEST_COVERAGE")

    # Always keep the full suite available; a single critical path is enough
    # to request it. This gate never treats a targeted run as FULL certification.
    mode = "FULL_REQUIRED" if reasons else "TARGETED"
    return {
        "schema_version": 1,
        "status": mode,
        "risk": risks["risk"],
        "head": head,
        "base": before_sha,
        "changed_paths": changed,
        "deleted_paths": deleted,
        "unclassified_paths": unclassified,
        "uncovered_paths": uncovered,
        "modules": modules if mode == "TARGETED" else [],
        "full_required": mode == "FULL_REQUIRED",
        "full_suite_waived": False,
        "certified": False,
        "reasons": reasons,
        "note": "TARGETED is a routine feedback mode, NEVER proof of certification. "
                "Doctor FAST on PR and manual FULL remain unchanged.",
    }


def changed_paths(root: Path, before_sha: str) -> tuple[list[str], list[str]]:
    if not before_sha or set(before_sha) == {"0"}:
        return [], []
    base = subprocess.run(
        ["git", "cat-file", "-e", f"{before_sha}^{{commit}}"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if base.returncode:
        return [], []
    result = subprocess.run(
        ["git", "diff", "--name-status", "--find-renames", "-z", f"{before_sha}...HEAD"],
        cwd=root, capture_output=True, check=False,
    )
    if result.returncode:
        raise ScopeError("Git diff failed; must not assume targeted coverage")
    tokens = result.stdout.decode("utf-8", errors="replace").split("\0")
    paths: set[str] = set()
    deletions: set[str] = set()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token:
            break
        # With -z, Git separates status and paths by NUL (not a tab).
        # Renames and copies carry two paths: old, new.
        status = token
        if status[0] not in "ACDMRTUXB" or i + 1 >= len(tokens):
            raise ScopeError("Git name-status result cannot be parsed safely")
        path = tokens[i + 1]
        if not path:
            raise ScopeError("Invalid Git path status")
        if status.startswith(("R", "C")):
            if i + 2 >= len(tokens) or not tokens[i + 2]:
                raise ScopeError("Incomplete Git rename/copy record")
            paths.add(tokens[i + 2])
            if status.startswith("R"):
                deletions.add(path)
            i += 3
        else:
            paths.add(path)
            if status.startswith(("D", "T", "U")):
                deletions.add(path)
            i += 2
    return sorted(paths), sorted(deletions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--output", type=Path, help="Optional GitHub Actions outputs path")
    parser.add_argument("--run", action="store_true", help="Run routine selected modules, never FULL")
    options = parser.parse_args(argv)
    try:
        root = ROOT.resolve()
        paths, deleted = changed_paths(root, options.base_ref)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              check=True, capture_output=True, text=True).stdout.strip()
        data = classify_diff(root, paths, before_sha=options.base_ref,
                             deletion_paths=deleted, head=head)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if options.output is not None:
            with options.output.open("a", encoding="utf-8") as f:
                f.write(f"full_required={str(data['full_required']).lower()}\n")
                f.write(f"scope_status={data['status']}\n")
        if options.run and data["status"] == "TARGETED":
            result = subprocess.run(
                [sys.executable, "-X", "faulthandler", "-m", "unittest", "-v",
                 *data["modules"]],
                cwd=root, check=False, timeout=600,
            )
            return result.returncode
        return 0
    except (OSError, subprocess.CalledProcessError, ScopeError) as exc:
        print(f"Atlas CI scope failure, FULL required: {exc}", file=sys.stderr)
        if options.output is not None:
            with options.output.open("a", encoding="utf-8") as f:
                f.write("full_required=true\nscope_status=FULL_REQUIRED\n")
        return 0  # fail closed to FULL; do not skip it for a planner failure


if __name__ == "__main__":
    raise SystemExit(main())
