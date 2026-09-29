from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.audit import run_audit
from tools.atlas_doctor_lib.core import cache_matches_git, git_state, load_json
from tools.atlas_doctor_lib.perf import profile_data_files
from tools.atlas_doctor_lib.report import compare_runs


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

    def test_cache_invalidates_when_worktree_changes(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            payload = run_audit(root)
            state = git_state(root)
            self.assertTrue(cache_matches_git(payload, state))
            (root / 'main.py').write_text('print("changed")\n', encoding='utf-8')
            self.assertFalse(cache_matches_git(payload, git_state(root)))
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

    def test_compare_runs_reports_new_and_fixed_issue_ids(self) -> None:
        old = {'issues': [{'id': 'a'}, {'id': 'b'}]}
        new = {'issues': [{'id': 'b'}, {'id': 'c'}]}
        payload = compare_runs(new, old)
        self.assertEqual([item['id'] for item in payload['new_issues']], ['c'])
        self.assertEqual([item['id'] for item in payload['fixed_issues']], ['a'])
        self.assertEqual(payload['unchanged_count'], 1)


if __name__ == '__main__':
    unittest.main()
