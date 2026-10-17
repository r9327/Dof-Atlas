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
        for kwargs in ({'route': {}}, {'route': {'route': 'INVALID'}}, {'deleted': ['app/old.py']},
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

    def test_known_high_risk_full_does_not_replay_unrelated_specialists(self):
        p = self.select(['app/core/json_store.py'], route={'route': 'FULL'},
                        ui={'status': 'UI_REQUIRED', 'selected_scenarios': ['guides-success']})
        self.assertTrue(p['full'])
        self.assertTrue(p['phase'])
        self.assertFalse(p['specialist_fallback'])
        self.assertTrue(p['workflows']['phase8-memory-benchmark']['selected'])
        self.assertTrue(p['workflows']['phase8-preload-benchmark']['selected'])
        self.assertFalse(p['workflows']['json-focused-data-contract']['selected'])
        self.assertFalse(p['workflows']['atlas-windows-distribution']['selected'])
        self.assertFalse(p['workflows']['doctor-runtime-perf']['selected'])

    def test_known_workflow_uses_focused_ci_contracts_without_application_full(self):
        p = self.select(['.github/workflows/phase-certification.yml'])
        self.assertFalse(p['full'])
        self.assertFalse(p['phase'])
        self.assertTrue(p['tooling_only'])
        self.assertFalse(p['specialist_fallback'])
        self.assertFalse(p['workflows']['json-focused-data-contract']['selected'])

    def test_small_router_change_is_focused_but_runtime_mixture_or_unknown_is_not(self):
        for path in ('tools/atlas_doctor_lib/ci_orchestrator.py',
                     'tools/atlas_doctor_lib/ci_routes.json', 'tests/test_doctor_ui_ci.py'):
            with self.subTest(path=path):
                p = self.select([path], route={'route': 'FULL'})
                self.assertFalse(p['full'])
                self.assertTrue(p['tooling_only'])
        for extra in ('app/core/json_store.py', 'tools/new_router.py',
                      'tools/atlas_integrity.py', '.github/rulesets/main.json',
                      'requirements-pyside.txt', '.github/workflows/unknown.yml'):
            with self.subTest(extra=extra):
                self.assertTrue(self.select(['tools/atlas_doctor_lib/ci_orchestrator.py', extra],
                                            route={'route': 'FULL'})['full'])
        self.assertTrue(self.select(['tools/atlas_doctor_lib/ci_orchestrator.py'], route={})['full'])
        self.assertTrue(self.select(['tools/atlas_doctor_lib/ci_orchestrator.py'],
                                    deleted=['tools/old.py'])['full'])
        self.assertTrue(self.select(['tools/atlas_doctor_lib/ci_orchestrator.py'],
                                    event='workflow_dispatch')['full'])

    def test_focused_ci_runs_and_stores_real_36_capability_witnesses(self):
        workflow = (ROOT / '.github/workflows/phase-certification.yml').read_text(encoding='utf-8')
        focused = workflow.split('  focused-validation:', 1)[1].split('  certify:', 1)[0]
        self.assertIn('run_capability_witnesses(Path.cwd(), timeout=240)', focused)
        self.assertIn('validate_capability_evidence(Path.cwd(), witness)', focused)
        self.assertIn("witness['status'] != 'PASS'", focused)
        self.assertIn("checked['status'] != 'PASS'", focused)
        self.assertIn('artifacts/doctor_ci/capability_evidence.json', focused)
        self.assertIn("if p['tooling_only']:", focused)
        self.assertIn('if-no-files-found: error', focused)

    def test_doctor_only_behavior_evidence_is_focused_not_app_release_certification(self):
        paths = [
            'tools/atlas_doctor.py',
            'tools/atlas_doctor_lib/capability_matrix.py',
            'tools/atlas_doctor_lib/capability_evidence.py',
            'tools/atlas_doctor_lib/agent_protocol.py',
            'tests/test_atlas_doctor_capabilities.py',
            'tests/test_atlas_doctor_capability_evidence.py',
            'tests/test_atlas_doctor_agent_protocol.py',
            '.ai/context_index.json',
            'docs/audit-remediation/2026-10-17/07-doctor-capability-ci-evidence.md',
        ]
        result = self.select(paths, route={'route': 'FULL'})
        self.assertTrue(result['tooling_only'])
        self.assertFalse(result['full'])
        self.assertFalse(result['phase'])
        self.assertFalse(result['workflows']['doctor-ui']['selected'])
        self.assertTrue(result['workflows']['graphify-targeted-ci']['selected'])
        for mixed in ['app/modules/encyclopedia/views/guides_view.py',
                      'tools/atlas_doctor_lib/runtime_observation.py',
                      'tests/test_guide_ultime_v5_ui.py']:
            with self.subTest(mixed=mixed):
                result = self.select([*paths, mixed], route={'route': 'FULL'})
                self.assertTrue(result['full'])
                self.assertTrue(result['phase'])
        self.assertTrue(self.select(paths, route={'route': 'INVALID'})['full'])
        self.assertTrue(self.select(paths, deleted=['tools/old_capability.py'])['full'])
        self.assertTrue(self.select(paths, event='workflow_dispatch')['full'])

    def test_integrity_policy_only_allows_additive_ci_test_wiring(self):
        from tools.atlas_doctor_lib.ci_tooling_scope import eligible
        from unittest.mock import patch
        paths = ['tools/atlas_integrity_policy.json']
        original = {'groups': {'CI_INTEGRITY': {'modules': ['tests.existing']}},
                    'certification': {'minimum_mode': 'FULL'}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tools').mkdir()
            policy = root / paths[0]
            def accepts(body):
                policy.write_text(json.dumps(body))
                with patch('tools.atlas_doctor_lib.ci_tooling_scope.subprocess.check_output',
                           return_value=json.dumps(original)):
                    return eligible(paths, root=root, base_sha='a' * 40)
            updated = json.loads(json.dumps(original))
            updated['groups']['CI_INTEGRITY']['modules'].append('tests.test_doctor_ci_orchestrator')
            self.assertTrue(accepts(updated))
            updated['certification']['minimum_mode'] = 'FAST'
            self.assertFalse(accepts(updated))
            updated = json.loads(json.dumps(original))
            updated['groups']['CI_INTEGRITY']['modules'] = ['tests.test_doctor_ci_orchestrator']
            self.assertFalse(accepts(updated))
            self.assertFalse(eligible(paths))

    def test_provider_contract_is_selected_for_provider_changes(self):
        p = self.select(['app/modules/encyclopedia/providers/quest_provider.py'])
        self.assertTrue(p['workflows']['encyclopedia-provider-import']['selected'])
        low = self.select(['tools/atlas_json_raw.py'])
        self.assertFalse(low['workflows']['encyclopedia-provider-import']['selected'])

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
        source = (ROOT / '.github/workflows/phase-certification.yml').read_text(encoding='utf-8')
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
        registry = json.loads((ROOT / 'tools/atlas_doctor_lib/ci_routes.json').read_text(encoding='utf-8'))
        for name in registry:
            source = (ROOT / f'.github/workflows/{name}.yml').read_text(encoding='utf-8')
            trigger = source.split('permissions:', 1)[0]
            self.assertIn('  workflow_call:', trigger, name)
            self.assertNotIn('  pull_request:', trigger, name)
            self.assertNotIn('  push:', trigger, name)
        central = (ROOT / '.github/workflows/phase-certification.yml').read_text(encoding='utf-8')
        self.assertIn('name: Public PR / Safe Validation', central)
        self.assertNotIn('      - edited\n', central)
        self.assertNotIn('      - converted_to_draft\n', central)
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
