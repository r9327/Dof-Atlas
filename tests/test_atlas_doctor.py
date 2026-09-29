from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.audit import run_audit
from tools.atlas_doctor_lib.core import cache_matches_git, git_state, load_json
from tools.atlas_doctor_lib.live import _sample_tree
from tools.atlas_doctor_lib.perf import profile_data_files
from tools.atlas_doctor_lib.report import compare_performance, compare_runs


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


class AtlasDoctorTests(unittest.TestCase):
    def make_repo(self) -> tempfile.TemporaryDirectory:
        directory = tempfile.TemporaryDirectory(prefix='atlas-doctor-')
        root = Path(directory.name)
        _git(root, 'init')
        _git(root, 'config', 'user.email', 'atlas-tests@example.invalid')
        _git(root, 'config', 'user.name', 'Atlas Tests')
        (root / 'main.py').write_text('print("ok")\n', encoding='utf-8')
        (root / 'app').mkdir()
        (root / 'data').mkdir()
        (root / '.gitignore').write_text('.ai/runtime/\n', encoding='utf-8')
        _git(root, 'add', '-A')
        _git(root, 'commit', '-m', 'baseline')
        directory.root = root  # type: ignore[attr-defined]
        return directory

    def test_audit_detects_silent_exception_and_writes_cache(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            target = root / 'app' / 'bad.py'
            target.write_text('def f():\n    try:\n        1 / 0\n    except Exception:\n        pass\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'bad')
            payload = run_audit(root)
            rules = {item['rule'] for item in payload['issues']}
            self.assertIn('silent_exception', rules)
            cached = load_json(root, 'latest_audit')
            self.assertEqual(cached['git']['head'], git_state(root)['head'])
        finally:
            directory.cleanup()

    def test_cache_invalidates_when_worktree_content_changes(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            payload = run_audit(root)
            state = git_state(root)
            self.assertTrue(cache_matches_git(payload, state))
            target = root / 'main.py'
            target.write_text('print("changed-1")\n', encoding='utf-8')
            dirty_state = git_state(root)
            self.assertFalse(cache_matches_git(payload, dirty_state))
            dirty_payload = {'git': dirty_state}
            target.write_text('print("changed-2")\n', encoding='utf-8')
            self.assertFalse(cache_matches_git(dirty_payload, git_state(root)))
        finally:
            directory.cleanup()

    def test_file_profile_reports_read_and_json_parse_times(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            target = root / 'data' / 'example.json'
            target.write_text(json.dumps({'items': list(range(50))}), encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'data')
            payload = profile_data_files(root)
            self.assertEqual(payload['files_measured'], 1)
            row = payload['slowest'][0]
            self.assertEqual(row['path'], 'data/example.json')
            self.assertGreaterEqual(row['read_ms'], 0.0)
            self.assertGreaterEqual(row['json_parse_ms'], 0.0)
        finally:
            directory.cleanup()

    def test_audit_flags_forbidden_import_star(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            target = root / 'app' / 'wildcard.py'
            target.write_text('from math import *\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'wildcard')
            payload = run_audit(root)
            self.assertIn('import_star', {item['rule'] for item in payload['issues']})
        finally:
            directory.cleanup()

    def test_live_sampler_reads_current_process(self) -> None:
        import os

        sample = _sample_tree(os.getpid())
        self.assertGreaterEqual(sample['process_count'], 1)
        self.assertGreater(sample['rss_bytes'], 0)
        self.assertGreaterEqual(sample['cpu_seconds'], 0.0)

    def test_compare_performance_detects_large_regression(self) -> None:
        old = {
            'runtime': {'benchmark': {'after': {'quests_open_ms': 100.0, 'startup_stabilized_rss_mb': 90.0}}},
            'file_profile': {'total_read_ms': 10.0, 'total_json_parse_ms': 20.0, 'p95_file_total_ms': 2.0},
        }
        new = {
            'runtime': {'benchmark': {'after': {'quests_open_ms': 130.0, 'startup_stabilized_rss_mb': 92.0}}},
            'file_profile': {'total_read_ms': 13.0, 'total_json_parse_ms': 20.0, 'p95_file_total_ms': 2.0},
        }
        payload = compare_performance(new, old)
        metrics = {row['metric'] for row in payload['regressions_15pct']}
        self.assertIn('quests_open_ms', metrics)
        self.assertIn('file_profile.total_read_ms', metrics)


    def test_compare_runs_rejects_different_audit_modes(self) -> None:
        old = {'integrity_mode': None, 'issues': []}
        new = {'integrity_mode': 'CRITICAL', 'issues': []}
        payload = compare_runs(new, old)
        self.assertEqual(payload['status'], 'UNAVAILABLE')

    def test_compare_performance_ignores_non_cost_numeric_ids(self) -> None:
        old = {'runtime': {'benchmark': {'after': {'first_achievement_id': 10, 'quests_open_ms': 100.0}}}}
        new = {'runtime': {'benchmark': {'after': {'first_achievement_id': 9999, 'quests_open_ms': 100.0}}}}
        payload = compare_performance(new, old)
        metrics = {row['metric'] for row in payload['metrics']}
        self.assertNotIn('first_achievement_id', metrics)

    def test_compare_runs_reports_new_and_fixed_issue_ids(self) -> None:
        old = {'issues': [{'id': 'a'}, {'id': 'b'}]}
        new = {'issues': [{'id': 'b'}, {'id': 'c'}]}
        payload = compare_runs(new, old)
        self.assertEqual([item['id'] for item in payload['new_issues']], ['c'])
        self.assertEqual([item['id'] for item in payload['fixed_issues']], ['a'])
        self.assertEqual(payload['unchanged_count'], 1)


if __name__ == '__main__':
    unittest.main()
