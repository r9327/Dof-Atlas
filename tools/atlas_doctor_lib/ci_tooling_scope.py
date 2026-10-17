"""Bounded CI-only validation, distinct from application/Phase certification."""
from __future__ import annotations

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
    # Developer-facing diagnosis only: tested but never application-certified.
    'atlas_doctor_capabilities', 'atlas_doctor_capability_evidence',
    'atlas_doctor_agent_protocol',
)
OWNERS = frozenset({
    'tools/atlas_doctor.py', 'tools/atlas_doctor_lib/ci_orchestrator.py',
    'tools/atlas_doctor_lib/ci_tooling_scope.py', 'tools/atlas_doctor_lib/ci_routes.json',
    'tools/atlas_doctor_lib/doctor_ui_ci.py', 'tools/atlas_meta_integrity.py',
    'tools/atlas_doctor_lib/capability_matrix.py',
    'tools/atlas_doctor_lib/capability_evidence.py',
    'tools/atlas_doctor_lib/agent_protocol.py',
    'tools/ci_main_phase_evidence.py', 'tools/ci_verified_pr_full.py',
    'tools/ci_required_certification.py',
    'tests/test_ai_context.py',
    *(f'tests/test_{name}.py' for name in TESTS),
})
RETIRED_WORKFLOWS = frozenset({'.github/workflows/public-pr-ci.yml'})


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
