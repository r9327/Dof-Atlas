from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("tests/critical_regression_inventory.json")

HARD_REQUIRED_RULE_IDS = frozenset(
    {
        "ARCH_RUNTIME_PATCH_ZERO",
        "ARCH_LEGACY_IMPORT_ZERO",
        "ARCH_RUNTIME_VERSION_ZERO",
        "IDENTITY_LEGACY_DEBT_ZERO",
        "IDENTITY_CANONICAL_CHARACTER",
        "PERSISTENCE_CANONICAL_WRITE_BOUNDARY",
        "PERSISTENCE_MIGRATION_IDEMPOTENCE",
        "PERSISTENCE_BATCH_IDEMPOTENCE",
        "PERSISTENCE_CONCURRENT_MERGE",
        "PROJECT_GUARDRAILS",
        "META_INTEGRITY_VERIFIER",
        "META_INTEGRITY_ATTACK_TESTS",
        "CI_RUNNER_CONTRACT",
        "APP_CI_WORKFLOW",
        "CI_FINAL_VERDICT",
        "FULL_DISCOVERY_SCOPE",
        "GUIDE_CI_WORKFLOW",
        "GUIDE_CANONICAL_RUNNER",
        "QT_CROSS_SUITE_TEARDOWN",
        "QT_HOOK_SHUTDOWN",
        "GUIDE_PREREQUISITE_AUDIT",
        "GUIDE_FINAL_COVERAGE_AUDIT",
        "INTEGRITY_GATE_POLICY",
        "INTEGRITY_GATE_RUNNER",
        "INTEGRITY_GATE_CONTRACT",
        "INTEGRITY_GATE_CI",
        "RESOURCE_BUDGET_POLICY",
        "RESOURCE_BUDGET_CONTRACT",
        "QT_ASYNC_NON_ACCUMULATION",
        "STARTUP_RESOURCE_CONTRACT",
        "GENERATED_FILES_GUARD",
        "REPOSITORY_HOOKS",
        "RANDOM_ORDER_RUNNER",
        "FAULT_INJECTION_CONTRACTS",
        "TARGETED_MUTATION_CONTRACT",
        "CRITICAL_COVERAGE_CONTRACT",
        "DEEP_VALIDATION_WORKFLOW",
    }
)

ZERO_BASELINES = {
    "ARCH_RUNTIME_PATCH_ZERO": (
        "tests/test_architecture_debt_baseline.py",
        "RUNTIME_PATCH_BASELINE",
    ),
    "ARCH_LEGACY_IMPORT_ZERO": (
        "tests/test_architecture_debt_baseline.py",
        "LEGACY_IMPORT_BASELINE",
    ),
    "ARCH_RUNTIME_VERSION_ZERO": (
        "tests/test_architecture_debt_baseline.py",
        "RUNTIME_VERSION_BASELINE",
    ),
    "IDENTITY_LEGACY_DEBT_ZERO": (
        "tests/test_character_identity_guardrails.py",
        "KNOWN_SLOT_BUSINESS_DEBT",
    ),
}

SENSITIVE_PATTERNS = (
    ".github/workflows/**",
    "tests/critical_regression_inventory.json",
    "tests/test_meta_integrity.py",
    "tests/test_*guardrails.py",
    "tests/test_architecture_debt_baseline.py",
    "tests/test_character_identity*.py",
    "tests/test_quest_visuals_lot6.py",
    "tests/test_*progress*.py",
    "tools/atlas_meta_integrity.py",
    "tools/atlas_integrity.py",
    "tools/atlas_integrity_policy.json",
    "tools/atlas_performance_budget.py",
    "tools/atlas_performance_budgets.json",
    "tools/atlas_critical_coverage.py",
    "tools/atlas_critical_coverage.json",
    "tools/atlas_fault_injection.py",
    "tools/atlas_fault_injection.json",
    "tools/atlas_mutation.py",
    "tools/random_order_tests.py",
    "tools/check_generated_files.py",
    ".githooks/**",
    "tools/run_guide_ultime_ci.ps1",
    "tools/audit_guide_ultime_*.py",
    "app/core/character_identity.py",
    "app/modules/encyclopedia/services/*progress*.py",
)

