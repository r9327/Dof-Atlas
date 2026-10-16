from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import agent, atlas_doctor, atlas_integrity
from tools.atlas_doctor_lib import gates


class DoctorVerificationContractTests(unittest.TestCase):
    @staticmethod
    def baseline():
        return {'git': {'head': 'baseline-sha'}, 'integrity_mode': 'CRITICAL', 'issues': []}

    @staticmethod
    def audit(verdict='PASS', integrity='PASS'):
        return {
            'integrity_mode': 'CRITICAL', 'issues': [],
            'summary': {'verdict': verdict, 'issues_total': 0, 'severity': {}},
            'integrity': {'status': integrity, 'command': ['python', '-m', 'tools.atlas_integrity', 'critical'],
                          'report': {'blockers': ['PERSISTENCE_FAILED'] if integrity == 'FAIL' else []}},
        }

    def invoke(self, payload, baseline=None, argv=None):
        output = io.StringIO()
        with (patch.object(atlas_doctor, 'load_json', return_value=baseline or self.baseline()),
              patch.object(atlas_doctor, 'run_audit', return_value=payload) as run,
              contextlib.redirect_stdout(output)):
            code = atlas_doctor.main(argv or ['verify', '--json'])
        return code, json.loads(output.getvalue()), run

    def test_verify_failure_is_nonzero_and_exposes_canonical_blocker(self):
        code, result, run = self.invoke(self.audit('FAIL', 'FAIL'))
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['primary_cause'], 'PERSISTENCE_FAILED')
        self.assertEqual(result['reproduction_command'], ['python', '-m', 'tools.atlas_integrity', 'critical'])
        self.assertEqual(run.call_args.kwargs['base_ref'], 'baseline-sha')

    def test_verify_pass_keeps_existing_comparison_fields(self):
        code, result, _ = self.invoke(self.audit())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['comparison']['status'], 'PASS')
        self.assertIn('audit', result)
        self.assertIn('comparison', result)

    def test_verify_warn_is_review_without_invented_cause(self):
        code, result, _ = self.invoke(self.audit('WARN'))
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'REVIEW')
        self.assertIn('no regression cause is inferred', result['primary_cause'])

    def test_verify_timeout_is_review_not_false_pass_or_executed_failure(self):
        code, result, _ = self.invoke(self.audit('PASS', 'TIMEOUT'))
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'REVIEW')

    def test_verify_rejects_incompatible_baseline_as_review(self):
        before = self.baseline()
        before['integrity_mode'] = None
        code, result, _ = self.invoke(self.audit(), before)
        self.assertEqual(code, 1)
        self.assertEqual(result['comparison']['status'], 'UNAVAILABLE')

    def test_verify_cli_forwards_explicit_base_and_gate(self):
        _, result, run = self.invoke(self.audit(), argv=['verify', '--base-ref', 'origin/main', '--gate', 'fast', '--json'])
        self.assertEqual(result['base_ref'], 'origin/main')
        self.assertEqual(run.call_args.kwargs, {'integrity_mode': 'fast', 'base_ref': 'origin/main'})

    def test_baseline_head_preserves_committed_changes_in_canonical_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
            git('init')
            git('config', 'user.name', 'Atlas Tests')
            git('config', 'user.email', 'atlas-tests@example.invalid')
            (root / 'example.py').write_text('value = 1\n')
            git('add', '.')
            git('commit', '-m', 'baseline')
            head = git('rev-parse', 'HEAD')
            (root / 'example.py').write_text('value = 2\n')
            git('add', '.')
            git('commit', '-m', 'change')
            before = self.baseline()
            before['git']['head'] = head
            def audit(actual_root, *, integrity_mode, base_ref):
                self.assertEqual(actual_root, root)
                self.assertEqual(atlas_integrity.changed_files(root, base_ref), ['example.py'])
                return self.audit()
            with (patch.object(atlas_doctor, 'load_json', return_value=before),
                  patch.object(atlas_doctor, 'run_audit', side_effect=audit)):
                result = atlas_doctor.command_verify(root, argparse.Namespace(json=True, gate='critical', base_ref=None))
            self.assertEqual(result['base_ref'], head)
            self.assertEqual(result['status'], 'PASS')

    def test_gate_adapter_forwards_base_to_single_canonical_engine(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps({'verdict': 'PASS'}), '')
        with (patch.object(Path, 'is_file', return_value=True),
              patch.object(gates.subprocess, 'run', return_value=completed) as run):
            result = gates.run_integrity_gate(Path.cwd(), 'fast', base_ref='base-sha')
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--base-ref') + 1], 'base-sha')
        self.assertIn('tools.atlas_integrity', command)
        self.assertEqual(result['status'], 'PASS')

    def test_gate_adapter_uses_mode_aware_timeout_and_utf8(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps({'verdict': 'PASS'}), '')
        with (patch.object(Path, 'is_file', return_value=True),
              patch.object(gates.subprocess, 'run', return_value=completed) as run):
            gates.run_integrity_gate(Path.cwd(), 'full')
        self.assertEqual(run.call_args.kwargs['timeout'], 7200)
        self.assertEqual(run.call_args.kwargs['env']['PYTHONUTF8'], '1')

        with (patch.object(Path, 'is_file', return_value=True),
              patch.object(gates.subprocess, 'run', return_value=completed) as run):
            gates.run_integrity_gate(Path.cwd(), 'critical', timeout=12)
        self.assertEqual(run.call_args.kwargs['timeout'], 12)

    def test_core_tooling_has_one_owned_scope_and_existing_tests(self):
        paths = ['tools/agent.py', 'tools/agent_planner.py', 'tools/tool_catalog.py',
                 'tools/tool_audit.py', 'tools/ai_context.py']
        ownership = agent.ownership_payload(agent.ROOT, paths)
        self.assertEqual(ownership['status'], 'PASS')
        self.assertTrue(all(row['primary_scope'] == 'quality_ci' for row in ownership['paths'].values()))
        impact = agent.impact_payload(agent.ROOT, paths)
        self.assertIn('tests.test_agent_planner', impact['recommended_tests'])
        self.assertIn('tests.test_tool_spec_contract', impact['recommended_tests'])


if __name__ == '__main__':
    unittest.main()
