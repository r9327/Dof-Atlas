from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor import build_parser
from tools.atlas_doctor_lib.ponytail import evaluate_ponytail

ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


class AtlasDoctorPonytailTests(unittest.TestCase):
    def make_repo(self) -> tempfile.TemporaryDirectory:
        directory = tempfile.TemporaryDirectory(prefix='atlas-ponytail-')
        root = Path(directory.name)
        _git(root, 'init')
        _git(root, 'config', 'user.email', 'atlas-tests@example.invalid')
        _git(root, 'config', 'user.name', 'Atlas Tests')
        (root / 'app').mkdir()
        (root / 'tools').mkdir()
        shutil.copy2(ROOT / 'tools' / 'ponytail_policy.json', root / 'tools' / 'ponytail_policy.json')
        (root / 'app' / 'existing.py').write_text('def existing():\n    return 1\n', encoding='utf-8')
        _git(root, 'add', '-A')
        _git(root, 'commit', '-m', 'baseline')
        directory.root = root  # type: ignore[attr-defined]
        return directory

    def test_cli_exposes_ponytail_command(self) -> None:
        args = build_parser().parse_args(['ponytail', '--base-ref', 'HEAD'])
        self.assertEqual(args.command, 'ponytail')
        self.assertEqual(args.base_ref, 'HEAD')

    def test_small_direct_change_passes(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            (root / 'app' / 'existing.py').write_text('def existing():\n    return 2\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'small change')
            payload = evaluate_ponytail(root)
            self.assertEqual(payload['status'], 'PASS')
            self.assertEqual(payload['summary']['findings_total'], 0)
        finally:
            directory.cleanup()

    def test_dependency_manifest_change_requires_review(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            (root / 'requirements-pyside.txt').write_text('example-package==1.0\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'dependency')
            payload = evaluate_ponytail(root)
            rules = {item['rule'] for item in payload['findings']}
            self.assertEqual(payload['status'], 'REVIEW')
            self.assertIn('ponytail_dependency_manifest_change', rules)
        finally:
            directory.cleanup()

    def test_low_fanin_new_abstraction_requires_review(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            (root / 'app' / 'extra.py').write_text('class ExampleFactory:\n    pass\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'factory')
            payload = evaluate_ponytail(root)
            rules = {item['rule'] for item in payload['findings']}
            self.assertIn('ponytail_low_fanin_abstraction', rules)
        finally:
            directory.cleanup()

    def test_parallel_marker_is_evidence_not_failure(self) -> None:
        directory = self.make_repo()
        try:
            root = Path(directory.name)
            (root / 'app' / 'feature_v2.py').write_text('VALUE = 2\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'parallel')
            payload = evaluate_ponytail(root)
            rules = {item['rule'] for item in payload['findings']}
            self.assertEqual(payload['status'], 'REVIEW')
            self.assertIn('ponytail_parallel_path_marker', rules)
            self.assertNotEqual(payload['status'], 'FAIL')
        finally:
            directory.cleanup()

    def test_missing_policy_is_only_fatal_when_explicitly_required(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix='atlas-ponytail-missing-')
        try:
            root = Path(directory.name)
            _git(root, 'init')
            _git(root, 'config', 'user.email', 'atlas-tests@example.invalid')
            _git(root, 'config', 'user.name', 'Atlas Tests')
            (root / 'main.py').write_text('print("ok")\n', encoding='utf-8')
            _git(root, 'add', '-A')
            _git(root, 'commit', '-m', 'baseline')
            self.assertEqual(evaluate_ponytail(root, required=False)['status'], 'UNAVAILABLE')
            self.assertEqual(evaluate_ponytail(root, required=True)['status'], 'FAIL')
        finally:
            directory.cleanup()


if __name__ == '__main__':
    unittest.main()
