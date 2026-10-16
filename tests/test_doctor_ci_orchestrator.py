from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from tools.atlas_doctor_lib.ci_orchestrator import plan_ci, select_workflows

ROOT = Path(__file__).resolve().parents[1]
SCOPED = {'route': 'SCOPED'}
UI_NONE = {'status': 'NOT_APPLICABLE', 'selected_scenarios': []}


class DoctorCiOrchestratorTests(unittest.TestCase):
    def select(self, paths, *, route=SCOPED, event='pull_request', ui=UI_NONE, deleted=()):
        return select_workflows(paths, event=event, phase_route=route, ui_plan=ui, deleted=deleted)

    def test_docs_only_retains_metadata_and_required_pr_check_without_heavy_jobs(self):
        p = self.select(['docs/usage.md', '.ai/context_index.json'], route={})
        self.assertFalse(p['full'])
        self.assertFalse(p['phase'])
        self.assertEqual({k for k, v in p['workflows'].items() if v['selected']},
                         {'ai-context-ci', 'signature-report'})

    def test_mixed_docs_and_code_does_not_hide_code_impact(self):
        p = self.select(['docs/usage.md', 'app/preload.py'])
        self.assertTrue(p['phase'])
        self.assertTrue(p['workflows']['phase8-preload-benchmark']['selected'])
        self.assertTrue(p['workflows']['phase8-memory-benchmark']['selected'])

    def test_unknown_or_deleted_changes_fall_back_to_real_full(self):
        for kwargs in ({'route': {}}, {'deleted': ['app/old.py']},
                       {'ui': {'status': 'REVIEW_REQUIRED'}}):
            with self.subTest(kwargs=kwargs):
                p = self.select(['app/new.py'], **kwargs)
                self.assertTrue(p['full'])
                self.assertTrue(p['phase'])
                self.assertTrue(p['workflows']['phase8-memory-benchmark']['selected'])

    def test_explicit_manual_certification_cannot_be_downscoped_by_docs(self):
        self.assertTrue(self.select(['docs/a.md'], event='workflow_dispatch')['full'])
        self.assertTrue(self.select(['docs/a.md'], event='workflow_dispatch')['phase'])

    def test_policy_document_is_not_an_ordinary_doc(self):
        p = self.select(['PHASE_CERTIFICATION.md'], route={})
        self.assertTrue(p['full'])
        self.assertFalse(p['docs_only'])

    def test_ui_scenarios_use_the_canonical_selection(self):
        p = self.select(['app/ui/theme.py'], ui={
            'status': 'UI_REQUIRED', 'selected_scenarios': ['guides-success']})
        self.assertTrue(p['workflows']['doctor-ui']['selected'])
        self.assertFalse(p['workflows']['app-ci']['selected'])
        self.assertTrue(self.select(['app/ui/theme.py'], event='push')['workflows']['app-ci']['selected'])

    def test_uncertain_ui_impact_runs_all_registered_scenarios_and_full(self):
        from tools.atlas_doctor_lib.doctor_ui_ci import exhaustive_review_plan, SCENARIOS
        original = {'status': 'REVIEW_REQUIRED', 'selected_scenarios': [],
                    'uncertainty': ['UNMAPPED_DEPENDENCY'], 'candidate_sha': 'a' * 40}
        campaign = exhaustive_review_plan(original)
        self.assertEqual(original['status'], 'REVIEW_REQUIRED')
        self.assertEqual(campaign['selected_scenarios'], sorted(SCENARIOS))
        self.assertEqual(campaign['uncertainty'], original['uncertainty'])
        self.assertEqual(campaign['status'], 'UI_REQUIRED')
        selection = self.select(['tools/unknown.py'], ui=original)
        self.assertTrue(selection['full'])
        self.assertTrue(selection['workflows']['doctor-ui']['selected'])

    def test_exhaustive_ui_fallback_never_accepts_dirty_or_wrong_sha(self):
        from unittest.mock import patch
        from tools.atlas_doctor_lib.doctor_ui_ci import plan_ui
        head, base = 'a' * 40, 'b' * 40
        for actual, dirty, expected in [(head, '', 'UI_REQUIRED'), (head, ' M app/a.py', 'REVIEW_REQUIRED'), (base, '', 'REVIEW_REQUIRED')]:
            with patch('tools.atlas_doctor_lib.doctor_ui_ci.git_value', side_effect=[actual, dirty, base]), patch('tools.atlas_doctor_lib.doctor_ui_ci.changed_paths', return_value=(['new.bin'], [])):
                report = plan_ui(ROOT, base, head, exhaustive_on_review=True)
            self.assertEqual(report['status'], expected)
            self.assertEqual(bool(report.get('exhaustive_on_review')), expected == 'UI_REQUIRED')

    def test_main_plan_never_starts_release_publishing_or_pr_only_doctor(self):
        p = self.select(['app/distribution/install.py'], route={}, event='push')
        self.assertFalse(p['workflows']['atlas-windows-distribution']['selected'])
        self.assertFalse(p['workflows']['doctor-certification']['selected'])
        self.assertTrue(p['workflows']['app-ci']['selected'])

    def test_real_git_diff_rename_and_missing_planner_cannot_become_empty_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
            git('init');git('config', 'user.name', 'CI Test');git('config', 'user.email', 'ci@example.invalid')
            (root / 'app').mkdir()
            (root / 'app/old.py').write_text('VALUE = 1\n')
            git('add', '.');git('commit', '-m', 'base');base = git('rev-parse', 'HEAD')
            git('mv', 'app/old.py', 'app/new.py');git('commit', '-m', 'rename');head = git('rev-parse', 'HEAD')
            # No tools in this isolated checkout: a failed canonical planner must cause FULL.
            report = plan_ci(root, base_ref=base, candidate_sha=head, event='pull_request',
                             output=root / 'artifacts/plan.json')
            self.assertEqual(report['changed_paths'], ['app/new.py'])
            self.assertEqual(report['deleted_paths'], ['app/old.py'])
            self.assertTrue(report['full'])
            self.assertFalse(report['tests_executed'])
            with self.assertRaises((ValueError, subprocess.SubprocessError)):
                plan_ci(root, base_ref='missing-base', candidate_sha=head, event='pull_request', output=root / 'plan.json')
            with self.assertRaises(ValueError):
                plan_ci(root, base_ref=base, candidate_sha=base, event='pull_request', output=root / 'plan.json')
            (root / 'app/new.py').write_text('VALUE = 2\n')
            with self.assertRaises(ValueError):
                plan_ci(root, base_ref=base, candidate_sha=head, event='pull_request', output=root / 'plan.json')

    def test_actual_final_verdict_rejects_skipped_failed_or_cancelled_selected_ci(self):
        source = (ROOT / '.github/workflows/phase-certification.yml').read_text()
        script = textwrap.dedent(source.rsplit('        run: |\n', 1)[1])
        for result, expected in [('success', 0), ('skipped', 1), ('failure', 1), ('cancelled', 1)]:
            env = {**os.environ, 'DOCTOR_REQUIRED': '["certify"]',
                   'DOCTOR_RESULTS': json.dumps({'doctor-plan': {'result': 'success'}, 'certify': {'result': result}})}
            done = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True)
            self.assertEqual(done.returncode, expected, done.stderr)
        for value in ('{}', '{"doctor-plan":{"result":"failure"}}'):
            env = {**os.environ, 'DOCTOR_REQUIRED': '', 'DOCTOR_RESULTS': value}
            self.assertNotEqual(subprocess.run([sys.executable, '-c', script], env=env, capture_output=True).returncode, 0)

    def test_single_automatic_entry_and_no_required_public_check_rename(self):
        registry = json.loads((ROOT / 'tools/atlas_doctor_lib/ci_routes.json').read_text())
        for name in registry:
            source = (ROOT / f'.github/workflows/{name}.yml').read_text()
            trigger = source.split('permissions:', 1)[0]
            self.assertIn('  workflow_call:', trigger, name)
            self.assertNotIn('  pull_request:', trigger, name)
            self.assertNotIn('  push:', trigger, name)
        central = (ROOT / '.github/workflows/phase-certification.yml').read_text()
        self.assertIn('name: Public PR / Safe Validation', central)
        self.assertIn('name: Require successful Doctor plan', central)
        self.assertIn('if: always() && github.event_name == \'pull_request\'', central)
        certify = central.split('  certify:', 1)[1].split('    steps:', 1)[0]
        self.assertIn('needs: doctor-plan', certify)
        self.assertNotIn('title', certify)
        self.assertNotIn('draft', certify)
        required_public = central.split('  safe-validation:', 1)[1].split('    steps:', 1)[0]
        self.assertIn('pr-fast-validation', required_public)
        self.assertIn('certify', required_public)
        for name in registry:
            self.assertIn(name.replace('-', '_'), required_public)


if __name__ == '__main__':
    unittest.main()