ROOT_OF_TRUST_FILES = frozenset(
    {
        ".github/workflows/app-ci.yml",
        ".github/workflows/guide-ultime-v5-ui.yml",
        "app/core/character_identity.py",
        "tests/critical_regression_inventory.json",
        "tests/test_architecture_debt_baseline.py",
        "tests/test_character_identity_guardrails.py",
        "tests/test_ci_runner_guardrails.py",
        "tests/test_meta_integrity.py",
        "tests/test_atlas_integrity.py",
        "tests/test_performance_budgets.py",
        "tests/test_qt_async_non_accumulation.py",
        "tests/test_startup_resource_contracts.py",
        "tools/atlas_meta_integrity.py",
        "tools/atlas_integrity.py",
        "tools/atlas_integrity_policy.json",
        "tools/atlas_performance_budget.py",
        "tools/atlas_performance_budgets.json",
        "tools/atlas_critical_coverage.py",
        "tools/atlas_critical_coverage.json",
        "tests/test_critical_coverage.py",
        "tests/test_generated_files_guard.py",
        "tests/test_repository_git_hooks.py",
        "tests/test_random_order_runner.py",
        "tests/test_fault_injection_contracts.py",
        "tests/test_targeted_mutation.py",
        "tools/atlas_fault_injection.py",
        "tools/atlas_fault_injection.json",
        "tools/atlas_mutation.py",
        "tools/random_order_tests.py",
        "tools/check_generated_files.py",
        ".github/workflows/deep-validation.yml",
        "tools/run_guide_ultime_ci.ps1",
    }
)

_SKIP_DECORATORS = {
    "unittest.skip",
    "unittest.skipIf",
    "unittest.skipUnless",
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "pytest.mark.xfail",
}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("inventory root must be an object")
    return payload


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _qualified_name(node.func)
    return ""


def _find_test_method(
    tree: ast.Module, symbol: str
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef | None, ast.ClassDef | None]:
    parts = symbol.split(".")
    if len(parts) != 2:
        return None, None
    class_name, method_name = parts
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                return child, node
        return None, node
    return None, None


def _skip_markers(nodes: Iterable[ast.AST]) -> list[str]:
    found: set[str] = set()
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                name = _qualified_name(decorator)
                if name in _SKIP_DECORATORS:
                    found.add(name)
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func)
            if name in {"pytest.skip", "self.skipTest"}:
                found.add(name)
    return sorted(found)


def _without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _literal_expression(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError):
        return False
    return True


def _is_constant_assertion(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Assert):
        return _literal_expression(statement.test)
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    call = statement.value
    name = _qualified_name(call.func)
    if not name.startswith("self.assert"):
        return False
    return bool(call.args) and all(_literal_expression(argument) for argument in call.args)


def _has_verification(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(method):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func)
            if name.startswith("self.assert") or name.startswith("pytest.raises"):
                return True
            if name in {"subprocess.run", "subprocess.check_call", "subprocess.check_output"}:
                return True
    return False


def inspect_critical_test(path: Path, symbol: str) -> list[str]:
    if not path.is_file():
        return [f"critical test file missing: {path.as_posix()}"]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=path.as_posix())
    except SyntaxError as exc:
        return [f"critical test cannot be parsed: {path.as_posix()}: {exc}"]
    method, owner_class = _find_test_method(tree, symbol)
    if method is None:
        return [f"critical test method missing: {path.as_posix()}:{symbol}"]

    issues: list[str] = []
    markers = _skip_markers([owner_class, method, *ast.walk(method)])
    if markers:
        issues.append(f"critical skip/xfail: {path.as_posix()}:{symbol}: {', '.join(markers)}")

    body = _without_docstring(method.body)
    if not body or all(isinstance(statement, ast.Pass) for statement in body):
        issues.append(f"critical test is empty: {path.as_posix()}:{symbol}")
        return issues
    if isinstance(body[0], ast.Return):
        issues.append(f"critical test returns immediately: {path.as_posix()}:{symbol}")

    for node in ast.walk(method):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            caught = _qualified_name(handler.type) if handler.type is not None else "bare"
            swallowed = bool(handler.body) and all(isinstance(item, ast.Pass) for item in handler.body)
            if caught in {"bare", "Exception", "BaseException"} and swallowed:
                issues.append(
                    f"critical test swallows {caught}: {path.as_posix()}:{symbol}"
                )

    if body and all(_is_constant_assertion(statement) for statement in body):
        issues.append(f"critical test has only constant assertions: {path.as_posix()}:{symbol}")
    elif not _has_verification(method):
        issues.append(f"critical test has no assertion or verification call: {path.as_posix()}:{symbol}")
    return issues


