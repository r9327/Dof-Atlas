from __future__ import annotations

import py_compile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import git_hook
from tools.check_generated_files import find_forbidden


ROOT = Path(__file__).resolve().parents[1]


class RepositoryGitHooksTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
