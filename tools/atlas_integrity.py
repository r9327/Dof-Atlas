from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

from tools.atlas_meta_integrity import classify_root_of_trust_changes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("tools/atlas_integrity_policy.json")
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

CRITICAL_PATTERNS = (
    ".github/workflows/**",
    "DEVELOPMENT_GUARDRAILS.md",
    "tests/critical_regression_inventory.json",
    "tests/test_*guardrails.py",
    "tests/test_architecture_debt_baseline.py",
    "tests/test_meta_integrity.py",
    "tools/atlas_integrity.py",
    "tools/atlas_integrity_policy.json",
    "tools/atlas_meta_integrity.py",
    "tools/atlas_critical_coverage.py",
    "tools/atlas_critical_coverage.json",
    "tools/run_guide_ultime_ci.ps1",
)

HIGH_PATTERNS = (
    "app/core/character_identity.py",
    "app/core/json_store.py",
    "app/**/*identity*.py",
    "app/**/*progress*.py",
    "app/**/*provider*.py",
    "app/**/*repository*.py",
    "app/**/*runtime*.py",
    "app/**/*startup*.py",
    "app/**/*lazy*.py",
    "app/**/*async*.py",
    "app/**/*thread*.py",
    "app/**/*lifecycle*.py",
    "app/**/*hook*.py",
    "local_dofus_data/**",
    "data/**/*.db",
    "data/**/*.json",
    "main.py",
    "Dofus_Atlas.bat",
    "bootstrap_dofus_atlas.ps1",
    "requirements-pyside.txt",
)

MEDIUM_PATTERNS = (
    "app/**",
    "tests/test_*.py",
)


class IntegrityConfigError(RuntimeError):
    pass