def validate_inventory(payload: dict[str, Any], root: Path) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    protections = payload.get("protections")
    if payload.get("schema_version") != 1:
        issues.append("inventory schema_version must be 1")
    if not isinstance(protections, list):
        return [*issues, "inventory protections must be a list"], []

    ids = [item.get("id") for item in protections if isinstance(item, dict)]
    valid_ids = [item for item in ids if isinstance(item, str) and item]
    duplicates = sorted({rule_id for rule_id in valid_ids if valid_ids.count(rule_id) > 1})
    if duplicates:
        issues.append(f"duplicate critical IDs: {', '.join(duplicates)}")
    missing_ids = sorted(HARD_REQUIRED_RULE_IDS - set(valid_ids))
    if missing_ids:
        issues.append(f"hard required IDs missing: {', '.join(missing_ids)}")

    critical_tests: list[str] = []
    for item in protections:
        if not isinstance(item, dict):
            issues.append("inventory protection must be an object")
            continue
        rule_id = item.get("id", "<missing-id>")
        owner = item.get("owner")
        if not isinstance(owner, dict):
            issues.append(f"{rule_id}: owner missing")
            continue
        relative = owner.get("path")
        kind = owner.get("kind")
        if not isinstance(relative, str) or not relative:
            issues.append(f"{rule_id}: owner path missing")
            continue
        path = root / relative
        if not path.is_file():
            issues.append(f"{rule_id}: owner missing: {relative}")
            continue
        if kind == "python_test":
            symbol = owner.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                issues.append(f"{rule_id}: test symbol missing")
                continue
            test_issues = inspect_critical_test(path, symbol)
            issues.extend(f"{rule_id}: {issue}" for issue in test_issues)
            critical_tests.append(f"{relative}:{symbol}")
        elif kind not in {"script", "workflow"}:
            issues.append(f"{rule_id}: unsupported owner kind: {kind}")
    return issues, critical_tests


def _assigned_literal(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    raise KeyError(name)


def check_zero_baselines(root: Path) -> tuple[list[str], dict[str, int | None]]:
    issues: list[str] = []
    counts: dict[str, int | None] = {}
    for rule_id, (relative, constant_name) in ZERO_BASELINES.items():
        path = root / relative
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)
            value = _assigned_literal(tree, constant_name)
        except (OSError, SyntaxError, ValueError, KeyError) as exc:
            counts[rule_id] = None
            issues.append(f"{rule_id}: cannot read literal zero baseline {constant_name}: {exc}")
            continue
        try:
            count = len(value)
        except TypeError:
            count = value if isinstance(value, int) else None
        counts[rule_id] = count
        if count != 0:
            issues.append(f"{rule_id}: {constant_name} must remain literal zero, found {count}")
    return issues, counts


def check_full_discovery_source(source: str) -> list[str]:
    issues: list[str] = []
    command = re.search(
        r"py\s+-3\.13\s+-X\s+faulthandler\s+-m\s+unittest\s+discover\b[^\r\n]*",
        source,
        flags=re.IGNORECASE,
    )
    if command is None:
        return ["canonical full unittest discovery command missing"]
    line = command.group(0)
    if re.search(r"(?:^|\s)-s\s+tests(?:\s|$)", line) is None:
        issues.append("full discovery start directory is not tests")
    if re.search(r"(?:^|\s)-p\s+[\"']?test_\*\.py[\"']?(?:\s|$)", line) is None:
        issues.append("full discovery pattern is not test_*.py")
    return issues


