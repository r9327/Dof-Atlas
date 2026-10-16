from __future__ import annotations

import py_compile
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import git_hook
from tools.check_generated_files import find_forbidden


ROOT = Path(__file__).resolve().parents[1]


class RepositoryGitHooksTests(unittest.TestCase):
    def test_pre_push_test_repositories_cannot_modify_the_repository_being_pushed(self) -> None:
        # Fixture setup itself must be safe even under the broken old hook.
        clean = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory) / "outer"
            foreign = Path(directory) / "foreign"
            outer.mkdir()
            foreign.mkdir()

            def git(*args):
                return subprocess.run(["git", *args], cwd=outer, env=clean,
                                      capture_output=True, text=True, check=True).stdout.strip()

            git("init")
            git("config", "user.name", "Outer")
            git("config", "user.email", "outer@example.invalid")
            (outer / "original.txt").write_text("outer", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "outer baseline")
            before = git("rev-parse", "HEAD")
            index = outer / ".git/index"
            digest = hashlib.sha256(index.read_bytes()).hexdigest()
            child = """
import pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
def git(*args):
    subprocess.run(['git', *args], cwd=root, capture_output=True, check=True)
git('init')
git('config', 'user.name', 'Foreign')
git('config', 'user.email', 'foreign@example.invalid')
(root / 'foreign.txt').write_text('foreign', encoding='utf-8')
git('add', '.')
git('commit', '-m', 'foreign baseline')
git('config', 'core.bare', 'true')
"""

            def gate(command, root, *, env):
                self.assertIn("tools.atlas_integrity", command)
                self.assertIn("fast", command)
                completed = subprocess.run([sys.executable, "-c", child, str(foreign)],
                                           cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return completed.returncode

            injected = dict(clean, GIT_DIR=str(outer / ".git"),
                            GIT_COMMON_DIR=str(outer / ".git"), GIT_WORK_TREE=str(outer),
                            GIT_INDEX_FILE=str(index), GIT_PREFIX="subdirectory/")
            with patch.dict(os.environ, injected, clear=True), patch.object(git_hook, "run", side_effect=gate):
                self.assertEqual(git_hook.pre_push(outer), 0)
                self.assertEqual(os.environ["GIT_INDEX_FILE"], str(index))
            self.assertEqual(git("rev-parse", "HEAD"), before)
            self.assertEqual(git("config", "user.name"), "Outer")
            self.assertEqual(git("config", "core.bare"), "false")
            self.assertEqual(hashlib.sha256(index.read_bytes()).hexdigest(), digest)
            self.assertTrue((foreign / ".git").is_dir())

    def test_tracked_hook_entrypoints_and_installer_exist(self) -> None:
        for relative in (
            ".githooks/pre-commit",
            ".githooks/pre-push",
            "tools/pre_commit.ps1",
            "tools/pre_push.ps1",
            "tools/install_git_hooks.ps1",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_staged_syntax_failure_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "broken.py"
            invalid.write_text("def broken(:\n", encoding="utf-8")
            with patch.object(git_hook, "staged_python_files", return_value=[invalid]):
                self.assertNotEqual(git_hook.check_staged_syntax(Path(directory)), 0)

    def test_forbidden_staged_file_blocks_commit(self) -> None:
        self.assertTrue(find_forbidden(["logs/start_log.txt"]))

    def test_pre_push_delegates_to_fast_integrity_gate(self) -> None:
        source = (ROOT / "tools/pre_push.ps1").read_text(encoding="utf-8")
        python_source = (ROOT / "tools/git_hook.py").read_text(encoding="utf-8")
        self.assertIn("tools.git_hook pre-push", source)
        self.assertIn('"tools.atlas_integrity", "fast"', python_source)
        shell_hook = (ROOT / ".githooks/pre-push").read_text(encoding="utf-8")
        self.assertIn('git lfs pre-push "$@"', shell_hook)


if __name__ == "__main__":
    unittest.main()