def normalize_paths(paths: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for raw in paths:
        path = str(raw).strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if path:
            normalized.add(path)
    return sorted(normalized)


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def affected_groups(paths: Iterable[str]) -> list[str]:
    groups: set[str] = set()
    for path in normalize_paths(paths):
        lowered = path.lower()
        if path.startswith("tests/test_") and path.endswith(".py"):
            groups.add("DIFF_TARGETS")
        if "identity" in lowered or path == "app/core/character_identity.py":
            groups.add("IDENTITY")
        if any(token in lowered for token in ("progress", "persistence", "repository", "json_store")):
            groups.add("PERSISTENCE")
        if any(token in lowered for token in ("startup", "launcher", "preflight")) or path in {
            "main.py",
            "Dofus_Atlas.bat",
            "bootstrap_dofus_atlas.ps1",
            "requirements-pyside.txt",
        }:
            groups.add("STARTUP")
        if "lazy" in lowered or "on_demand" in lowered:
            groups.add("LAZY_LOADING")
        if any(token in lowered for token in ("async", "thread", "lifecycle", "hook", "timer", "future")):
            groups.add("ASYNC_LIFECYCLE")
        if path.startswith("app/") and any(
            token in lowered
            for token in ("/views/", "/pages/", "home", "guide", "quest", "achievement")
        ):
            groups.add("GOLDEN_FLOWS")
        if path.startswith(".github/workflows/"):
            groups.add("CI_INTEGRITY")
        if path.startswith("data/") or path.startswith("local_dofus_data/"):
            groups.add("DATA_INTEGRITY")
    return sorted(groups)


def classify_risk(paths: Iterable[str]) -> dict[str, Any]:
    changed = normalize_paths(paths)
    root_of_trust = classify_root_of_trust_changes(changed)
    reasons: list[str] = []
    risk = "LOW"

    if root_of_trust["modified"]:
        risk = "CRITICAL"
        reasons.append("root_of_trust")
    for path in changed:
        candidate = "LOW"
        if _matches(path, CRITICAL_PATTERNS):
            candidate = "CRITICAL"
        elif _matches(path, HIGH_PATTERNS):
            candidate = "HIGH"
        elif _matches(path, MEDIUM_PATTERNS):
            candidate = "MEDIUM"
        if RISK_ORDER[candidate] > RISK_ORDER[risk]:
            risk = candidate
        if candidate != "LOW":
            reasons.append(f"{candidate}:{path}")

    return {
        "risk": risk,
        "reasons": sorted(set(reasons)),
        "affected_groups": affected_groups(changed),
        "root_of_trust": root_of_trust,
    }


def _run_git(root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def repository_head(root: Path) -> str:
    completed = _run_git(root, ["rev-parse", "HEAD"])
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def optional_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        payload = json.loads((root / relative).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_base_ref(root: Path, requested: str | None) -> str:
    base_ref = requested
    if base_ref is None:
        upstream = _run_git(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
        if upstream.returncode != 0 or not upstream.stdout.strip():
            raise IntegrityConfigError("no upstream is configured; pass --base-ref explicitly")
        base_ref = upstream.stdout.strip()
    resolved = _run_git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
    if resolved.returncode != 0:
        raise IntegrityConfigError(f"base ref cannot be resolved: {base_ref}")
    return base_ref


def changed_files(root: Path, base_ref: str) -> list[str]:
    commands = (
        ["diff", "--name-only", f"{base_ref}...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--cached", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for arguments in commands:
        completed = _run_git(root, arguments)
        if completed.returncode != 0:
            raise IntegrityConfigError(
                f"git {' '.join(arguments)} failed: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        paths.update(line for line in completed.stdout.splitlines() if line.strip())
    return normalize_paths(paths)


def build_diff_report(paths: Iterable[str], classification: dict[str, Any]) -> dict[str, Any]:
    changed = normalize_paths(paths)
    root_modified = classification["root_of_trust"]["modified"]
    return {
        "app": [path for path in changed if path.startswith("app/")],
        "tests": [path for path in changed if path.startswith("tests/")],
        "tools": [path for path in changed if path.startswith("tools/")],
        "ci": [path for path in changed if path.startswith(".github/workflows/")],
        "data": [
            path
            for path in changed
            if path.startswith("data/") or path.startswith("local_dofus_data/")
        ],
        "root_of_trust": root_modified,
        "identity_persistence": [
            path
            for path in changed
            if any(token in path.lower() for token in ("identity", "progress", "persistence", "repository"))
        ],
        "risk": classification["risk"],
    }


class CommandExecutor:
    def run(self, command: list[str], cwd: Path) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise IntegrityConfigError(f"cannot execute {command[0]}: {exc}") from exc
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }


def load_policy(root: Path, policy_path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    path = policy_path if policy_path.is_absolute() else root / policy_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityConfigError(f"integrity policy unavailable: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise IntegrityConfigError("integrity policy schema_version must be 1")
    groups = payload.get("groups")
    modes = payload.get("modes")
    risk_requirements = payload.get("risk_requirements")
    if not isinstance(groups, dict) or not isinstance(modes, dict) or not isinstance(risk_requirements, dict):
        raise IntegrityConfigError("integrity policy groups, modes and risk_requirements must be objects")
    expected_modes = {"FAST", "CRITICAL", "FULL", "DEEP"}
    if set(modes) != expected_modes:
        raise IntegrityConfigError("integrity policy must define FAST, CRITICAL and FULL modes")
    if set(risk_requirements) != set(RISK_ORDER):
        raise IntegrityConfigError("integrity policy must define LOW, MEDIUM, HIGH and CRITICAL risks")
    for owner, names in {**modes, **{f"risk:{key}": value for key, value in risk_requirements.items()}}.items():
        if not isinstance(names, list) or any(name not in groups for name in names):
            raise IntegrityConfigError(f"integrity policy references an unknown group in {owner}")
    return payload


def _changed_test_modules(root: Path, paths: Iterable[str]) -> list[str]:
    modules = []
    for path in normalize_paths(paths):
        if (
            path.startswith("tests/test_")
            and path.endswith(".py")
            and (root / path).is_file()
        ):
            modules.append(path[:-3].replace("/", "."))
    return sorted(set(modules))


def _critical_inventory_modules(root: Path) -> list[str]:
    path = root / "tests/critical_regression_inventory.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        protections = payload["protections"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise IntegrityConfigError(f"critical inventory unavailable: {exc}") from exc
    modules: set[str] = set()
    for protection in protections:
        owner = protection.get("owner", {}) if isinstance(protection, dict) else {}
        relative = owner.get("path")
        if owner.get("kind") == "python_test" and isinstance(relative, str) and relative.endswith(".py"):
            modules.add(relative[:-3].replace("/", ".").replace("\\", "."))
    if not modules:
        raise IntegrityConfigError("critical inventory contains no executable Python test owner")
    return sorted(modules)


def _command_for_group(
    name: str,
    config: dict[str, Any],
    *,
    root: Path,
    base_ref: str,
    changed: list[str],
) -> list[str] | None:
    runner = config.get("runner")
    python = sys.executable
    if runner == "meta_integrity":
        return [
            python,
            "-X",
            "faulthandler",
            "-m",
            "tools.atlas_meta_integrity",
            "--root",
            str(root),
            "--base-ref",
            base_ref,
            "--json",
        ]
    if runner == "compileall":
        paths = config.get("paths")
        if not isinstance(paths, list) or not paths:
            raise IntegrityConfigError(f"{name}: compileall paths are missing")
        return [python, "-m", "compileall", "-q", *paths]
    if runner == "generated_files":
        return [python, "-m", "tools.check_generated_files", "--root", str(root), "--tracked"]
    if runner == "unittest_modules":
        modules = config.get("modules")
        if not isinstance(modules, list) or not modules:
            raise IntegrityConfigError(f"{name}: unittest modules are missing")
        return [python, "-X", "faulthandler", "-m", "unittest", "-v", *modules]
    if runner == "fault_injection":
        return [python, "-X", "faulthandler", "-m", "tools.atlas_fault_injection", "--json"]
    if runner == "critical_coverage":
        return [python, "-X", "faulthandler", "-m", "tools.atlas_critical_coverage", "--json"]
    if runner == "targeted_mutation":
        return [python, "-m", "tools.atlas_mutation", "--json"]
    if runner == "random_order":
        return [python, "-X", "faulthandler", "-m", "tools.random_order_tests", "--seed", "9327", "--quiet"]
    if runner == "timing_performance":
        return [python, "-X", "faulthandler", "-m", "app.modules.encyclopedia.tools.benchmark_guides_performance"]
    if runner == "critical_inventory":
        return [
            python,
            "-X",
            "faulthandler",
            "-m",
            "unittest",
            "-v",
            *_critical_inventory_modules(root),
        ]
    if runner == "changed_tests":
        modules = _changed_test_modules(root, changed)
        if not modules:
            return None
        return [python, "-X", "faulthandler", "-m", "unittest", "-v", *modules]
    if runner == "full_unittest_discovery":
        return [
            python,
            "-X",
            "faulthandler",
            "-m",
            "unittest",
            "discover",
            "-v",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ]
    if runner == "guide_ci":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "tools/run_guide_ultime_ci.ps1",
        ]
    raise IntegrityConfigError(f"{name}: unsupported runner {runner!r}")


def _test_count(output: str) -> int | None:
    matches = re.findall(r"Ran\s+(\d+)\s+tests?", output)
    return int(matches[-1]) if matches else None


def _guide_details(root: Path, config: dict[str, Any]) -> tuple[list[str], int | None]:
    summary_path = root / "artifacts/ci_guide_ultime_logs/ci_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return [], None
    mapping = config.get("blocker_ids", {})
    blockers: list[str] = []
    for check in summary.get("checks", []):
        if not isinstance(check, dict) or check.get("exit_code") == 0:
            continue
        name = check.get("name")
        blockers.append(mapping.get(name, f"GUIDE_CHECK_FAILED:{name}"))
    return sorted(set(blockers)), summary.get("total_checks")


def _required_groups(policy: dict[str, Any], mode: str, classification: dict[str, Any]) -> list[str]:
    requested = set(policy["modes"][mode])
    requested.update(policy["risk_requirements"][classification["risk"]])
    requested.update(classification["affected_groups"])
    if mode not in {"FULL", "DEEP"}:
        requested.discard("FULL_SUITE")
        requested.discard("DATA_INTEGRITY")
    return [name for name in policy["groups"] if name in requested]


def verdict_from_groups(groups: dict[str, dict[str, Any]], required: Iterable[str]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    for name in required:
        group = groups[name]
        if not group.get("blocking", True):
            continue
        blockers.extend(group.get("blockers", []))
        if group.get("status") == "NOT_RUN":
            blockers.append(f"{name}_NOT_RUN")
        elif group.get("status") != "PASS" and not group.get("blockers"):
            blockers.append(f"{name}_FAILED")
    unique = sorted(set(blockers))
    return ("PASS" if not unique else "BLOCKED"), unique


def exit_code_for_report(report: dict[str, Any]) -> int:
    if report.get("verdict") == "PASS":
        return 0
    if report.get("verdict") == "BLOCKED":
        return 1
    return 2


def execute_gate(
    *,
    root: Path,
    mode: str,
    base_ref: str,
    changed: list[str],
    policy: dict[str, Any],
    executor: Any | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    mode = mode.upper()
    if mode not in policy["modes"]:
        raise IntegrityConfigError(f"unsupported mode: {mode}")
    executor = executor or CommandExecutor()
    classification = classify_risk(changed)
    required = _required_groups(policy, mode, classification)
    groups = {
        name: {
            "status": "NOT_RUN",
            "required": name in required,
            "owner": config.get("owner"),
            "blocking": config.get("blocking", True),
            "commands": [],
            "tests": None,
            "blockers": [],
        }
        for name, config in policy["groups"].items()
    }
    commands: list[dict[str, Any]] = []
    blockers: list[str] = []
    critical_debt = 0
    guardrail_counts: dict[str, int | None] = {}
    protections_missing: list[str] = []

    for name in required:
        config = policy["groups"][name]
        command = _command_for_group(name, config, root=root, base_ref=base_ref, changed=changed)
        if command is None:
            groups[name]["status"] = "PASS"
            groups[name]["tests"] = 0
            continue
        result = executor.run(command, root)
        if not isinstance(result, dict) or "exit_code" not in result:
            raise IntegrityConfigError(f"{name}: command executor returned an invalid result")
        output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
        command_report = {
            "group": name,
            "command": result.get("command", command),
            "exit_code": int(result["exit_code"]),
            "duration_seconds": float(result.get("duration_seconds", 0.0)),
            "tests": _test_count(output),
        }
        if int(result["exit_code"]) != 0:
            command_report["output_tail"] = "\n".join(output.strip().splitlines()[-40:])
        commands.append(command_report)
        groups[name]["commands"].append(command_report)
        groups[name]["tests"] = command_report["tests"]
        if command_report["exit_code"] == 0:
            status = config.get("success_status", "PASS")
        else:
            status = "BLOCKED" if config.get("blocking", True) else "MEASURED_ONLY_FAILED"
        groups[name]["status"] = status

        group_blockers: list[str] = []
        if name == "META_INTEGRITY":
            try:
                meta = json.loads(result.get("stdout", ""))
            except (json.JSONDecodeError, TypeError) as exc:
                raise IntegrityConfigError(f"META_INTEGRITY returned invalid JSON: {exc}") from exc
            zero_counts = meta.get("zero_debt", {})
            if isinstance(zero_counts, dict):
                guardrail_counts = dict(zero_counts)
                critical_debt = sum(value for value in zero_counts.values() if isinstance(value, int))
            protections_missing = list(meta.get("protections_missing", []))
            groups[name]["details"] = {
                "protections_missing": meta.get("protections_missing", []),
                "root_of_trust": meta.get("root_of_trust", {}),
            }
        if name == "DATA_INTEGRITY":
            group_blockers, checks = _guide_details(root, config)
            groups[name]["tests"] = checks
        if name in {"FAULT_INJECTION", "CRITICAL_COVERAGE", "TARGETED_MUTATION"}:
            try:
                groups[name]["details"] = json.loads(result.get("stdout", ""))
            except (json.JSONDecodeError, TypeError):
                groups[name]["details"] = {"parse_error": True}
        if status not in {"PASS", "MEASURED_ONLY"} and config.get("blocking", True) and not group_blockers:
            group_blockers.append(f"{name}_FAILED")
        groups[name]["blockers"] = group_blockers
        blockers.extend(group_blockers)

    verdict, blockers = verdict_from_groups(groups, required)
    report = {
        "schema_version": 1,
        "mode": mode,
        "head": repository_head(root),
        "risk": classification["risk"],
        "verdict": verdict,
        "base_ref": base_ref,
        "changed_files": changed,
        "groups": groups,
        "commands": commands,
        "blockers": sorted(set(blockers)),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "root_of_trust_changed": bool(classification["root_of_trust"]["modified"]),
        "critical_debt": critical_debt,
        "budgets": {
            "classification": "BUDGETED",
            "status": groups["RESOURCE_BUDGETS"]["status"],
            "policy": optional_json(root, "tools/atlas_performance_budgets.json").get("metrics", {}),
        },
        "guardrails": guardrail_counts,
        "guardrail_bypass": len(protections_missing),
        "lifecycle": {
            "async": groups["ASYNC_LIFECYCLE"]["status"],
            "monolithic": groups["MONOLITHIC_LIFECYCLE"]["status"],
        },
        "coverage": groups["CRITICAL_COVERAGE"].get("details", {"verdict": "NOT_RUN"}),
        "mutation": groups["TARGETED_MUTATION"].get("details", {"verdict": "NOT_RUN"}),
        "github_protection": {
            "branch": "feature/guide-ultime-v5-ui",
            "branch_protection": "NOT_VERIFIED",
            "ruleset": "NOT_VERIFIED",
            "required_checks": "ADMIN_ACTION_REQUIRED",
            "pull_request_required": "ADMIN_ACTION_REQUIRED",
            "force_push": "NOT_VERIFIED",
            "deletion": "NOT_VERIFIED",
            "bypass": "NOT_VERIFIED",
            "codeowners": "PREPARED_LOCAL",
        },
        "counts": {
            "commands": len(commands),
            "tests": sum(command["tests"] or 0 for command in commands),
        },
        "risk_reasons": classification["reasons"],
        "diff_report": build_diff_report(changed, classification),
        "validations_required": required,
        "validations_executed": [name for name in required if groups[name]["status"] != "NOT_RUN"],
        "validations_not_run": [name for name in policy["groups"] if groups[name]["status"] == "NOT_RUN"],
        "performance": {
            "resource_budgets": {
                "classification": "BUDGETED",
                "status": groups["RESOURCE_BUDGETS"]["status"],
            },
            "timing_rss_cpu": {
                "classification": "MEASURED_ONLY",
                "status": "MEASURED_ONLY",
            },
        },
    }
    return report


def _print_human(report: dict[str, Any]) -> None:
    print("ATLAS INTEGRITY")
    print()
    print(f"{'Mode':28} {report['mode']}")
    print(f"{'Risk':28} {report['risk']}")
    print(f"{'Base ref':28} {report['base_ref']}")
    print(f"{'Root of trust changed':28} {'YES' if report['root_of_trust_changed'] else 'NO'}")
    print()
    for name, group in report["groups"].items():
        if group["required"]:
            print(f"{name.replace('_', ' ').title():28} {group['status']}")
    performance = report.get("performance", {})
    if performance:
        print(f"{'Timing performance':28} {performance['timing_rss_cpu']['status']}")
    print()
    print(f"{'Critical debt':28} {report['critical_debt']}")
    print(f"{'Blockers':28} {len(report['blockers'])}")
    print()
    print(f"VERDICT: {report['verdict']}")
    if report["blockers"]:
        print()
        print("Reasons:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    diff = report["diff_report"]
    print()
    print("DIFF REPORT")
    for key in ("app", "tests", "tools", "ci", "data", "root_of_trust", "identity_persistence"):
        value = diff[key]
        rendered = len(value) if isinstance(value, list) else ("YES" if value else "NO")
        print(f"{key.replace('_', ' ').title():28} {rendered}")
        if isinstance(value, list):
            for path in value:
                print(f"  - {path}")
    print(f"{'Validations required':28} {', '.join(report['validations_required'])}")
    print(f"{'Validations executed':28} {', '.join(report['validations_executed'])}")
    print(f"{'Validations not executed':28} {', '.join(report['validations_not_run'])}")
    print()
    print("COMMANDS")
    for command in report["commands"]:
        tests = "" if command["tests"] is None else f", tests={command['tests']}"
        print(
            f"- {command['group']}: exit={command['exit_code']}, "
            f"duration={command['duration_seconds']:.3f}s{tests}"
        )
        if command.get("output_tail"):
            print("  failure output:")
            for line in str(command["output_tail"]).splitlines():
                print(f"    {line}")


def _error_report(mode: str, base_ref: str | None, message: str, duration: float) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": mode.upper(),
        "risk": "UNKNOWN",
        "verdict": "ERROR",
        "base_ref": base_ref,
        "changed_files": [],
        "groups": {},
        "commands": [],
        "blockers": [],
        "duration_seconds": round(duration, 3),
        "root_of_trust_changed": False,
        "critical_debt": None,
        "error": message,
    }


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description="Run the Dofus Atlas local Zero-Trust integrity gate.")
    parser.add_argument("mode", choices=("fast", "critical", "full", "deep"))
    parser.add_argument("--base-ref")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--json", action="store_true", help="Write only the machine-readable report.")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        policy = load_policy(root, args.policy)
        base_ref = resolve_base_ref(root, args.base_ref)
        changed = changed_files(root, base_ref)
        report = execute_gate(
            root=root,
            mode=args.mode,
            base_ref=base_ref,
            changed=changed,
            policy=policy,
        )
    except Exception as exc:
        message = str(exc)
        report = _error_report(args.mode, args.base_ref, message, time.perf_counter() - started)
        if not isinstance(exc, IntegrityConfigError):
            report["traceback"] = traceback.format_exc()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("ATLAS INTEGRITY")
            print()
            print("VERDICT: ERROR")
            print(f"Reason: {message}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return exit_code_for_report(report)


if __name__ == "__main__":
    raise SystemExit(main())