def _workflow_step(source: str, name: str) -> str:
    match = re.search(
        rf"^\s+- name:\s*{re.escape(name)}\s*$([\s\S]*?)(?=^\s+- name:|\Z)",
        source,
        flags=re.MULTILINE,
    )
    return match.group(0) if match else ""


def _optional_step_issue(block: str, label: str, *, allow_continue: bool = False) -> list[str]:
    if not block:
        return [f"critical CI step missing: {label}"]
    issues: list[str] = []
    if re.search(r"^\s+if:\s*", block, flags=re.MULTILINE):
        issues.append(f"critical CI step became conditional: {label}")
    if not allow_continue and re.search(
        r"^\s+continue-on-error:\s*true\s*$", block, flags=re.IGNORECASE | re.MULTILINE
    ):
        issues.append(f"critical CI step allows failure: {label}")
    return issues


def check_ci_contracts(root: Path) -> list[str]:
    issues: list[str] = []
    app_path = root / ".github/workflows/app-ci.yml"
    guide_path = root / ".github/workflows/guide-ultime-v5-ui.yml"
    runner_path = root / "tools/run_guide_ultime_ci.ps1"
    gate_path = root / "tools/atlas_integrity.py"
    policy_path = root / "tools/atlas_integrity_policy.json"
    for path in (app_path, guide_path, runner_path, gate_path, policy_path):
        if not path.is_file():
            issues.append(f"CI owner missing: {path.relative_to(root).as_posix()}")
    if issues:
        return issues

    app = app_path.read_text(encoding="utf-8-sig")
    guide = guide_path.read_text(encoding="utf-8-sig")
    runner = runner_path.read_text(encoding="utf-8-sig")
    issues.extend(check_full_discovery_source(app))

    if "pull_request:" not in app or re.search(r"^\s*push:\s*$", app, re.MULTILINE) is None:
        issues.append("application CI automatic push/pull-request triggers missing")
    for required_path in ('"tools/**"', '"tests/**"', '".github/workflows/**"'):
        if required_path not in app:
            issues.append(f"app CI trigger scope missing {required_path}")
    for required_path in ('"launch.py"', '"main.py"', '"sitecustomize.py"', '"scripts/**"', '"config/**"'):
        if required_path not in app:
            issues.append(f"app CI critical path missing {required_path}")
    if ".\\tools\\run_guide_ultime_ci.ps1" not in app:
        issues.append("app CI no longer invokes the canonical Guide runner")
    if "-m tools.atlas_integrity fast" not in app:
        issues.append("app CI no longer invokes the Atlas FAST integrity gate")
    full_step = _workflow_step(app, "Run full application test suite")
    issues.extend(_optional_step_issue(full_step, "full application test suite", allow_continue=True))
    gate_step = _workflow_step(app, "Run Atlas integrity FAST gate")
    issues.extend(_optional_step_issue(gate_step, "Atlas FAST integrity gate"))
    verdict_step = _workflow_step(app, "Fail full validation when a full check failed")
    if '${{ steps.full_tests.outcome }}' not in verdict_step or "throw (\"Full validation failed:" not in verdict_step:
        issues.append("blocking final application CI verdict missing")
    if "if: ${{ always() }}" not in verdict_step:
        issues.append("final application CI verdict is not unconditional")
    required_gates = {
        "Run architecture guardrails": "Architecture",
        "Run canonical identity and persistence contracts": "Identity / Persistence",
        "Run startup and lazy-loading contracts": "Startup / Lazy",
        "Run Qt lifecycle and non-accumulation contracts": "Qt Lifecycle / Async",
        "Enforce deterministic resource budgets": "Resource Budgets",
        "Run Guide Quests Success Home golden flows": "Golden Flows",
        "Run representative lifecycle modules in one process": "Monolithic Lifecycle",
        "Run canonical Guide and data integrity runner": "Guide / Data Integrity",
    }
    for step_name, label in required_gates.items():
        block = _workflow_step(app, step_name)
        issues.extend(_optional_step_issue(block, label))
        if block and "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" not in block:
            issues.append(f"critical CI gate does not propagate failure: {label}")

    if "workflow_dispatch:" not in guide or re.search(r"^\s*(push|pull_request):", guide, re.MULTILINE):
        issues.append("detailed Guide workflow is not manual-only")
    if ".\\tools\\run_guide_ultime_ci.ps1" not in guide:
        issues.append("Guide workflow no longer invokes the canonical runner")
    guide_step = _workflow_step(guide, "Run Guide Ultime Windows CI")
    issues.extend(_optional_step_issue(guide_step, "Guide canonical runner"))

    for module in (
        "tools.audit_guide_ultime_manual_prerequisites",
        "tools.audit_guide_ultime_manual_final_coverage",
    ):
        position = runner.find(module)
        if position < 0:
            issues.append(f"blocking Guide audit missing from runner: {module}")
            continue
        if "--strict" not in runner[position : position + 500]:
            issues.append(f"blocking Guide audit lost --strict: {module}")
    if "$failed.Count -gt 0" not in runner or "exit 1" not in runner:
        issues.append("canonical Guide runner final failure verdict missing")
    try:
        policy = _read_json(policy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"integrity policy unavailable: {exc}")
    else:
        modes = policy.get("modes", {})
        fast = set(modes.get("FAST", [])) if isinstance(modes, dict) else set()
        full = set(modes.get("FULL", [])) if isinstance(modes, dict) else set()
        deep = set(modes.get("DEEP", [])) if isinstance(modes, dict) else set()
        required_fast = {"META_INTEGRITY", "SYNTAX", "GENERATED_FILES", "ARCHITECTURE", "IDENTITY"}
        if not required_fast.issubset(fast):
            issues.append("integrity FAST policy lost a mandatory validation group")
        if not {"FULL_SUITE", "DATA_INTEGRITY"}.issubset(full):
            issues.append("integrity FULL policy lost full discovery or Guide data validation")
        required_deep = {"RANDOM_ORDER", "FAULT_INJECTION", "TARGETED_MUTATION", "CRITICAL_COVERAGE", "MONOLITHIC_LIFECYCLE", "TIMING_PERFORMANCE", "FULL_SUITE"}
        if not required_deep.issubset(deep):
            issues.append("integrity DEEP policy lost a deep validation group")
        groups = policy.get("groups", {})
        data = groups.get("DATA_INTEGRITY", {}) if isinstance(groups, dict) else {}
        blocker_ids = data.get("blocker_ids", {}) if isinstance(data, dict) else {}
        if set(blocker_ids.values()) != {"GUIDE_PREREQUISITE_DATA", "GUIDE_FINAL_COVERAGE"}:
            issues.append("integrity policy lost stable Guide blocker IDs")
        known_blockers = set(data.get("known_blockers", [])) if isinstance(data, dict) else set()
        if known_blockers != {"GUIDE_PREREQUISITE_DATA", "GUIDE_FINAL_COVERAGE"}:
            issues.append("integrity policy lost the exact known Guide blocker inventory")
        if data.get("failure_semantics") != "BLOCKING":
            issues.append("known Guide blockers are no longer explicitly blocking")
        forbidden_keys = {"allowed_blockers", "allowed_debt", "tolerated_failures"}
        if forbidden_keys.intersection(data):
            issues.append("known Guide blockers must never be configured as allowed debt")
    return issues


