"""Pure-Python tests of the PR254 pre-CI runner's PASS/FAIL contract."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.assets.unity_pre_ci import SOURCE_FILES, STDLIB_TESTS, examine


class PreCiRunnerTests(unittest.TestCase):
    def test_green_tree_then_source_and_test_failure(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            for name in SOURCE_FILES:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("value = 1\n", encoding="utf-8")
            for name in STDLIB_TESTS:
                (root / name).write_text(
                    "import unittest\n"
                    "class T(unittest.TestCase):\n"
                    " def test_ok(self): self.assertTrue(True)\n"
                    "if __name__ == '__main__': unittest.main()\n",
                    encoding="utf-8",
                )
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run([
                "git", "-c", "user.name=PreCiFixture",
                "-c", "user.email=fixture@localhost", "commit", "-qm", "fixture",
            ], cwd=root, check=True)
            passing = examine(root)
            self.assertEqual(passing["status"], "PASS", passing["checks"])
            self.assertEqual(len(passing["head_sha"]), 40)
            self.assertFalse(passing["github_ci_launched"])
            exact = examine(root, expected_sha=passing["head_sha"])
            self.assertEqual(exact["checks"]["git_revision"]["status"], "PASS")
            stale = examine(root, expected_sha="0" * 40)
            self.assertEqual(stale["status"], "FAIL")
            self.assertEqual(stale["checks"]["git_revision"]["status"], "FAIL")
            invalid = examine(root, expected_sha="not-a-sha")
            self.assertEqual(invalid["status"], "FAIL")

            broken_source = root / SOURCE_FILES[0]
            broken_source.write_text("def nope(:\n", encoding="utf-8")
            syntax_failure = examine(root)
            self.assertEqual(syntax_failure["status"], "FAIL")
            self.assertEqual(syntax_failure["checks"]["python_syntax"]["status"], "FAIL")
            self.assertEqual(
                syntax_failure["checks"]["tracked_worktree_clean"]["status"], "FAIL"
            )

            broken_source.write_text("value = 1\n", encoding="utf-8")
            broken_test = root / STDLIB_TESTS[0]
            broken_test.write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                " def test_failure(self): self.fail('controlled failure')\n"
                "if __name__ == '__main__': unittest.main()\n",
                encoding="utf-8",
            )
            failed = examine(root)
            self.assertEqual(failed["status"], "FAIL")
            self.assertEqual(failed["checks"][STDLIB_TESTS[0]]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
