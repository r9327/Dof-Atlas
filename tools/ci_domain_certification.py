from __future__ import annotations

"""Exact-SHA, fail-closed owner/domain routing for modular PR certification.

This planner is NOT a FULL/Phase/release certificate. Unknown ownership must
block an automatic scoped certificate; it must never silently omit tests.
The baseline contract comes from the PR base, never from this PR's own plan.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
DOMAINS = ("ci", "craft", "quests", "guides", "ui", "startup", "identity", "data")
INFRA_PATHS = frozenset({
    ".ai/context_index.json", "README.md",
    "DOCTOR_ADAPTIVE_CERTIFICATION.md", "PHASE_CERTIFICATION.md",
    ".gitattributes", ".gitignore",
})
CI_FILES = frozenset({
    "tools/atlas_integrity.py", "tools/atlas_integrity_policy.json",
    "tools/atlas_meta_integrity.py", "tools/phase_certification_verdict.py",
    "tools/phase_adaptive_gate.py", "tools/ci_required_certification.py",
    "tools/ci_scope_gate.py", "tools/ci_pr_audit.py",
    "tools/ci_domain_certification.py", "tools/doctor_certification.py",
    "tools/atlas_full_suite_proof.py", "tools/ci_verified_pr_full.py",
    "tools/ci_main_phase_evidence.py", "tools/ci_guide_full_evidence.py",
    "tools/doctor_policy_authority.py", "tools/ci_guide_full_evidence.py",
})
CRAFT_PATHS = frozenset({
    "app/local_data_cache.py", "app/craft_preload.py",
    "app/pages/craft_page.py", "tools/benchmark_phase8_memory.py",
    "tools/phase8_memory_tolerance.py",
})


def owners_for(path: str) -> frozenset[str]:
    """Static, independently checked closed-world owners (not PR title hints)."""
    if (not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or ".." in path.split("/")):
        raise ValueError("Unsafe changed path")
    if path in INFRA_PATHS or (path.startswith("docs/") and path.endswith(".md")):
        return frozenset()
    if path.startswith(".github/workflows/") or path.startswith(".github/rulesets/"):
        return frozenset({"ci"})
    if path in CI_FILES or path.startswith("tools/atlas_doctor_lib/"):
        return frozenset({"ci"})
    if path in CRAFT_PATHS or path.startswith("app/pages/craft_"):
        return frozenset({"craft"})
    if path.startswith("app/modules/encyclopedia/services/guide_"):
        return frozenset({"guides"})
    if path.startswith("app/modules/encyclopedia/providers/") or path.startswith("app/quest_"):
        return frozenset({"quests"})
    if path.startswith("app/ui/") or path.startswith("app/pages/"):
        return frozenset({"ui"})
    if path.startswith("local_dofus_data/") or path.startswith("data/"):
        return frozenset({"data", "craft", "quests"})
    if path.startswith("app/core/") and any(
        token in path for token in ("identity", "character", "json_store", "progress")
    ):
        return frozenset({"identity", "guides"})
    if path in {"main.py", "launch.py", "sitecustomize.py", "requirements-pyside.txt"}:
        return frozenset({"startup", "ui", "craft", "quests", "guides"})
    if path.startswith("tests/test_") and path.endswith(".py"):
        leaf = path[11:-3]
        if leaf.startswith(("ci_", "doctor_", "phase_", "atlas_integrity", "atlas_meta",
                            "meta_integrity", "public_pr_", "security_hardening",
                            "repository_git", "generated_file")):
            return frozenset({"ci"})
        if any(token in leaf for token in ("craft", "memory", "preload")):
            return frozenset({"craft"})
        if any(token in leaf for token in ("guide", "progress", "achievement")):
            return frozenset({"guides"})
        if any(token in leaf for token in ("quest", "catalog")):
            return frozenset({"quests"})
        if any(token in leaf for token in ("startup", "launcher")):
            return frozenset({"startup"})
        if any(token in leaf for token in ("character", "identity")):
            return frozenset({"identity"})
        if any(token in leaf for token in ("qt_", "ui_", "pyside", "window")):
            return frozenset({"ui"})
        # A new test must not be silently considered irrelevant.
        return frozenset()
    return frozenset()


def _normal_path(path: str) -> bool:
    return (isinstance(path, str) and bool(path) and not path.startswith("/")
            and "\\" not in path and ".." not in path.split("/"))


def plan_domains(*, base_sha: str, candidate_sha: str, paths: list[str],
                 deleted: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    if not SHA.fullmatch(base_sha) or not SHA.fullmatch(candidate_sha):
        raise ValueError("Exact base/head SHAs required")
    if (not isinstance(paths, list) or not paths or len(paths) != len(set(paths))
            or any(not _normal_path(p) for p in paths)):
        raise ValueError("Incomplete or unsafe exact PR diff")
    if (not isinstance(deleted, (tuple, list)) or any(not _normal_path(p) for p in deleted)
            or any(p not in paths for p in deleted)):
        raise ValueError("Deleted paths must be an exact diff subset")
    domain_paths = {d: [] for d in DOMAINS}
    unknown = []
    for path in paths:
        owners = owners_for(path)
        for d in owners:
            domain_paths[d].append(path)
        if not owners and path not in INFRA_PATHS and not (
            path.startswith("docs/") and path.endswith(".md")
        ):
            unknown.append(path)
    groups = [d for d in DOMAINS if domain_paths[d]]
    # Removal/type-change provenance cannot be guessed from the candidate.
    # A removed policy, source or test blocks, never downgrades to a subset.
    problems = []
    if deleted:
        problems.append("REMOVAL_OR_RENAME_REQUIRES_REVIEW")
    if unknown:
        problems.append("UNKNOWN_OWNER_BLOCKS_MODULAR_CERTIFICATE")
    if not groups and not problems:
        groups.append("metadata")
    return {
        "schema_version": 1, "kind": "atlas_independent_domain_plan",
        "base_sha": base_sha, "candidate_sha": candidate_sha,
        "status": "BLOCKED" if problems else "READY_TO_EXECUTE",
        "domains": groups, "domain_paths": domain_paths,
        "unknown_paths": sorted(unknown), "deleted_paths": sorted(set(deleted)),
        "reasons": problems, "tests_executed": False,
        "phase_certified": False, "merge_authorized": False,
        "full_suite_executed": False,
        "note": "All selected domain contracts and independent specialist jobs must PASS on exact SHA. This plan is not a certificate.",
    }


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True,
                          text=True, encoding="utf-8", check=True, timeout=45)
    return done.stdout


def exact_git_diff(base_sha: str, candidate_sha: str) -> tuple[list[str], list[str]]:
    """Compare the PR merge-base, never unrelated post-divergence main commits."""
    result = _git("diff", "--name-status", "-z", "--no-renames",
                  f"{base_sha}...{candidate_sha}")
    fields = result.split("\0")
    if not fields or fields[-1] != "" or (len(fields) - 1) % 2:
        raise ValueError("Malformed Git status diff")
    changed, deleted = [], []
    for i in range(0, len(fields) - 1, 2):
        flag, path = fields[i:i + 2]
        if flag not in {"M", "A", "D", "T"} or not _normal_path(path):
            raise ValueError("Unexpected file status or path")
        changed.append(path)
        if flag in {"D", "T"}:
            deleted.append(path)
    return changed, deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    head = _git("rev-parse", "HEAD").strip()
    if head != args.candidate_sha:
        raise SystemExit("Candidate SHA does not match exact checkout")
    paths, deleted = exact_git_diff(args.base_sha, head)
    outcome = plan_domains(base_sha=args.base_sha, candidate_sha=head,
                           paths=paths, deleted=deleted)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcome, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print("Independent domains:", ", ".join(outcome["domains"]), "status:", outcome["status"])
    return 0 if outcome["status"] == "READY_TO_EXECUTE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
