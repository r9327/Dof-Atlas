from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.ci_history import (
    application_log_profile,
    actions_job_step_profile,
    duplicate_unittest_modules,
    report_from_files,
)


class CIHistoryTests(unittest.TestCase):
    def test_profile_reads_existing_log_without_executing_tests(self):
        log = '\n'.join([
            '2026-10-10T11:40:00.000Z & py -3.13 -m unittest discover -v -s tests -p "test_*.py"',
            '2026-10-10T11:40:01.000Z test_one (test_a.C.test_one) ... ok',
            '2026-10-10T11:40:07.000Z test_two (test_a.C.test_two) ... ok',
            '2026-10-10T11:40:08.000Z test_three (test_b.C.test_three) ... ok',
            '2026-10-10T11:40:08.500Z Ran 3 tests in 8.500s',
            '2026-10-10T11:40:08.500Z OK',
        ])
        report = application_log_profile(log)
        self.assertEqual(report['test_count_declared'], 3)
        self.assertEqual(report['test_verdict_lines_seen'], 3)
        self.assertEqual(report['top_20_approx_intervals'][0]['approx_seconds'], 6.0)
        self.assertFalse(report['tests_executed'])
        self.assertIn('not individual test runtimes', report['limitations'])

    def test_incomplete_or_unmarked_logs_fail_closed(self):
        for source in ('hello world', 'unittest discover -v -s tests',
                       '-m unittest discover -v -s tests\nRan 1 test in 1.0s'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                application_log_profile(source)

    def test_jobs_use_github_step_boundaries(self):
        job = {'name': 'Full Application Suite', 'conclusion': 'success', 'steps': [
            {'name': 'Full', 'started_at': '2026-10-10T11:00:00Z',
             'completed_at': '2026-10-10T11:03:00Z', 'conclusion': 'success'},
            {'name': 'Setup', 'started_at': '2026-10-10T10:58:00Z',
             'completed_at': '2026-10-10T10:58:20Z', 'conclusion': 'success'},
        ]}
        result = actions_job_step_profile(job)
        self.assertEqual(result['top_20_steps'][0]['seconds'], 180)
        self.assertFalse(result['tests_executed'])

    def test_static_duplicate_report_does_not_authorize_skips(self):
        first = '''- name: First\n  run: |\n    python -m unittest -v tests.test_foo tests.test_bar\n'''
        second = '''- name: Second\n  run: |\n    python -m unittest -v tests.test_foo\n'''
        report = duplicate_unittest_modules({'one.yml': first, 'two.yml': second})
        self.assertEqual(report['duplicate_module_count'], 1)
        self.assertEqual(report['duplicated_modules'][0]['module'], 'tests.test_foo')
        self.assertEqual(report['elisions_authorized'], 0)
        self.assertFalse(report['full_suite_waived'])

    def test_full_application_suite_reports_slowest_tests_without_filters(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    '.github/workflows/app-ci.yml').read_text(encoding='utf-8')
        full = next(line.strip() for line in workflow.splitlines()
                    if '-m unittest discover -v -s tests' in line)
        self.assertIn('-p "test_*.py" --durations=20', full)
        self.assertNotIn(' -k ', full)
        self.assertNotIn(' --failfast', full)
        self.assertNotIn(' --buffer', full)
    def test_read_files_instead_of_running_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'workflow.yml'
            path.write_text('- name: Tests\n  run: python -m unittest tests.test_foo\n', encoding='utf-8')
            report = report_from_files(workflow_paths=[path])
            self.assertEqual(report['duplicates']['distinct_explicit_modules'], 1)
            self.assertTrue(report['read_only'])


if __name__ == '__main__':
    unittest.main()
