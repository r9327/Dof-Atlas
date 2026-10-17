"""Bounded CI-only validation, distinct from application/Phase certification."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import unittest

# Every supported owner is covered by this stdlib contract suite. Unknown tools,
# runtime files, dependencies, rulesets and certification executors stay outside.
TESTS = (
    'doctor_ci_orchestrator', 'phase_adaptive_gate', 'main_phase_evidence',
    'ci_verified_pr_full', 'ci_required_certification', 'meta_integrity',
    'ci_runner_guardrails', 'public_pr_ci_guardrails', 'security_hardening_guardrails',
    'phase_certification_guardrails', 'doctor_certification_policy',
    'graphify_workflow_budget', 'ci_scope_gate', 'doctor_ui_ci', 'atlas_integrity',
    'repository_git_hooks', 'atlas_doctor_graphify', 'doctor_certification',
    'doctor_certification_shadow', 'phase_certification_performance_schema',
    'doctor_scenario_runner', 'memory_policy_contract', 'generated_file_guardrails',
    'phase8_memory_policy_advisory', 'phase8_deep_comparison',
    'phase8_preload_benchmark_contract', 'doctor_github_provenance',
    'phase8_memory_benchmark_contract', 'doctor_policy_authority', 'ai_context', 'doctor_ui',
)
OWNERS = frozenset({
    'tools/atlas_doctor.py', 'tools/atlas_doctor_lib/ci_orchestrator.py',
    'tools/atlas_doctor_lib/ci_tooling_scope.py', 'tools/atlas_doctor_lib/ci_routes.json',
    'tools/atlas_doctor_lib/doctor_ui_ci.py', 'tools/atlas_meta_integrity.py',
    'tools/ci_main_phase_evidence.py', 'tools/ci_verified_pr_full.py',
    'tools/ci_required_certification.py',
    'tests/test_ai_context.py',
    *(f'tests/test_{name}.py' for name in TESTS),
})
RETIRED_WORKFLOWS = frozenset({'.github/workflows/public-pr-ci.yml'})

# Real Doctor UI detector files are tooling only when their import boundary
# is verified AND the Windows detector journeys are selected separately.
# Changing application views/providers is never eligible.
QT_DETECTOR_PATHS = frozenset({
    'tools/atlas_doctor_lib/doctor_ui.py',
    'tools/atlas_doctor_lib/doctor_ui_qt.py',
    'tools/atlas_doctor_lib/ui_raster_oracle.py',
    'tools/atlas_doctor_lib/ui_contrast_oracle.py',
    'tests/test_doctor_ui_qt.py',
})


def _qt_detector_boundary(root: Path | None, path: str) -> bool:
    if root is None:
        return False
    root = root.resolve()
    source = root / path
    try:
        if (source.is_symlink() or not source.is_file()
                or not source.resolve().is_relative_to(root)
                or source.stat().st_size > 512 * 1024):
            return False
        ast_tree = ast.parse(source.read_text(encoding='utf-8-sig'), filename=path)
    except (OSError, SyntaxError, UnicodeError, ValueError):
        return False
    if path.startswith('tests/'):
        return True  # Real Qt test runs on Windows; not imported by stdlib.
    if path.endswith(('/ui_raster_oracle.py', '/ui_contrast_oracle.py')):
        # The screenshot raster analyzer must remain completely stdlib-only.
        forbidden = ('app', 'PySide6', 'shiboken6')
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.Import) and any(
                alias.name.split('.')[0] in forbidden for alias in node.names
            ):
                return False
            if isinstance(node, ast.ImportFrom) and (
                (node.module or '').split('.')[0] in forbidden
            ):
                return False
    # Imports of PySide/app are allowed inside *executed isolated functions*.
    # At module import time the Doctor orchestrator must remain stdlib-only.
    top_level = []
    for node in ast_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        top_level.extend(ast.walk(node))
    for node in top_level:
        if isinstance(node, ast.Import):
            if any(alias.name.startswith(('app.', 'PySide6', 'shiboken6'))
                   or alias.name in {'app', 'PySide6', 'shiboken6'} for alias in node.names):
                return False
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ''
            if name.startswith(('app.', 'PySide6', 'shiboken6')) or name in {'app', 'PySide6', 'shiboken6'}:
                return False
        elif isinstance(node, ast.Call):
            func = node.func
            if ((isinstance(func, ast.Name) and func.id == '__import__')
                    or (isinstance(func, ast.Attribute) and func.attr == 'import_module')):
                return False
    return True



def eligible(paths, *, deleted=(), root: Path | None = None, base_sha='') -> bool:
    registry = json.loads(Path(__file__).with_name('ci_routes.json').read_text())
    workflows = {f'.github/workflows/{name}.yml' for name in registry}
    workflows |= {'.github/workflows/phase-certification.yml',
                  '.github/workflows/scoped-pr-ci.yml'} | RETIRED_WORKFLOWS
    if not paths or set(deleted) - RETIRED_WORKFLOWS:
        return False
    has_tooling = False
    for path in paths:
        if path in {'.ai/context_index.json', 'README.md', 'PHASE_CERTIFICATION.md',
                    'DOCTOR_ADAPTIVE_CERTIFICATION.md'} or (
                path.startswith('docs/') and path.endswith('.md') and '..' not in path.split('/')):
            continue
        if path == 'tools/atlas_integrity_policy.json':
            # Wiring a new tested CI module is not a change of the FULL policy.
            # Any other JSON change, including a removed mandatory test, falls back.
            if root is None or not base_sha:
                return False
            try:
                old = json.loads(subprocess.check_output(
                    ['git', 'show', f'{base_sha}:{path}'], cwd=root, text=True, timeout=20))
                new = json.loads((root / path).read_text())
                previous = old['groups']['CI_INTEGRITY']['modules']
                current = new['groups']['CI_INTEGRITY']['modules']
                allowed = {f'tests.test_{name}' for name in TESTS}
                if not set(previous) <= set(current) or set(current) - set(previous) - allowed:
                    return False
                old['groups']['CI_INTEGRITY']['modules'] = current
                if old != new:
                    return False
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                return False
        elif path in QT_DETECTOR_PATHS:
            if not _qt_detector_boundary(root, path):
                return False
        elif path not in OWNERS and path not in workflows:
            return False
        has_tooling = True
    return has_tooling


def run_checks(root: Path) -> None:
    suite = unittest.TestSuite()
    for name in TESTS:
        tests = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern=f'test_{name}.py')
        if tests.countTestCases() == 0:
            raise ValueError('Missing mandatory tooling contracts: ' + name)
        suite.addTests(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
