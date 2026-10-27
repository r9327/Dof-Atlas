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
# Historical critical groups are the independent BASELINE minimum. A domain
# owns every shared consumer test, not just modules matching filename globs.
# The candidate cannot remove tests from these baseline groups.
BASELINE_GROUPS = {
    "ci": ("ARCHITECTURE", "CI_INTEGRITY"),
    "craft": ("ASYNC_LIFECYCLE", "RESOURCE_BUDGETS"),
    "quests": ("PERSISTENCE", "LAZY_LOADING", "GOLDEN_FLOWS"),
    "guides": ("PERSISTENCE", "GOLDEN_FLOWS"),
    "ui": ("ASYNC_LIFECYCLE", "GOLDEN_FLOWS"),
    "startup": ("STARTUP", "LAZY_LOADING", "RESOURCE_BUDGETS"),
    "identity": ("IDENTITY", "PERSISTENCE"),
    "data": ("PERSISTENCE", "GOLDEN_FLOWS"),
}

# Explicitly reviewed AI entrypoints and certification policy documentation
# are CI-owned instructions, not unknown application modules or generic
# metadata. This ownership does NOT waive the independent root-of-trust/FULL
# decision for PHASE_CERTIFICATION.md or any executable policy change.
REVIEWED_CI_INSTRUCTION_PATHS = frozenset({
    "AGENTS.md", "AI_ENTRYPOINT.md", "CLAUDE.md",
    ".github/copilot-instructions.md", ".cursor/rules/atlas-doctor.mdc",
    "app/AGENTS.md", "data/AGENTS.md", "tests/AGENTS.md", "tools/AGENTS.md",
    "tools/skills/dofus-atlas-tools/SKILL.md",
    "PHASE_CERTIFICATION.md", "DOCTOR_ADAPTIVE_CERTIFICATION.md",
})
INFRA_PATHS = frozenset({
    ".ai/context_index.json", "README.md",
    ".gitattributes", ".gitignore",
})
CI_FILES = frozenset({
    "tools/atlas_integrity.py", "tools/atlas_integrity_policy.json",
    "tools/atlas_meta_integrity.py", "tools/phase_certification_verdict.py",
    "tools/phase_adaptive_gate.py", "tools/ci_required_certification.py",
    "tools/ci_smart_host_proof.py",
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
    if path in REVIEWED_CI_INSTRUCTION_PATHS:
        return frozenset({"ci"})
    if path in INFRA_PATHS or (path.startswith("docs/") and path.endswith(".md")):
        return frozenset()
    if path.startswith(".github/workflows/") or path.startswith(".github/rulesets/"):
        return frozenset({"ci"})
    if path in CI_FILES or path.startswith("tools/atlas_doctor_lib/"):
        return frozenset({"ci"})
    # Shared data APIs are consumed by Craft and Quest/Guide loaders; a file
    # label alone cannot prove the change is Craft-only. Until a separately
    # authenticated symbol/call-graph closure exists, retain all consumers.
    # The standalone updater and Qt preload are shared startup/UI contracts.
    # Keep this exact-path allowlist: unknown distribution modules stay blocked.
    # Reviewed smart-update surface: explicit paths only. Files are shared by
    # launcher, release/asset integrity and runtime data. Never add a wildcard:
    # any future distribution helper must acquire its own ownership review.
    if path in {
        "app/distribution/install.py",
        "app/distribution/release_client.py",
        "app/distribution/disk_space.py",
        "app/distribution/file_clone.py",
        "app/distribution/cleanup.py",
        "app/distribution/install_location.py",
        "tests/test_distribution_disk_space.py",
        "tests/test_distribution_smart_update.py",
        "tests/test_distribution_packaging.py",
    }:
        return frozenset({"ci", "startup", "data"})
    if path in {"app/distribution/launcher.py", "app/distribution/launcher_ui.py"}:
        return frozenset({"startup", "ui"})
    if path == "app/ui/preload_popup.py":
        return frozenset({"startup", "ui"})
    if path == "app/local_data_cache.py":
        return frozenset({"craft", "quests", "guides", "data"})
    if path in CRAFT_PATHS or path.startswith("app/pages/craft_"):
        return frozenset({"craft"})
    if path.startswith("app/modules/encyclopedia/services/guide_"):
        return frozenset({"guides"})
    if path in {
        "app/modules/encyclopedia/views/shared_manual_guide_view.py",
        "app/modules/encyclopedia/views/guides_view.py",
        "app/modules/encyclopedia/views/guide_ultime_manual_view.py",
        "app/modules/encyclopedia/views/guide_ultime_universal_view.py",
    }:
        # All four concrete guide readers have both Guide logic and Qt clients.
        # Unknown view modules remain BLOCKED; no wildcard or coverage reduction.
        return frozenset({"guides", "ui"})
    if path in {
        "app/modules/encyclopedia/views/encyclopedia_page.py",
        "app/modules/encyclopedia/views/guide_catalog_view.py",
        "app/modules/encyclopedia/views/guide_featured_home.py",
        "app/modules/encyclopedia/views/guide_library_sources.py",
        "app/modules/encyclopedia/widgets/guide_card.py",
    }:
        # Catalog widgets and the Encyclopedia shell have Guide and UI consumers.
        return frozenset({"guides", "ui"})
    if path.startswith("app/assets/themes/dofus_unity/"):
        # Owned *only* as UI/data inputs, not approved for redistribution.
        if Path(path).suffix.lower() in {".png", ".ttf", ".md"}:
            return frozenset({"ui", "data"})
        return frozenset()
    if path.startswith("docs/design/dofus-unity/"):
        # Narrow source-asset inventory; unknown executable formats stay blocked.
        if Path(path).suffix.lower() in {".zip", ".md", ".json"}:
            return frozenset({"ui", "data"})
        return frozenset()
    if path == "docs/plans/guides-2026-10-24/06b-dofus-unity-asset-manifest.csv":
        return frozenset({"ui", "data"})
    if path == "tools/assets/import_dofus_unity_ui.ps1":
        return frozenset({"ci", "ui"})
    # PR #254's local proof tools cross these real consumers. Enumerate
    # exact paths rather than permitting an unreviewed tools/assets wildcard.
    if path in {
        "tools/assets/clean_unity_wallpaper.py",
        "tools/assets/inspect_unity_assets.py",
    }:
        return frozenset({"ci", "ui", "data"})
    if path == "tools/assets/unity_local_cycle_probe.py":
        return frozenset({"ci", "guides", "ui"})
    if path == "tools/assets/unity_pre_ci.py":
        return frozenset({"ci", "guides", "ui", "startup", "data"})
    if path == "scripts/windows/package_release.py":
        return frozenset({"ci", "ui", "startup", "data"})
    if path in {"tests/test_distribution_package.py", "tests/test_unity_pre_ci_runner.py"}:
        return frozenset({"ci", "startup"})
    if path == "tests/test_unity_assets_inventory.py":
        return frozenset({"ui", "data"})
    if path == "tests/test_unity_cycle_metrics.py":
        return frozenset({"guides", "ui"})
    if path == "tests/test_unity_wallpaper_cleaner.py":
        return frozenset({"ui", "data"})
    if path == "tests/test_unity_skin.py":
        return frozenset({"ui"})
    if path == "tests/test_distribution_export.py":
        # Runtime export policy is both CI packaging integrity and startup.
        return frozenset({"ci", "startup"})
    if path.startswith("app/modules/encyclopedia/providers/") or path.startswith("app/quest_"):
        return frozenset({"quests"})
    if path == "app/pages/_quests_page_impl.py":
        # Shared Quest HTML templates and their QWidget consumers.
        return frozenset({"quests", "ui"})
    if path.startswith("app/pages/quest_"):
        return frozenset({"ui", "quests"})
    if path.startswith("app/pages/guide_") or path.startswith("app/pages/achievement_"):
        return frozenset({"ui", "guides"})
    if path.startswith("app/ui/") or path.startswith("app/pages/"):
        return frozenset({"ui"})
    if path.startswith("local_dofus_data/") or path.startswith("data/"):
        return frozenset({"data", "craft", "quests", "guides"})
    if path.startswith("app/core/") and any(
        token in path for token in ("identity", "character", "json_store", "progress")
    ):
        return frozenset({"identity", "guides"})
    if path in {"main.py", "launch.py", "sitecustomize.py", "requirements-pyside.txt"}:
        return frozenset({"startup", "ui", "craft", "quests", "guides", "identity", "data"})
    if path.startswith("tests/test_") and path.endswith(".py"):
        leaf = path[11:-3]
        if leaf == "lanyel_shared_manual_ui":
            return frozenset({"guides", "ui"})
        if leaf.startswith(("ci_", "doctor_", "phase_", "atlas_integrity", "atlas_meta",
                            "meta_integrity", "main_phase_evidence", "public_pr_",
                            "security_hardening", "repository_git", "generated_file")):
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
        "changed_paths": paths,
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



def _module_sources(root: Path, domain: str) -> list[str]:
    """Existing exact test modules only; never infer a PASS from an absent file."""
    tests = root / "tests"
    if domain == "ci":
        from tools.atlas_doctor_lib.ci_tooling_scope import TESTS
        prefixes = [f"test_{name}.py" for name in TESTS]
        prefixes += ["test_ci_domain_certification.py"]
        missing = [p for p in prefixes if not (tests / p).is_file()]
        if missing:
            raise ValueError("Missing mandatory CI test modules: " + ", ".join(missing))
        return ["tests." + p[:-3] for p in prefixes]
    if domain == "craft":
        patterns = ("test_craft*.py", "test_phase8_memory*.py",
                    "test_memory*.py", "test_phase8_preload*.py")
    elif domain == "quests":
        patterns = ("test_quest*.py", "test_encyclopedia_provider*.py",
                    "test_encyclopedia_on_demand*.py")
    elif domain == "guides":
        patterns = ("test_guide*.py", "test_progress*.py",
                    "test_achievement*.py")
    elif domain == "ui":
        patterns = ("test_doctor_ui_qt.py", "test_pyside*.py",
                    "test_qt*.py", "test_quest_visuals*.py")
    elif domain == "startup":
        patterns = ("test_startup*.py", "test_main_startup*.py",
                    "test_launcher*.py", "test_lazy*.py")
    elif domain == "identity":
        patterns = ("test_character*.py", "test_identity*.py",
                    "test_progress_interprocess*.py")
    elif domain == "data":
        patterns = ("test_local_data*.py", "test_data*.py",
                    "test_json*.py", "test_quest_catalog*.py")
    else:
        raise ValueError("Unrecognized certification domain: " + domain)
    found = {p for pattern in patterns for p in tests.glob(pattern) if p.is_file()}
    if not found:
        raise ValueError("No real tests discovered for mandatory " + domain)
    return ["tests." + p.stem for p in sorted(found)]


def execute_domain_tests(plan: dict[str, Any], *, root: Path, base_sha: str) -> dict[str, Any]:
    """Run every mapped test, all touched tests, and base-anchored CI contracts."""
    import hashlib
    import time
    import unittest
    from tools.atlas_full_suite_proof import ProofResult, ids

    head = _git("rev-parse", "HEAD").strip()
    if plan.get("status") != "READY_TO_EXECUTE" or plan.get("candidate_sha") != head:
        raise ValueError("No valid exact-SHA domain plan")
    if plan.get("base_sha") != base_sha or plan.get("deleted_paths") or plan.get("unknown_paths"):
        raise ValueError("Domain coverage incomplete or stale")
    domains = plan.get("domains")
    if not isinstance(domains, list) or not domains or len(domains) != len(set(domains)):
        raise ValueError("No closed-world domain inventory")
    # Baseline policy and baseline CI contract registry must remain an exact
    # lower bound even when the PR changes its own candidate routing code.
    import ast
    baseline_ci_registry = _git("show", f"{base_sha}:tools/atlas_doctor_lib/ci_tooling_scope.py")
    parsed = ast.parse(baseline_ci_registry)
    previous_tests = None
    for node in parsed.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "TESTS" for target in node.targets
        ):
            previous_tests = ast.literal_eval(node.value)
    if (not isinstance(previous_tests, tuple) or not previous_tests
            or any(not isinstance(item, str) for item in previous_tests)):
        raise ValueError("Cannot independently authenticate original CI test registry")
    from tools.atlas_doctor_lib.ci_tooling_scope import TESTS as candidate_ci_tests
    if not set(previous_tests) <= set(candidate_ci_tests):
        raise ValueError("Candidate removed mandatory baseline CI contracts")
    prior = json.loads(_git("show", f"{base_sha}:tools/atlas_integrity_policy.json"))
    if prior.get("schema_version") != 1:
        raise ValueError("Unrecognized baseline policy")
    base_ci = prior.get("groups", {}).get("CI_INTEGRITY", {}).get("modules")
    if not isinstance(base_ci, list) or not base_ci:
        raise ValueError("Missing original CI certification obligations")
    module_names: set[str] = set()
    for domain in domains:
        if domain == "metadata":
            continue
        if domain not in BASELINE_GROUPS:
            raise ValueError("Unrecognized domain has no baseline obligations")
        for group_name in BASELINE_GROUPS[domain]:
            group = prior.get("groups", {}).get(group_name)
            if (not isinstance(group, dict) or group.get("runner") != "unittest_modules"
                    or not group.get("critical") or not isinstance(group.get("modules"), list)
                    or not group["modules"] or any(
                        not isinstance(n, str) or not n.startswith("tests.test_")
                        for n in group["modules"])):
                raise ValueError("Baseline critical domain group missing: " + group_name)
            module_names.update(group["modules"])
    if "ci" in domains:
        module_names.update(base_ci)
        for name in previous_tests:
            path = root / "tests" / ("test_" + name + ".py")
            if not path.is_file() or path.is_symlink():
                raise ValueError("Missing baseline CI module: " + name)
            module_names.add("tests.test_" + name)
    for domain in domains:
        if domain == "metadata":
            continue
        module_names.update(_module_sources(root, domain))
    # Every changed test is mandatory even when its domain is CI-adjacent.
    for relative in plan.get("changed_paths", ()):
        if relative.startswith("tests/test_") and relative.endswith(".py"):
            test = root / relative
            if not test.is_file() or test.is_symlink():
                raise ValueError("Removed/unsafe changed test: " + relative)
            module_names.add("tests." + test.stem)
    mandatory = sorted(module_names)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromName(name) for name in mandatory])
    if loader.errors:
        raise ValueError("Unimportable mandatory domain test: " + "; ".join(loader.errors)[:1000])
    expected = ids(suite) if mandatory else []
    if mandatory and (not expected or len(set(expected)) != len(expected)):
        raise ValueError("Empty or duplicated exact test identities")
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2, resultclass=ProofResult).run(suite)
    seconds = round(time.perf_counter() - started, 3)
    statuses = result.completed
    complete = bool((not mandatory or (len(statuses) == len(expected)
        and result.testsRun == len(expected)
        and set(k for k, _ in statuses) == set(expected)
        and len(set(k for k, _ in statuses)) == len(expected)
        and all(status == "ok" for _, status in statuses)))
        and result.wasSuccessful())
    return {
        "schema_version": 1, "kind": "atlas_domain_tests_exact_sha",
        "candidate_sha": head, "base_sha": base_sha,
        "baseline_policy_sha256": hashlib.sha256(
            _git("show", f"{base_sha}:tools/atlas_integrity_policy.json").encode()
        ).hexdigest(),
        "domains": domains, "required_modules": mandatory,
        "expected_test_ids": sorted(expected), "successful_test_ids":
            sorted(k for k, status in statuses if status == "ok"),
        "tests_run": result.testsRun,
        "duration_seconds": seconds,
        "status": "PASS_DOMAIN_TESTS_NOT_PHASE_CERTIFIED" if complete else "BLOCKED",
        "tests_executed": True, "full_suite_executed": False,
        "phase_certified": False, "merge_authorized": False,
        "note": "Only domain tests. Independent required specialists and host CI verdict must also PASS.",
    }



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Run exact-SHA selected module tests on this Windows runner")
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
    if outcome["status"] != "READY_TO_EXECUTE":
        print("Modular domain selection BLOCKED:", outcome["reasons"])
        return 1
    if args.execute:
        evidence = execute_domain_tests(outcome, root=Path.cwd(), base_sha=args.base_sha)
        proof = args.output.with_name("domain_test_evidence.json")
        proof.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        if evidence["status"] != "PASS_DOMAIN_TESTS_NOT_PHASE_CERTIFIED":
            print("Modular tests BLOCKED; see", proof)
            return 1
    print("Independent domains:", ", ".join(outcome["domains"]), "status:", outcome["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
