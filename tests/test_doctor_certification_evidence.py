from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.certification_evidence import inspect_previous_evidence
from tools.atlas_doctor_lib.certification_passport import environment
from tools.atlas_doctor_lib.certification_engine import fingerprint
from tools.atlas_doctor_lib.certification_policy import POLICY_ID


def git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=root, check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


class EvidenceClosureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "Doctor Fixture")
        git(self.root, "config", "user.email", "doctor@invalid.local")
        self.write("tools/core.py", "ENABLED = True\n")
        self.write("requirements-pyside.txt", "requirements fixture\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")
        self.previous = git(self.root, "rev-parse", "HEAD")

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")

    def commit(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "next")
        return git(self.root, "rev-parse", "HEAD")

    def passport(self):
        record = {
            "candidate_sha": self.previous,
            "plan_fingerprint": "old-plan",
            "verdict": "SCOPED_PASS_NOT_FULL",
            "tests_passed": ["tests.test_dummy"],
            "execution": {"status": "SCOPED_TESTS_PASS"},
            "environment": environment(self.root),
            "policy_id": POLICY_ID,
            "authority": "ADVISORY_ONLY",
            "phase_certified": False, "release_certified": False,
            "full_suite_waived": False, "merge_authorized": False,
        }
        record["content_digest"] = fingerprint(record)
        return record

    def candidate_plan(self, sha):
        return {
            "candidate_sha": sha, "status": "READY_TO_RUN_SCOPED",
            "test_modules": ["tests.test_dummy"],
        }

    def test_docs_only_is_review_candidate_not_an_automatic_skip(self):
        self.write("docs/notes.md", "Documentation only")
        head = self.commit()
        result = inspect_previous_evidence(
            self.root, self.passport(), self.candidate_plan(head)
        )
        self.assertEqual(result["status"], "CANDIDATE_FOR_INDEPENDENT_PROVENANCE_REVIEW")
        self.assertTrue(result["git_non_doc_objects_unchanged"])
        self.assertFalse(result["github_provenance_authenticated"])
        self.assertFalse(result["automated_test_reuse_authorized"])
        self.assertFalse(result["tests_skipped"])
        self.assertFalse(result["full_suite_waived"])

    def test_python_or_data_changes_are_not_reusable(self):
        for changed in ("tools/core.py", "data/guide.json", "tests/test_dummy.py"):
            with self.subTest(changed=changed):
                self.write(changed, "changed\n")
                head = self.commit()
                result = inspect_previous_evidence(
                    self.root, self.passport(), self.candidate_plan(head)
                )
                self.assertIn("NON_DOCUMENTATION_GIT_OBJECT_CHANGED", result["reasons"])

    def test_changed_requirements_blocks(self):
        prior = self.passport()
        self.write("requirements-pyside.txt", "updated dependencies")
        head = self.commit()
        result = inspect_previous_evidence(
            self.root, prior, self.candidate_plan(head)
        )
        self.assertIn("EXECUTION_ENVIRONMENT_CHANGED", result["reasons"])

    def test_forged_digest_is_rejected(self):
        self.write("docs/notes.md", "docs")
        head = self.commit()
        previous = self.passport()
        previous["tests_passed"] = ["tests.test_dummy", "tests.test_other"]
        result = inspect_previous_evidence(
            self.root, previous, self.candidate_plan(head)
        )
        self.assertIn("INVALID_PRIOR_PASSPORT_INTEGRITY", result["reasons"])

    def test_head_mismatch_is_rejected(self):
        self.write("docs/notes.md", "docs")
        head = self.commit()
        result = inspect_previous_evidence(
            self.root, self.passport(), self.candidate_plan("c" * 40)
        )
        self.assertIn("UNVERIFIED_EXACT_GIT_ANCESTRY", result["reasons"])

    def test_no_previous_pass_is_eligible(self):
        self.write("docs/notes.md", "docs")
        head = self.commit()
        previous = self.passport()
        previous["verdict"] = "BLOCKED"
        result = inspect_previous_evidence(
            self.root, previous, self.candidate_plan(head)
        )
        self.assertIn("PREVIOUS_SCOPED_PASS_NOT_PROVEN", result["reasons"])


if __name__ == "__main__":
    unittest.main()
