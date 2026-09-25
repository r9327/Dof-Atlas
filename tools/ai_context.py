from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = Path(".ai/context_index.json")
WATCHED_TREES = (
    ".githooks",
    ".github",
    "app",
    "data",
    "scripts",
    "tests",
    "tools",
)
WATCHED_ROOT_FILES = (
    "AGENTS.md",
    "AI_CONTEXT.md",
    "DEVELOPMENT_GUARDRAILS.md",
    "Dofus_Atlas.bat",
    "GITHUB_PROTECTION.md",
    "GUIDE_ULTIME_STATUS.md",
    "PERFORMANCE_GUARDRAILS.md",
    "PHASE_CERTIFICATION.md",
    "ROAD_IA.md",
    "ZERO_TRUST_RULES.md",
    "bootstrap_dofus_atlas.ps1",
    "launch.py",
    "main.py",
    "requirements-pyside.txt",
    "sitecustomize.py",
)
DOMAIN_TEST_MODULES: dict[str, tuple[str, ...]] = {
    "core": ("tests.test_character_identity_guardrails",),
    "data": ("tests.test_critical_json_schema",),
    "encyclopedia": (
        "tests.test_encyclopedia_on_demand_loading",
        "tests.test_encyclopedia_tab_demand_loading",
    ),
    "guide": (
        "tests.test_guide_ultime_manual_prerequisites",
        "tests.test_guide_ultime_final_coverage_catalog",
    ),
    "quality": (
        "tests.test_ai_context",
        "tests.test_repository_git_hooks",
        "tests.test_meta_integrity",
    ),
    "runtime": ("tests.test_startup_resource_contracts",),
    "ui": ("tests.test_performance_guardrails",),
}
DOMAIN_CANONICAL_PATHS: dict[str, tuple[str, ...]] = {
    "guide": (
        "data/routes/guide_ultime_manual/manifest_v1.json",
        "GUIDE_ULTIME_STATUS.md",
    ),
    "quality": (
        "ZERO_TRUST_RULES.md",
        "PHASE_CERTIFICATION.md",
        "tests/critical_regression_inventory.json",
    ),
    "ui": (
        "app/ui/theme.py",
        "app/ui/components.py",
    ),
}


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def committed_tree_sha(root: Path, ref: str = "HEAD") -> str:
    return _git(root, "rev-parse", f"{ref}^{{tree}}")


def staged_tree_sha(root: Path) -> str:
    return _git(root, "write-tree")


def _object_at(root: Path, tree_sha: str, path: str) -> dict[str, str] | None:
    output = _git(root, "ls-tree", tree_sha, "--", path)
    if not output:
        return None
    line = output.splitlines()[0]
    metadata, object_path = line.split("\t", 1)
    mode, object_type, sha = metadata.split(" ", 2)
    if object_path != path:
        return None
    return {"mode": mode, "type": object_type, "sha": sha}


def build_index(root: Path, tree_sha: str) -> dict[str, object]:
    trees: dict[str, dict[str, str]] = {}
    root_files: dict[str, dict[str, str]] = {}

    for path in WATCHED_TREES:
        item = _object_at(root, tree_sha, path)
        if item is not None:
            trees[path] = item

    for path in WATCHED_ROOT_FILES:
        item = _object_at(root, tree_sha, path)
        if item is not None:
            root_files[path] = item

    return {
        "schema_version": 1,
        "source": "git-tree-fingerprints",
        "watched_trees": trees,
        "watched_root_files": root_files,
    }


