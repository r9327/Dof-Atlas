from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.certification_cumulative import assess_cumulative


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


class CumulativeCertificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "Doctor Test")
        git(self.root, "config", "user.email", "doctor@example.invalid")
        self.write("tools/readme.txt", "first")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "baseline")
        self.base = git(self.root, "rev-parse", "HEAD")

    def write(self, path: str, value: str):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value, encoding="utf-8")

    def commit(self, name="second") -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", name)
        return git(self.root, "rev-parse", "HEAD")

    def test_low_risk_cumulative_diff_does_not_authorize_skips(self):
        self.write("tools/readme.txt", "second")
        head = self.commit()
        outcome = assess_cumulative(self.root, baseline_sha=self.base, candidate_sha=head)
        self.assertEqual(outcome["status"], "NO_ADDITIONAL_ESCALATION")
        self.assertEqual(outcome["changed_paths"], ["tools/readme.txt"])
        self.assertFalse(outcome["base_full_proven"])
        self.assertFalse(outcome["authorizes_skipping_tests"])

    def test_multiple_small_changes_cross_domain_force_full(self):
        self.write("app/service/feature.py", "x = 1")
        self.write("data/encyclopedia/example.txt", "content")
        head = self.commit()
        result = assess_cumulative(self.root, baseline_sha=self.base, candidate_sha=head)
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("CROSS_DOMAIN_ACCUMULATION", result["reasons"])

    def test_sensitive_change_accumulation_escalates(self):
        self.write("main.py", "print('ready')")
        head = self.commit()
        result = assess_cumulative(self.root, baseline_sha=self.base, candidate_sha=head)
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("CUMULATIVE_RISK_HIGH", result["reasons"])

    def test_deleted_content_escalates(self):
        git(self.root, "rm", "tools/readme.txt")
        head = self.commit()
        result = assess_cumulative(self.root, baseline_sha=self.base, candidate_sha=head)
        self.assertEqual(result["status"], "FULL_REQUIRED")
        self.assertIn("CUMULATIVE_REMOVAL_OR_RENAME", result["reasons"])

    def test_head_mismatch_and_invalid_sha_are_blocked(self):
        self.write("tools/readme.txt", "changed")
        head = self.commit()
        self.assertEqual(assess_cumulative(
            self.root, baseline_sha=self.base, candidate_sha="c" * 40,
        )["status"], "BLOCKED")
        self.assertEqual(assess_cumulative(
            self.root, baseline_sha="untrusted", candidate_sha=head,
        )["status"], "BLOCKED")

    def test_wrong_ancestry_is_blocked(self):
        head = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(assess_cumulative(
            self.root, baseline_sha="a" * 40, candidate_sha=head,
        )["status"], "BLOCKED")

    def test_cumulative_base_that_is_not_an_ancestor_is_blocked(self):
        self.write("tools/readme.txt", "next")
        first = self.commit("first")
        git(self.root, "checkout", "-qb", "side", self.base)
        self.write("tools/readme.txt", "side")
        side = self.commit("side")
        git(self.root, "checkout", "-q", "master") if "master" in git(
            self.root, "branch", "--list", "master"
        ) else git(self.root, "checkout", "-q", "main")
        self.assertEqual(assess_cumulative(
            self.root, baseline_sha=side, candidate_sha=first,
        )["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
