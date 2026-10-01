from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.atlas_doctor_lib.audit import run_audit
from tools.atlas_doctor_lib.core import cache_matches_git, git_state, load_json, write_json
from tools.atlas_doctor_lib.live import _sample_tree, inspect_live
from tools.atlas_doctor_lib.perf import profile_data_files
from tools.atlas_doctor_lib.report import build_ai_report, compare_performance, compare_runs


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
            self.assertEqual(payload['analysis_sources'], {
                'static_ast': True, 'tracked_files': True, 'graph': False, 'atlas_integrity': False,
            })
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

    def test_audit_accepts_narrow_intentional_suppression(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            target = root / 'app' / 'cleanup.py'
            target.write_text(
                'from contextlib import suppress\n'
                'def close_socket(sock):\n'
                '    with suppress(OSError):\n'
                '        sock.close()\n',
                encoding='utf-8',
            )
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'intentional-cleanup')
            payload = run_audit(root)
            self.assertNotIn('silent_exception', {item['rule'] for item in payload['issues']})
        finally:
            directory.cleanup()

    def test_audit_resolves_canonical_lazy_export_mapping(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            package = root / 'app' / 'package'
            package.mkdir()
            (package / '__init__.py').write_text(
                'from importlib import import_module\n'
                '_LAZY_EXPORTS = {"Thing": ("app.package.thing", "Thing")}\n'
                'def __getattr__(name):\n'
                '    target = _LAZY_EXPORTS.get(name)\n'
                '    module_name, attribute_name = target\n'
                '    return getattr(import_module(module_name), attribute_name)\n',
                encoding='utf-8',
            )
            (package / 'thing.py').write_text('class Thing:\n    pass\n', encoding='utf-8')
            (package / 'dead.py').write_text('class Dead:\n    pass\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'lazy exports')
            issues = run_audit(root, save=False)['issues']
            dead_paths = {item['path'] for item in issues if item['rule'] == 'unreferenced_module'}
            self.assertNotIn('app/package/thing.py', dead_paths)
            self.assertIn('app/package/dead.py', dead_paths)
        finally:
            directory.cleanup()

    def test_audit_keeps_unproven_dynamic_import_as_unreferenced(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            package = root / 'app' / 'package'
            package.mkdir()
            (package / '__init__.py').write_text(
                'from importlib import import_module\n'
                'UNRELATED = {"Thing": ("app.package.thing", "Thing")}\n'
                'def load(module_name):\n'
                '    return import_module(module_name)\n',
                encoding='utf-8',
            )
            (package / 'thing.py').write_text('class Thing:\n    pass\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'unproven dynamic import')
            issues = run_audit(root, save=False)['issues']
            dead_paths = {item['path'] for item in issues if item['rule'] == 'unreferenced_module'}
            self.assertIn('app/package/thing.py', dead_paths)
        finally:
            directory.cleanup()

    def test_audit_recognizes_executor_submitted_io_but_keeps_direct_ui_io(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            view = root / 'app' / 'pages' / 'view.py'
            view.parent.mkdir()
            view.write_text(
                'from concurrent.futures import ThreadPoolExecutor\n'
                'from pathlib import Path\n'
                'POOL = ThreadPoolExecutor(max_workers=1)\n'
                'def decode(path):\n'
                '    return Path(path).read_bytes()\n'
                'def direct(path):\n'
                '    return Path(path).read_bytes()\n'
                'def start(path):\n'
                '    return POOL.submit(decode, path)\n',
                encoding='utf-8',
            )
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'executor io')
            issues = run_audit(root, save=False)['issues']
            io_lines = {item['line'] for item in issues if item['rule'] == 'sync_io_ui'}
            self.assertNotIn(5, io_lines)
            self.assertIn(7, io_lines)
        finally:
            directory.cleanup()

    def test_audit_recognizes_transitive_blocking_io_but_keeps_true_spin(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            target = root / 'app' / 'loops.py'
            target.write_text(
                'def blocking(stream):\n'
                '    return stream.read(1)\n'
                'def consume(stream):\n'
                '    while True:\n'
                '        if not blocking(stream):\n'
                '            break\n'
                'def spin(flag):\n'
                '    while True:\n'
                '        if flag():\n'
                '            continue\n',
                encoding='utf-8',
            )
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'loops')
            issues = run_audit(root, save=False)['issues']
            loop_lines = {item['line'] for item in issues if item['rule'] == 'busy_loop_risk'}
            self.assertNotIn(4, loop_lines)
            self.assertIn(8, loop_lines)
        finally:
            directory.cleanup()

    def test_audit_distinguishes_controlled_and_ordinary_dynamic_exec(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            target = root / 'app' / 'dynamic.py'
            target.write_text(
                'def controlled(source, path):\n'
                '    namespace: dict = {"__file__": str(path), "__name__": "isolated"}\n'
                '    exec(compile(source, str(path), "exec"), namespace)\n'
                'def ordinary(source):\n'
                '    exec(source)\n',
                encoding='utf-8',
            )
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'dynamic exec')
            issues = run_audit(root, save=False)['issues']
            controlled = [item for item in issues if item['rule'] == 'controlled_dynamic_exec']
            ordinary = [item for item in issues if item['rule'] == 'dynamic_exec']
            self.assertEqual([item['line'] for item in controlled], [3])
            self.assertEqual([item['line'] for item in ordinary], [5])
            self.assertEqual(controlled[0]['severity'], 'INFO')
            self.assertEqual(ordinary[0]['severity'], 'HIGH')
        finally:
            directory.cleanup()

    def test_snapshot_rotation_publishes_previous_and_latest(self) -> None:
        with tempfile.TemporaryDirectory(prefix='atlas-doctor-rotation-') as directory:
            root = Path(directory)
            write_json(root, 'latest_audit', {'value': 'before'})
            write_json(root, 'latest_audit', {'value': 'after'}, rotate=True)
            self.assertEqual(load_json(root, 'previous_audit'), {'value': 'before'})
            self.assertEqual(load_json(root, 'latest_audit'), {'value': 'after'})

    def test_failed_rotation_preserves_both_published_snapshots(self) -> None:
        with tempfile.TemporaryDirectory(prefix='atlas-doctor-rotation-') as directory:
            root = Path(directory)
            write_json(root, 'latest_audit', {'value': 'original'})
            write_json(root, 'latest_audit', {'value': 'before'}, rotate=True)
            with patch('tools.atlas_doctor_lib.core.os.replace', side_effect=OSError('rotation denied')):
                with self.assertRaisesRegex(OSError, 'rotation denied'):
                    write_json(root, 'latest_audit', {'value': 'after'}, rotate=True)
            self.assertEqual(load_json(root, 'previous_audit'), {'value': 'original'})
            self.assertEqual(load_json(root, 'latest_audit'), {'value': 'before'})

    def test_live_trace_failure_states_reach_agent_report(self) -> None:
        directory = self.make_repo()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        runner = root / 'tools' / 'atlas_doctor_io_runner.py'
        runner.parent.mkdir()
        runner.write_text('# subprocess boundary fixture', encoding='utf-8')
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        process.wait.return_value = 0
        cases = (
            (None, True, 'UNAVAILABLE'),
            (b'{invalid json', True, 'FAIL'),
            (b'[]', True, 'FAIL'),
            (b'\\xff', True, 'FAIL'),
            (b'{"schema_version":1,"summary":{"unique_files":0},"slowest":[]}', True, 'PASS'),
            (None, False, 'DISABLED'),
        )
        for content, trace_io, expected in cases:
            with self.subTest(content=content, trace_io=trace_io):
                def launch(*args, **kwargs):
                    if content is not None:
                        path = Path(kwargs['env']['ATLAS_DOCTOR_IO_TRACE'])
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content)
                    return process

                with patch('tools.atlas_doctor_lib.live.git_state', return_value=git_state(root)), \
                        patch('tools.atlas_doctor_lib.live.subprocess.Popen', side_effect=launch):
                    payload = inspect_live(root, trace_io=trace_io, quiet=True)
                self.assertEqual(payload['io_trace_status'], expected)
                if expected == 'PASS':
                    self.assertIsInstance(payload['io_trace'], dict)
                    self.assertIsNone(payload['io_trace_reason'])
                else:
                    self.assertIsNone(payload['io_trace'])
                    self.assertTrue(payload['io_trace_reason'])
                report = build_ai_report(root)['live_performance']
                self.assertEqual(report['io_trace_status'], expected)
                self.assertEqual(report['io_trace_reason'], payload['io_trace_reason'])
                self.assertEqual(report['io_trace_path'], payload['io_trace_path'])

    def test_missing_live_runner_is_explicit(self) -> None:
        directory = self.make_repo()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        process.wait.return_value = 0
        with patch('tools.atlas_doctor_lib.live.git_state', return_value=git_state(root)), \
                patch('tools.atlas_doctor_lib.live.subprocess.Popen', return_value=process):
            payload = inspect_live(root, trace_io=True, quiet=True)
        self.assertEqual(payload['io_trace_status'], 'UNAVAILABLE')
        self.assertIn('runner is absent', payload['io_trace_reason'])

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