def render_index(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sync_index(root: Path = ROOT, *, stage: bool = False) -> bool:
    root = root.resolve()
    payload = build_index(root, staged_tree_sha(root))
    target = root / INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    content = render_index(payload)
    previous = target.read_text(encoding="utf-8") if target.is_file() else None
    changed = previous != content
    if changed:
        target.write_text(content, encoding="utf-8", newline="\n")
    if stage:
        _git(root, "add", "--", INDEX_PATH.as_posix())
    return changed


def check_index(root: Path = ROOT, *, ref: str = "HEAD") -> bool:
    root = root.resolve()
    target = root / INDEX_PATH
    if not target.is_file():
        return False
    expected = render_index(build_index(root, committed_tree_sha(root, ref)))
    return target.read_text(encoding="utf-8") == expected


def normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_path(path: str) -> str:
    normalized = normalize_path(path)
    lowered = normalized.casefold()
    name = Path(normalized).name.casefold()

    if "guide" in lowered and (
        lowered.startswith("app/modules/encyclopedia/")
        or lowered.startswith("data/routes/")
        or lowered.startswith("tools/")
        or lowered.startswith("tests/")
    ):
        return "guide"
    if lowered.startswith("app/modules/encyclopedia/") or lowered.startswith("data/encyclopedia/"):
        return "encyclopedia"
    if lowered.startswith("app/core/") or lowered.startswith("app/services/"):
        return "core"
    if lowered.startswith("app/ui/") or lowered.startswith("app/pages/") or name == "main.py":
        return "ui"
    if lowered.startswith("app/"):
        return "runtime"
    if lowered.startswith("data/"):
        return "data"
    if lowered.startswith("tests/"):
        return "tests"
    if lowered.startswith("tools/") or lowered.startswith(".github/") or lowered.startswith(".githooks/"):
        return "quality"
    return "repository"


def recommended_context(paths: Iterable[str]) -> list[str]:
    domains = {classify_path(path) for path in paths}
    documents = ["AGENTS.md", "AI_CONTEXT.md", "DEVELOPMENT_GUARDRAILS.md"]
    if domains & {"ui", "runtime", "encyclopedia", "guide"}:
        documents.append("PERFORMANCE_GUARDRAILS.md")
    if "guide" in domains:
        documents.append("GUIDE_ULTIME_STATUS.md")
    if domains & {"quality", "tests"}:
        documents.append("ZERO_TRUST_RULES.md")
    if domains & {"quality", "tests", "guide"}:
        documents.append("PHASE_CERTIFICATION.md")
    return list(dict.fromkeys(documents))


def _test_module_path(module: str) -> Path:
    return Path(*module.split(".")).with_suffix(".py")


def recommended_tests(root: Path, paths: Iterable[str]) -> list[str]:
    normalized_paths = [normalize_path(path) for path in paths]
    modules: list[str] = []

    for path in normalized_paths:
        path_obj = Path(path)
        if path.startswith("tests/") and path_obj.suffix.casefold() == ".py" and path_obj.name.startswith("test_"):
            modules.append(".".join(path_obj.with_suffix("").parts))
            continue
        if path_obj.suffix.casefold() == ".py":
            exact = Path("tests") / f"test_{path_obj.stem}.py"
            if (root / exact).is_file():
                modules.append(".".join(exact.with_suffix("").parts))

    domains = {classify_path(path) for path in normalized_paths}
    for domain in sorted(domains):
        modules.extend(DOMAIN_TEST_MODULES.get(domain, ()))

    existing = [module for module in modules if (root / _test_module_path(module)).is_file()]
    return list(dict.fromkeys(existing))


def recommended_canonical_paths(root: Path, paths: Iterable[str]) -> list[str]:
    domains = {classify_path(path) for path in paths}
    candidates: list[str] = []
    for domain in sorted(domains):
        candidates.extend(DOMAIN_CANONICAL_PATHS.get(domain, ()))
    return list(dict.fromkeys(path for path in candidates if (root / path).exists()))


def _changed_paths(root: Path) -> list[str]:
    paths: set[str] = set()
    for arguments in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        output = _git(root, *arguments)
        paths.update(line for line in output.splitlines() if line.strip())
    return sorted(paths)


def _status_payload(root: Path) -> dict[str, object]:
    paths = _changed_paths(root)
    domains: dict[str, list[str]] = {}
    for path in paths:
        domains.setdefault(classify_path(path), []).append(path)
    return {
        "branch": _git(root, "branch", "--show-current"),
        "head": _git(root, "rev-parse", "HEAD"),
        "remote": _git(root, "remote", "get-url", "origin", check=False),
        "changed_paths": paths,
        "domains": domains,
        "recommended_context": recommended_context(paths),
        "recommended_tests": recommended_tests(root, paths),
        "canonical_anchors": recommended_canonical_paths(root, paths),
        "committed_index_current": check_index(root),
    }


def _print_status(payload: dict[str, object]) -> None:
    print(f"branch: {payload['branch']}")
    print(f"head: {payload['head']}")
    if payload.get("remote"):
        print(f"remote: {payload['remote']}")
    print(f"committed context index: {'CURRENT' if payload['committed_index_current'] else 'STALE/MISSING'}")
    changed_paths = payload["changed_paths"]
    if not changed_paths:
        print("working tree: no tracked/untracked content changes")
    else:
        print("changed domains:")
        for domain, domain_paths in payload["domains"].items():
            print(f"  {domain}: {len(domain_paths)}")
            for path in domain_paths[:8]:
                print(f"    - {path}")
            if len(domain_paths) > 8:
                print(f"    - ... +{len(domain_paths) - 8}")
    print("read/review:")
    for document in payload["recommended_context"]:
        print(f"  - {document}")
    if payload["canonical_anchors"]:
        print("canonical anchors:")
        for path in payload["canonical_anchors"]:
            print(f"  - {path}")
    if payload["recommended_tests"]:
        print("targeted tests:")
        for module in payload["recommended_tests"]:
            print(f"  - {module}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compact live context router for Dofus Atlas agents.")
    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status", help="Show live repository context for an agent.")
    status_parser.add_argument("--json", action="store_true")

    route_parser = subparsers.add_parser("route", help="Route one or more paths to useful context and tests.")
    route_parser.add_argument("paths", nargs="+")
    route_parser.add_argument("--json", action="store_true")

    sync_parser = subparsers.add_parser("sync", help="Regenerate the compact staged-tree context index.")
    sync_parser.add_argument("--stage", action="store_true")

    check_parser = subparsers.add_parser("check", help="Verify the committed context index against a ref.")
    check_parser.add_argument("--ref", default="HEAD")

    args = parser.parse_args(argv)
    root = ROOT.resolve()
    command = args.command or "status"

    if command == "status":
        payload = _status_payload(root)
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            _print_status(payload)
        return 0

    if command == "route":
        payload = {
            "domains": {path: classify_path(path) for path in args.paths},
            "recommended_context": recommended_context(args.paths),
            "canonical_anchors": recommended_canonical_paths(root, args.paths),
            "recommended_tests": recommended_tests(root, args.paths),
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for path, domain in payload["domains"].items():
                print(f"{domain}: {path}")
            print("read/review:")
            for document in payload["recommended_context"]:
                print(f"  - {document}")
            if payload["canonical_anchors"]:
                print("canonical anchors:")
                for path in payload["canonical_anchors"]:
                    print(f"  - {path}")
            if payload["recommended_tests"]:
                print("targeted tests:")
                for module in payload["recommended_tests"]:
                    print(f"  - {module}")
        return 0

    if command == "sync":
        changed = sync_index(root, stage=args.stage)
        print("AI context index updated" if changed else "AI context index already current")
        return 0

    if command == "check":
        ok = check_index(root, ref=args.ref)
        print("AI context index: PASS" if ok else "AI context index: STALE/MISSING")
        return 0 if ok else 1

    parser.error(f"unsupported command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
