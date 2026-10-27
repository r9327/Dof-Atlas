from __future__ import annotations

"""Single stdlib-only impact decision for NEW Doctor UI campaigns.

Reuses AI Context path normalization/test routing and ci_scope_gate's verified
base...HEAD diff parser. It never changes FAST, FULL or certification policy.
Explicit UI consumers include Qt signals/lazy wiring that import-only maps miss.
Unknown paths cannot establish absence of UI impact.
"""

import argparse
import ast
import json
import subprocess
from pathlib import Path

from tools import ai_context
from tools.ci_scope_gate import changed_paths
from tools.atlas_doctor_lib.doctor_ui import (
    DEFAULT_SCENARIOS, SCENARIOS, git_value, required_assertions, run_ui, write_json,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY_VERSION = 1
BOTH = ("guides-success", "guides-lanyel")
ALL_GUIDES = DEFAULT_SCENARIOS
# Maintained runtime edges: imports alone do not describe signal destinations.
UI_CONSUMERS = {
    "app/modules/encyclopedia/views/shared_manual_guide_view.py": ALL_GUIDES,
    "app/modules/encyclopedia/views/guide_ultime_manual_view.py": ALL_GUIDES,
    "app/modules/encyclopedia/views/manual_route_guides_view.py": ALL_GUIDES,
    "app/modules/encyclopedia/views/deferred_achievement_guides_view.py": ALL_GUIDES,
    "app/modules/encyclopedia/views/guides_view.py": ALL_GUIDES,
    "app/modules/encyclopedia/views/encyclopedia_page.py": (*ALL_GUIDES, "achievement-detail"),
    "app/modules/encyclopedia/views/achievements_view.py": ("achievement-detail",),
    "app/modules/encyclopedia/widgets/achievement_detail_widget.py": ("achievement-detail",),
    "app/modules/encyclopedia/providers/achievement_provider.py": (*ALL_GUIDES, "achievement-detail"),
    "app/modules/encyclopedia/services/link_service.py": ("guide-quests",),
    "app/pages/quests_page.py": ("guide-quests",),
    "app/pages/lazy_quests_page.py": ("guide-quests",),
    "app/modules/encyclopedia/widgets/quest_detail_view.py": ("guide-quests",),
    "app/ui/theme.py": ALL_GUIDES,
    "app/ui/components.py": ALL_GUIDES,
}
INDEPENDENT_TOOLS = frozenset({
    "tools/atlas_json_raw.py", "tools/check_generated_files.py",
    "tools/agent_task_profiles.py",
    "tools/atlas_meta_integrity.py", "tools/ci_main_phase_evidence.py",
    "tools/ci_verified_pr_full.py",
    # Certification router has no product-UI consumer by itself; its source is
    # still AST-checked for new app/Qt/dynamic imports on every edited SHA.
    "tools/ci_domain_certification.py",
    "tools/ci_required_certification.py",
    # Source-only Doctor diagnostics, checked for Qt/app or dynamic imports.
    "tools/atlas_doctor_lib/capability_matrix.py",
    "tools/atlas_doctor_lib/capability_evidence.py",
    "tools/atlas_doctor_lib/agent_protocol.py",
})
VALIDATOR_PATHS = frozenset({
    "tools/atlas_doctor.py", "tools/atlas_doctor_lib/ci_orchestrator.py",
    "tools/atlas_doctor_lib/ci_routes.json", "tools/atlas_integrity_policy.json",
    "tools/atlas_doctor_lib/ci_tooling_scope.py",
})


def _ci_workflow(path: str) -> bool:
    # Workflow definitions change the validation environment, not product UI.
    # They still select a real validator smoke; Doctor owns suite selection.
    return path.startswith('.github/workflows/') and path.endswith(('.yml', '.yaml'))


def _module(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")


def test_app_import_targets(root: Path, path: str) -> tuple[set[str], bool, bool]:
    """Resolve direct app imports in a changed test to real source modules.

    The reverse production graph excludes tests by design. Without this bridge,
    a test importing a Guide widget is falsely reported as an unmapped UI
    dependency. Unknown/dynamic imports still force REVIEW_REQUIRED.
    """
    tree = ast.parse((root / path).read_text(encoding="utf-8-sig"), filename=path)
    sources: set[str] = set()
    runtime_import = False
    unresolved = False
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                unresolved = True  # Relative test imports may hide app consumers.
            modules = [base] + [base + "." + a.name for a in node.names] if base else []
        elif isinstance(node, ast.Call) and (
            isinstance(node.func, ast.Name) and node.func.id == "__import__"
            or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
        ):
            unresolved = True
        app_candidates = [name for name in modules if name == "app" or name.startswith("app.")]
        if any(name.split(".")[0] in {"app", "PySide6", "shiboken6"} for name in modules):
            runtime_import = True
        for name in app_candidates:
            relative = name.replace(".", "/")
            candidates = (relative + ".py", relative + "/__init__.py")
            resolved = False
            for candidate in candidates:
                target = root / candidate
                if target.is_file() and not target.is_symlink():
                    sources.add(candidate)
                    resolved = True
            # A bare symbol in 'from app.module import Symbol' need not be a
            # module; the base import must resolve, not each exported symbol.
            if not resolved and name in [a.name for n in ast.walk(tree)
                                         if isinstance(n, ast.Import) for a in n.names]:
                unresolved = True
        # Missing base modules in ImportFrom are checked separately below.
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            parent = node.module.replace(".", "/")
            if not any((root / (parent + suffix)).is_file()
                       for suffix in (".py", "/__init__.py")):
                unresolved = True
    return sources, runtime_import, unresolved


def dependency_map(root: Path) -> tuple[dict[str, set[str]], list[str]]:
    """AST-only reverse imports; no application execution or Qt installation."""
    files = [p for base in ("app", "tools") for p in (root / base).rglob("*.py")]
    modules = {_module(p.relative_to(root).as_posix()): p.relative_to(root).as_posix() for p in files}
    reverse: dict[str, set[str]] = {}
    errors = []
    for module, path in modules.items():
        try:
            tree = ast.parse((root / path).read_text(encoding="utf-8-sig"))
        except (SyntaxError, OSError, UnicodeError):
            errors.append(path)
            continue
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                parent = module.split(".")[:-1] if not path.endswith("/__init__.py") else module.split(".")
                prefix = ".".join(parent[:len(parent) - node.level + 1]) if node.level else ""
                source = ".".join(part for part in (prefix, node.module) if part)
                imports = [source] + [source + "." + alias.name for alias in node.names]
            for imported in imports:
                if imported in modules:
                    reverse.setdefault(modules[imported], set()).add(path)
    return reverse, errors


def classify_ui(root: Path, paths, *, candidate_sha: str, base_sha: str,
                deleted=(), forced=(), diff_valid=True) -> dict:
    changed = sorted({ai_context.normalize_path(p) for p in paths})
    selected: set[str] = set()
    reasons: dict[str, list[str]] = {s: [] for s in SCENARIOS}
    impacted = set()
    uncertainty = []
    if not diff_valid or not base_sha or not candidate_sha:
        uncertainty.append("UNVERIFIED_DIFF_OR_SHA")
    removed_runtime = [path for path in deleted if not _ci_workflow(path)]
    if removed_runtime:
        uncertainty.append("REMOVED_RENAMED_OR_TYPE_CHANGED: " + ", ".join(sorted(removed_runtime)))
    if len(changed) > 80:
        uncertainty.append("BROAD_CHANGE_REQUIRES_REVIEW")
    reverse = None
    parse_errors = []

    def include(scenarios, reason, path):
        selected.update(scenarios)
        impacted.add(path)
        for scenario in scenarios:
            reasons[scenario].append(reason)

    for path in changed:
        if not path or path.startswith(("/", "../")) or "/../" in path:
            uncertainty.append("INVALID_PATH: " + path)
        elif path.endswith(".md") or path == ".ai/context_index.json":
            continue
        elif path in ("tools/atlas_doctor_lib/doctor_ui_qt.py",
                       "tools/atlas_doctor_lib/doctor_ui.py",
                       "tests/test_doctor_ui_qt.py", "tests/test_doctor_ui.py"):
            # Changes to shared UI assertions must exercise both production
            # Guides as well as the smoke and Success journeys; otherwise
            # manual/combat persistence could silently pass via smoke alone.
            include(("guides-success", "guides-lanyel", "validator-smoke", "achievement-detail"),
                    "Shared Doctor Qt validator changed: " + path, path)
        elif path.startswith(("tools/atlas_doctor_lib/doctor_ui", "tools/atlas_doctor_lib/ui_raster_oracle", "tools/atlas_doctor_lib/ui_contrast_oracle", "tests/test_doctor_ui")):
            include(("validator-smoke", "achievement-detail"),
                    "Validator and real Success journey changed: " + path, path)
        elif _ci_workflow(path) or path in VALIDATOR_PATHS:
            include(("validator-smoke",), "Validator/selection contract changed: " + path, path)
        elif path in UI_CONSUMERS:
            include(UI_CONSUMERS[path], "Explicit Qt runtime consumer: " + path, path)
        elif path.startswith("data/routes/guide_ultime_manual/"):
            include(("guides-success", "guide-quests"), "Canonical authored Guide input: " + path, path)
        elif path == "data/encyclopedia/guides/dofus_sylvestre.json":
            include(("guides-lanyel", "guide-quests"), "Canonical Lanyel input: " + path, path)
        elif path in INDEPENDENT_TOOLS:
            # Recheck the known independent owner instead of letting its name
            # authorize a newly introduced Qt/application import.
            try:
                tree = ast.parse((root / path).read_text(encoding="utf-8-sig"))
                imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
                imports.extend(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
                dynamic = any(isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name) and node.func.id == "__import__"
                    or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
                ) for node in ast.walk(tree))
                if dynamic or any(name == "app" or name.startswith(("PySide", "app.")) for name in imports):
                    uncertainty.append("INDEPENDENT_TOOL_CHANGED_BOUNDARY: " + path)
            except (OSError, SyntaxError, UnicodeError):
                uncertainty.append("UNVERIFIED_INDEPENDENT_TOOL: " + path)
        elif path.endswith(".py"):
            if reverse is None:
                reverse, parse_errors = dependency_map(root)
            frontier = [path]
            test_runtime = False
            if path.startswith("tests/test_"):
                try:
                    imported_sources, test_runtime, unresolved = test_app_import_targets(root, path)
                    frontier.extend(sorted(imported_sources))
                    if unresolved:
                        uncertainty.append("UNVERIFIED_TEST_IMPORT: " + path)
                except (OSError, SyntaxError, UnicodeError, ValueError):
                    test_runtime = True
                    uncertainty.append("UNREADABLE_TEST_IMPORTS: " + path)
            visited = set()
            consumers = set()
            while frontier and len(visited) < 4000:
                current = frontier.pop()
                if current in visited:
                    continue
                visited.add(current)
                if current in UI_CONSUMERS:
                    consumers.add(current)
                frontier.extend(reverse.get(current, set()) - visited)
            for consumer in sorted(consumers):
                include(UI_CONSUMERS[consumer], f"AST import dependency: {path} → {consumer}", consumer)
            if not consumers:
                # Only a verified non-runtime test is independent of UI. An
                # unreadable test or unmatched app consumer remains REVIEW_REQUIRED.
                if path.startswith("tests/test_") and not test_runtime and not any(
                    item.endswith(": " + path) for item in uncertainty
                ):
                    continue
                uncertainty.append("UNMAPPED_DEPENDENCY: " + path)
        else:
            uncertainty.append("UNCLASSIFIED_PATH: " + path)
    if parse_errors:
        uncertainty.append("INCOMPLETE_IMPORT_MAP: " + ", ".join(parse_errors[:10]))
    for scenario in forced:
        if scenario not in SCENARIOS:
            uncertainty.append("UNKNOWN_FORCED_SCENARIO: " + scenario)
        else:
            include((scenario,), "Explicit bounded workflow_dispatch selection", "manual")
    return {
        "schema_version": 1, "policy_version": POLICY_VERSION,
        "candidate_sha": candidate_sha, "base_sha": base_sha,
        "changed_paths": changed, "deleted_paths": sorted(deleted),
        "impacted_ui_paths": sorted(impacted),
        "selected_scenarios": sorted(selected),
        "excluded_scenarios": sorted(set(SCENARIOS) - selected),
        "reason_per_scenario": {s: reasons[s] or ["No mapped changed consumer for this scenario"] for s in SCENARIOS},
        "recommended_tests": list(ai_context.recommended_tests(root, changed)),
        "status": "REVIEW_REQUIRED" if uncertainty else "UI_REQUIRED" if selected else "NOT_APPLICABLE",
        "uncertainty": uncertainty, "forced_scenarios": list(forced),
        "tests_executed": False, "full_suite_waived": False,
        "reuse_policy": "One campaign per PR head; reuse requires the same SHA, clean tree, selected assertions and hashed artifacts",
    }



# Cross-PR regression watch: evidence IDs for four distinct product journeys.
# These are NOT synonyms for validator-smoke or a successful Guide-only run.
# Achievement-detail assertions are owned by Doctor UI PR #216; while absent,
# every corresponding control stays explicitly NOT_COVERED.
REGRESSION_REQUIREMENTS = {
    "achievement-click": ("achievement-detail/click-opens-detail",),
    "guide-to-quests": (
        "guide-quests/guide_complet-quest-0",
        "guide-quests/dofus_sylvestre-quest-0",
    ),
    "achievement-first-open": ("achievement-detail/first-open-lazy",),
    "render-and-capture": (
        "guides-success/geometry-1-1200",
        "guides-success/geometry-1-960",
        "guides-lanyel/geometry-1-1200",
        "guides-lanyel/geometry-1-960",
        "achievement-detail/geometry-1200",
        "achievement-detail/geometry-960",
    ),
}



def _valid_png_capture(path: Path) -> bool:
    """Verify chunks and bounded RGB/RGBA pixels from non-interlaced Qt PNGs."""
    import zlib

    try:
        if path.stat().st_size > 32_000_000:
            return False
        payload = path.read_bytes()
    except OSError:
        return False
    if not payload.startswith(bytes.fromhex("89504e470d0a1a0a")):
        return False
    offset = 8
    header_seen = image_seen = False
    compressed = bytearray()
    stride = expected_bytes = 0
    while offset + 12 <= len(payload):
        size = int.from_bytes(payload[offset:offset + 4], "big")
        end = offset + 12 + size
        if size > 32_000_000 or end > len(payload):
            return False
        kind = payload[offset + 4:offset + 8]
        data = payload[offset + 8:offset + 8 + size]
        actual_crc = int.from_bytes(payload[end - 4:end], "big")
        if zlib.crc32(kind + data) & 0xFFFFFFFF != actual_crc:
            return False
        if not header_seen:
            if kind != b"IHDR" or size != 13:
                return False
            width, height = (int.from_bytes(data[:4], "big"),
                             int.from_bytes(data[4:8], "big"))
            if not (0 < width <= 8192 and 0 < height <= 8192):
                return False
            # Qt's captures are 8-bit RGB/RGBA. Unsupported encodings cannot
            # establish a usable screenshot without a matching pixel decoder.
            depth, color, compression, filtering, interlace = data[8:]
            if depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                return False
            stride = 1 + width * (3 if color == 2 else 4)
            expected_bytes = height * stride
            if expected_bytes > 32_000_000:
                return False
            header_seen = True
        elif kind == b"IHDR":
            return False
        if kind == b"IDAT":
            image_seen = True
            compressed.extend(data)
        if kind == b"IEND":
            if not (image_seen and size == 0 and end == len(payload)):
                return False
            # CRC and SHA integrity do not prove that IDAT contains pixels.
            # Limit output before decompression to reject compressed bombs.
            try:
                decoder = zlib.decompressobj()
                pixels = decoder.decompress(compressed, expected_bytes + 1)
            except zlib.error:
                return False
            return (decoder.eof and not decoder.unused_data
                    and not decoder.unconsumed_tail and len(pixels) == expected_bytes
                    and all(pixels[row] <= 4 for row in range(0, expected_bytes, stride)))
        offset = end
    return False


def _regression_assertions(folders: list[Path], sha: str) -> tuple[dict, list[str]]:
    """Read only hash-verified real sessions for an exact SHA, never bare JSON."""
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for folder in folders:
        try:
            report = read_evidence(folder, sha)
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append("INVALID_SESSION: " + str(exc))
            continue
        if (report.get("candidate_sha") != sha or report.get("dirty") is not False
                or report.get("status") not in {"PASS", "FAIL", "BLOCKED", "REVIEW"}
                or report.get("tests_executed") is not True):
            errors.append("UNTRUSTED_OR_UNEXECUTED_SESSION")
            continue
        assertions = report.get("assertions")
        required = report.get("required_assertions")
        if not isinstance(assertions, list) or not isinstance(required, list):
            errors.append("MISSING_REQUIRED_ASSERTION_INVENTORY")
            continue
        from tools.atlas_doctor_lib.doctor_ui import verdict
        computed = verdict(assertions, required)
        if report["status"] == "PASS" and computed != "PASS":
            errors.append("INCONSISTENT_PASS_REPORT")
            continue
        artifacts = manifest.get("artifacts", {})
        for row in assertions:
            if not isinstance(row, dict) or not isinstance(row.get("assertion_id"), str):
                errors.append("INVALID_ASSERTION")
                continue
            ident = row["assertion_id"]
            if ident in rows and ident != "session/qt-exceptions":
                errors.append("DUPLICATE_ASSERTION: " + ident)
                continue
            if ident == "session/qt-exceptions" and ident in rows:
                if row.get("assertion_status") != "PASS":
                    errors.append("QT_EXCEPTION_IN_SESSION")
                continue
            captures = row.get("evidence_ids")
            linked = [name for name in captures if isinstance(name, str)
                      and name.endswith(".png") and name in artifacts] if isinstance(captures, list) else []
            if not linked:
                # A positive control must have a linked, hash-verified PNG,
                # not merely an unrelated screenshot in the session manifest.
                errors.append("ASSERTION_MISSING_CAPTURE: " + ident)
            for name in linked:
                # A hash-valid but corrupted/fabricated screenshot never grants PASS.
                if not _valid_png_capture(folder / name):
                    errors.append("INVALID_SCREENSHOT_PNG: " + name)
            rows[ident] = {**row, "_session_status": report["status"]}
    return rows, errors


def watch_ui_regressions(*, baseline_sha: str, candidate_sha: str,
                         baseline_sessions: list[Path],
                         candidate_sessions: list[Path]) -> dict:
    """Compare four observable UI contracts without claiming release certification.

    PASS on a smoke test cannot cover a missing real achievement journey.
    A missing baseline/candidate produces NOT_COVERED, not an invented delta.
    """
    errors = []
    if (len(baseline_sha) != 40 or len(candidate_sha) != 40
            or not all(c in "0123456789abcdef" for c in (baseline_sha + candidate_sha).lower())
            or baseline_sha == candidate_sha):
        errors.append("INVALID_OR_IDENTICAL_SHAS")
    if len(baseline_sessions) > 8 or len(candidate_sessions) > 8:
        errors.append("SESSION_BUDGET_EXCEEDED")
    before, before_errors = _regression_assertions(baseline_sessions[:8], baseline_sha) if not errors else ({}, [])
    after, after_errors = _regression_assertions(candidate_sessions[:8], candidate_sha) if not errors else ({}, [])
    errors.extend("baseline: " + e for e in before_errors)
    errors.extend("candidate: " + e for e in after_errors)
    controls = {}
    for label, required in REGRESSION_REQUIREMENTS.items():
        missing_before = [key for key in required if key not in before]
        missing_after = [key for key in required if key not in after]
        if missing_before or missing_after:
            status = "NOT_COVERED"
        elif any(after[key].get("assertion_status") != "PASS" for key in required):
            status = "REGRESSION_REVIEW" if all(
                before[key].get("assertion_status") == "PASS"
                and before[key].get("_session_status") == "PASS"
                for key in required
            ) else "UNVERIFIED"
        elif all(before[key].get("assertion_status") == "PASS"
                 and before[key].get("_session_status") == "PASS" for key in required):
            status = "NO_REGRESSION_OBSERVED" if all(
                after[key].get("_session_status") == "PASS" for key in required
            ) else "UNVERIFIED"
        else:
            status = "UNVERIFIED"
        controls[label] = {
            "status": status, "required_assertions": list(required),
            "baseline_missing": missing_before, "candidate_missing": missing_after,
            "baseline_verdicts": {key: before[key].get("assertion_status") for key in required if key in before},
            "candidate_verdicts": {key: after[key].get("assertion_status") for key in required if key in after},
        }
    result_status = ("BLOCKED" if errors else
                     "REGRESSION_REVIEW" if any(c["status"] == "REGRESSION_REVIEW" for c in controls.values()) else
                     "NO_REGRESSION_OBSERVED" if all(c["status"] == "NO_REGRESSION_OBSERVED" for c in controls.values()) else
                     "NOT_COVERED")
    return {
        "schema_version": 1, "kind": "doctor_ui_regression_watch",
        "status": result_status, "baseline_sha": baseline_sha,
        "candidate_sha": candidate_sha, "controls": controls,
        "errors": errors, "tests_executed": False,
        "phase_certified": False, "release_certified": False,
        "limits": ("Only exact-SHA, hash-verified UI session assertions and linked PNGs "
                   "are compared. This does not execute UI, prove semantic correctness "
                   "or certify an installed Windows application."),
    }


def exhaustive_review_plan(report: dict) -> dict:
    """Run every registered UI scenario when impact cannot safely narrow the set.

    This never expands the evidence claim beyond the known scenario registry;
    canonical FULL remains independently required for unknown product impact.
    """
    if report['status'] != 'REVIEW_REQUIRED':
        return report
    result = dict(report)
    result.update(status='UI_REQUIRED', selected_scenarios=sorted(SCENARIOS),
                  excluded_scenarios=[], exhaustive_on_review=True)
    result['reason_per_scenario'] = {
        scenario: ['Exhaustive registered UI campaign: impact uncertainty']
        for scenario in SCENARIOS
    }
    return result


def plan_ui(root: Path, base: str, candidate: str, forced=(), *, exhaustive_on_review=False) -> dict:
    actual = git_value(root, "rev-parse", "HEAD")
    valid = actual == candidate and not git_value(root, "status", "--porcelain")
    try:
        base_sha = git_value(root, "rev-parse", "--verify", base + "^{commit}")
        paths, deleted = changed_paths(root, base_sha)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        base_sha, paths, deleted, valid = "", [], [], False
    report = classify_ui(root, paths, candidate_sha=candidate, base_sha=base_sha,
                         deleted=deleted, forced=forced, diff_valid=valid)
    return exhaustive_review_plan(report) if valid and exhaustive_on_review else report


def campaign_verdict(plan: dict, reports: list[dict], candidate: str) -> dict:
    """Independent fail-closed result; a skipped required Windows job cannot pass."""
    result = {"schema_version": 1, "candidate_sha": candidate,
              "selected_scenarios": plan.get("selected_scenarios", []),
              "tests_executed": False, "status": "BLOCKED", "errors": [],
              "phase_certified": False, "full_suite_waived": False}
    errors = result["errors"]
    if plan.get("candidate_sha") != candidate or plan.get("policy_version") != POLICY_VERSION:
        errors.append("UNTRUSTED_PLAN")
    selected = plan.get("selected_scenarios", [])
    if len(set(selected)) != len(selected) or set(selected) - set(SCENARIOS):
        errors.append("INVALID_SELECTION")
    if plan.get("status") == "NOT_APPLICABLE" and not selected and not reports and not errors:
        result["status"] = "NOT_APPLICABLE"
        return result
    if plan.get("status") != "UI_REQUIRED" or not selected:
        errors.append("UI_IMPACT_REQUIRES_REVIEW")
    executed = []
    for report in reports:
        if (report.get("candidate_sha") != candidate or report.get("dirty") is not False
                or report.get("status") != "PASS" or report.get("tests_executed") is not True):
            errors.append("INVALID_OR_FAILED_UI_EVIDENCE")
        assertions = report.get("assertions", [])
        from tools.atlas_doctor_lib.doctor_ui import verdict
        expected = required_assertions(report.get("selected_scenarios", []), report.get("repeats", 2))
        if (set(expected) != set(report.get("required_assertions", []))
                or verdict(assertions, expected) != "PASS"):
            errors.append("MISSING_OR_FAILED_REQUIRED_ASSERTIONS")
        for scenario in report.get("selected_scenarios", []):
            if not any(a.get("scenario_id") == scenario and a.get("assertion_status") == "PASS" for a in assertions):
                errors.append("SCENARIO_NOT_EXECUTED: " + scenario)
            executed.append(scenario)
    if sorted(executed) != sorted(selected):
        errors.append("MISSING_OR_DUPLICATE_SCENARIOS")
    if not errors:
        result.update(status="PASS", tests_executed=True)
    return result


def read_evidence(folder: Path, candidate: str) -> dict:
    import hashlib

    report = json.loads((folder / "ui_verdict.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("candidate_sha") != candidate or manifest.get("dirty") is not False:
        raise ValueError("Untrusted UI manifest")
    artifacts = manifest.get("artifacts", {})
    required = set(report.get("required_evidence", [])) | {"ui_verdict.json", "actions.json", "request.json", "worker.log"}
    if not required <= artifacts.keys() or not any(name.endswith(".png") for name in required):
        raise ValueError("Missing real capture/session evidence")
    for name, digest in artifacts.items():
        if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Missing or modified UI artifact: " + name)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "verdict", "regression-watch"))
    parser.add_argument("--base-ref")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--plan", type=Path, default=ROOT / ".ai/runtime/atlas_doctor/ui_ci_selection.json")
    parser.add_argument("--force", choices=SCENARIOS, action="append", default=[])
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--exhaustive-on-review", action="store_true", help="Run all registered scenarios for uncertain verified diffs; never waive FULL")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / ".ai/runtime/atlas_doctor/ui")
    parser.add_argument("--baseline-sha", default="")
    parser.add_argument("--baseline-session", type=Path, action="append", default=[])
    parser.add_argument("--candidate-session", type=Path, action="append", default=[])
    parser.add_argument("--watch-output", type=Path, default=ROOT / "artifacts/doctor_ui/regression_watch.json")
    args = parser.parse_args(argv)
    if args.action == "regression-watch":
        report = watch_ui_regressions(
            baseline_sha=args.baseline_sha, candidate_sha=args.candidate_sha,
            baseline_sessions=args.baseline_session,
            candidate_sessions=args.candidate_session,
        )
        write_json(args.watch_output, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["status"] == "NO_REGRESSION_OBSERVED" else 2
    if args.action == "plan":
        if not args.base_ref:
            parser.error("plan requires --base-ref")
        report = plan_ui(ROOT, args.base_ref, args.candidate_sha, args.force, exhaustive_on_review=args.exhaustive_on_review)
        write_json(args.plan, report)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"run_ui={str(bool(report['selected_scenarios'])).lower()}\n")
                stream.write(f"ui_status={report['status']}\n")
    else:
        if args.action == "run":
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            checked = plan_ui(ROOT, plan["base_sha"], args.candidate_sha, plan.get("forced_scenarios", []), exhaustive_on_review=plan.get("exhaustive_on_review", False))
            if checked != plan or plan["status"] != "UI_REQUIRED":
                raise ValueError("UI plan cannot be reproduced at the clean exact candidate")
            report = run_ui(ROOT, scenarios=plan["selected_scenarios"], mode="all")
        else:
            try:
                plan = json.loads(args.plan.read_text(encoding="utf-8"))
                if not isinstance(plan, dict):
                    raise ValueError("UI selection must be a JSON object")
                reports = [read_evidence(p.parent, args.candidate_sha)
                           for p in args.evidence_root.glob("*/ui_verdict.json")]
                report = campaign_verdict(plan, reports, args.candidate_sha)
            except (OSError, ValueError, KeyError) as exc:
                report = {"schema_version": 1, "status": "BLOCKED", "error": str(exc),
                          "candidate_sha": args.candidate_sha, "tests_executed": False,
                          "phase_certified": False, "full_suite_waived": False}
            write_json(args.plan.with_name("ui_campaign_verdict.json"), report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] in {"PASS", "NOT_APPLICABLE", "UI_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
