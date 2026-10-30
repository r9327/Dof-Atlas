"""Regression proof for Doctor's unbounded static inventory and Unity triage."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.full_scope import (
    audit_full_scope, write_full_scope_report,
)


class DoctorFullScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for args in (
            ["init", "-q"], ["config", "user.email", "atlas@example.invalid"],
            ["config", "user.name", "Doctor Test"],
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True,
                           capture_output=True)

    def _file(self, name: str, content: str):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _commit(self):
        for args in (["add", "-A"], ["commit", "-qm", "fixture"]):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root,
                                       text=True).strip()

    def _unity(self):
        self._file("app/ui/unity_skin.py", "UNITY_PALETTE = {'BG': '#151821'}\n")
        self._file("app/ui/theme.py", "from app.ui.unity_skin import UNITY_PALETTE\n")

    def test_more_than_150_files_4000_functions_and_512k_are_scanned(self):
        self._unity()
        for n in range(151):
            self._file("app/mod_%03d.py" % n, "def function_%d():\n    return %d\n" % (n, n))
        huge = "# " + ("padding " * 85000) + "\n"
        self._file("app/giant.py", huge + "".join(
            "def item_%d():\n    return %d\n" % (n, n) for n in range(4002)
        ))
        sha = self._commit()
        result = audit_full_scope(self.root, expected_sha=sha)
        coverage = result["source_coverage"]
        self.assertEqual(coverage["status"], "PASS")
        self.assertEqual(coverage["total"], 155)
        self.assertEqual(coverage["inspected"], 155)
        self.assertEqual(coverage["functions_inspected"], 4153)
        self.assertFalse(coverage["truncated"])
        self.assertEqual(coverage["missing"], [])
        self.assertEqual(result["status"], "REVIEW")
        self.assertFalse(result["complete_application_certified"])
        self.assertEqual(result["unity_style"]["native_windows_visual"], "NOT_RUN")

    def test_style_candidates_do_not_become_false_visual_pass(self):
        self._unity()
        self._file("app/widgets.py", '''def update(button):
    button.setStyleSheet("QPushButton { color: #FFFFFF; }")
''')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha)
        names = {row["kind"] for row in report["unity_style"]["static_candidates"]}
        self.assertIn("LOCAL_QSS_OVERRIDE_REVIEW", names)
        self.assertIn("LOCAL_LITERAL_QSS_COLOR_REVIEW", names)
        self.assertEqual(report["unity_style"]["status"], "REVIEW")
        self.assertFalse(report["unity_style"]["visual_certified"])
        self.assertTrue(report["worktree_clean"])

    def test_missing_or_invalid_tracked_source_blocks_full_inventory(self):
        self._unity()
        self._file("app/ok.py", "answer = 42\n")
        sha = self._commit()
        (self.root / "app/ok.py").write_text("if :\n", encoding="utf-8")
        report = audit_full_scope(self.root, expected_sha=sha)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["source_coverage"]["total"], 3)
        self.assertEqual(report["source_coverage"]["inspected"], 2)
        self.assertEqual(report["source_coverage"]["parse_errors"][0]["file"], "app/ok.py")
        self.assertFalse(report["worktree_clean"])
        (self.root / "app/ok.py").unlink()
        report = audit_full_scope(self.root, expected_sha=sha)
        self.assertEqual(report["source_coverage"]["missing"], ["app/ok.py"])

    def test_sha_mismatch_fails_closed(self):
        self._file("app/ok.py", "pass\n")
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha="f" * 40)
        self.assertNotEqual(sha, "f" * 40)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "Expected SHA differs from exact checkout HEAD")

    def test_findings_untruncated_and_report_is_confined_to_artifacts(self):
        self._unity()
        for n in range(90):
            self._file("app/mod_%03d.py" % n, '''def reused():
    pass
''')
        sha = self._commit()
        report = audit_full_scope(self.root, expected_sha=sha)
        groups = report["findings"]["exact_ast_duplicate_groups"]
        self.assertGreaterEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["occurrences"]), 90)
        self.assertFalse(report["findings"]["truncated"])
        target = write_full_scope_report(
            self.root, Path("artifacts/doctor/full_scope.json"), report,
        )
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["candidate_sha"], sha)
        with self.assertRaises(ValueError):
            write_full_scope_report(self.root, Path("app/overwritten.json"), report)


if __name__ == "__main__":
    unittest.main()