def detect_sensitive_changes(paths: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for path in paths:
        if not path:
            continue
        relative = str(path).replace("\\", "/")
        if relative.startswith("./"):
            relative = relative[2:]
        normalized.add(relative)
    return sorted(
        path
        for path in normalized
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in SENSITIVE_PATTERNS)
    )


def classify_root_of_trust_changes(paths: Iterable[str]) -> dict[str, Any]:
    normalized = {
        str(path).replace("\\", "/")[2:]
        if str(path).replace("\\", "/").startswith("./")
        else str(path).replace("\\", "/")
        for path in paths
        if path
    }
    modified = sorted(normalized & ROOT_OF_TRUST_FILES)
    if len(modified) >= 2:
        risk = "CRITICAL"
    elif modified:
        risk = "HIGH"
    else:
        risk = "NONE"
    return {"modified": modified, "risk": risk}


def _git_paths(root: Path, base_ref: str) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    paths: set[str] = set()
    for index, command in enumerate(commands):
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0 and index == 0:
            continue
        paths.update(line.strip() for line in completed.stdout.splitlines() if line.strip())
    return sorted(paths)


def verify_repository(
    root: Path = ROOT,
    inventory_path: Path = DEFAULT_INVENTORY,
    *,
    changed_paths: Iterable[str] | None = None,
    base_ref: str = "@{upstream}",
) -> dict[str, Any]:
    inventory_file = inventory_path if inventory_path.is_absolute() else root / inventory_path
    inventory_issues: list[str] = []
    critical_tests: list[str] = []
    try:
        payload = _read_json(inventory_file)
        inventory_issues, critical_tests = validate_inventory(payload, root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        inventory_issues.append(f"critical inventory unavailable: {exc}")

    zero_issues, zero_counts = check_zero_baselines(root)
    ci_issues = check_ci_contracts(root)
    paths = list(changed_paths) if changed_paths is not None else _git_paths(root, base_ref)
    sensitive = detect_sensitive_changes(paths)
    root_of_trust = classify_root_of_trust_changes(paths)

    skip_issues = [issue for issue in inventory_issues if "skip/xfail" in issue]
    owner_issues = [issue for issue in inventory_issues if issue not in skip_issues]
    rules = [
        {"name": "critical_inventory", "status": "PASS" if not owner_issues else "BLOCKED", "issues": owner_issues},
        {"name": "critical_skip_xfail", "status": "PASS" if not skip_issues else "BLOCKED", "issues": skip_issues},
        {"name": "zero_debt_baselines", "status": "PASS" if not zero_issues else "BLOCKED", "issues": zero_issues},
        {"name": "full_discovery_and_ci", "status": "PASS" if not ci_issues else "BLOCKED", "issues": ci_issues},
    ]
    all_issues = [*owner_issues, *skip_issues, *zero_issues, *ci_issues]
    return {
        "verdict": "PASS" if not all_issues else "BLOCKED",
        "rules": rules,
        "critical_test_count": len(critical_tests),
        "protections_missing": all_issues,
        "skips_xfails": skip_issues,
        "zero_debt": zero_counts,
        "sensitive_files": sensitive,
        "sensitive_change_detected": bool(sensitive),
        "root_of_trust": root_of_trust,
        "root_of_trust_modified": bool(root_of_trust["modified"]),
    }


def _print_human(report: dict[str, Any]) -> None:
    print("ATLAS META INTEGRITY")
    print()
    labels = {
        "critical_inventory": "Critical inventory",
        "critical_skip_xfail": "Critical skip/xfail",
        "zero_debt_baselines": "Zero debt baselines",
        "full_discovery_and_ci": "Full discovery and CI",
    }
    for rule in report["rules"]:
        print(f"{labels[rule['name']]:28} {rule['status']}")
        for issue in rule["issues"]:
            print(f"  - {issue}")
    sensitive_status = "CHANGED" if report["sensitive_change_detected"] else "UNCHANGED"
    print(f"{'Sensitive files':28} {sensitive_status}")
    for path in report["sensitive_files"]:
        print(f"  - {path}")
    if report["root_of_trust_modified"]:
        print()
        print("ROOT OF TRUST MODIFIED")
        print("modified:")
        for path in report["root_of_trust"]["modified"]:
            print(f"  - {path}")
        print(f"risk: {report['root_of_trust']['risk']}")
    print()
    print(f"VERDICT: {report['verdict']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Dofus Atlas critical guardrail integrity.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--base-ref", default="@{upstream}")
    parser.add_argument("--json", action="store_true", help="Write the report as JSON to stdout.")
    args = parser.parse_args(argv)
    report = verify_repository(args.root.resolve(), args.inventory, base_ref=args.base_ref)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
